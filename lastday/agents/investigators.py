"""Investigators: the probes that turn federated rows into evidence.

Each probe is a small set of read-only Lightning SQL queries against the
sources the Cartographer found, followed by attribution to catalog systems and
to resolved employees. Every Evidence row keeps the id of the query that
produced it, so any claim in the final report can be traced to SQL.

Probes:
  footprint      the departing person's own activity in every source
  code           commits per system and author (repo path -> service catalog)
  reviews        pull-request reviewers per system
  work           Jira issues per component and assignee
  conversation   Slack thread answers, attributed to systems from the thread text
  activity:<t>   any discovered table linking people to catalog systems (e.g. PagerDuty)
  docs           wiki pages per system: freshness, author still here?
  access         privileged access only the departing person holds
  chores         recurring tickets that stop when the owner leaves
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from ..federation.base import ident, in_list, lit
from ..llm.embeddings import get_embedder
from .blackboard import Blackboard, Evidence

WEIGHTS = {"commit": 1.0, "review": 0.6, "slack_answer": 2.0, "issue_done": 1.2, "issue_open": 0.5,
           "chore": 1.5, "activity": 1.5}
HALF_LIFE_DAYS = 240
TIP_HINT = re.compile(r"(--[a-z]|\b\d+(\.\d+)?\s?(%|h|hours?|minutes?|days?|rps|s)\b|\bnever\b|\balways\b|\bdon't\b|"
                      r"\bnot\b.*\bbut\b|\.ya?ml|\.py|\btable\b|\bacct\b|\bcheckpoint\b|\bbecause\b)", re.I)


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromtimestamp(float(s), tz=timezone.utc)
        except ValueError:
            return None


def decay(at: str | None, as_of: date) -> float:
    d = _dt(at)
    if not d:
        return 0.5
    age = (datetime(as_of.year, as_of.month, as_of.day, tzinfo=timezone.utc) - d).days
    return math.exp(-max(0, age) / HALF_LIFE_DAYS * math.log(2))


def _norm(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9 ]", " ", (text or "").lower().replace("-", " ").replace("_", " ")) + " "


class Attributor:
    """Decides which catalog system a piece of text is about."""

    def __init__(self, systems: dict):
        self.systems = systems
        self.terms = {}
        for sid, s in systems.items():
            names = {_norm(s.get("name", "")).strip(), _norm(sid).strip()}
            names.discard("")
            aliases = {_norm(a).strip() for a in s.get("alias_list", [])}
            self.terms[sid] = (names, aliases)
        self._emb = None

    def scores(self, text: str, channel: str | None = None) -> dict[str, float]:
        t = _norm(text)
        out: dict[str, float] = {}
        for sid, (names, aliases) in self.terms.items():
            sc = sum(3.0 for n in names if f" {n} " in t)
            sc += sum(2.0 for a in aliases if f" {a} " in t)
            if sc and channel and self.systems[sid].get("slack_channel") == channel:
                sc += 0.5
            if sc:
                out[sid] = sc
        return out

    def best(self, text: str, channel: str | None = None, allow_semantic: bool = True,
             answer: str = "") -> tuple[str | None, str]:
        """text is the topic (a thread's question, a page title); answer text counts for less."""
        sc = {k: v * 1.5 for k, v in self.scores(text, channel).items()}
        for k, v in self.scores(answer).items():
            sc[k] = sc.get(k, 0.0) + v
        text = f"{text} {answer}".strip()
        if sc:
            ranked = sorted(sc.items(), key=lambda x: -x[1])
            if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
                return ranked[0][0], "keyword"
            return None, "tie"
        if not allow_semantic:
            return None, "none"
        # No keyword: fall back to embedding similarity against the catalog (NVIDIA NIM when configured).
        emb = get_embedder()
        cands = [sid for sid, s in self.systems.items() if not channel or s.get("slack_channel") == channel] or list(self.systems)
        sims = emb.similarity(text, [f"{self.systems[c]['name']}. {self.systems[c].get('description', '')}" for c in cands])
        i = max(range(len(cands)), key=lambda k: sims[k])
        floor = 0.42 if emb.remote_ok else 0.32
        return (cands[i], "semantic") if sims[i] >= floor else (None, "none")


class Investigators:
    name = "Investigator"

    def __init__(self, bb: Blackboard, window_days: int = 365):
        self.bb = bb
        self.cut = (bb.as_of - timedelta(days=window_days)).isoformat()
        self.attr = Attributor(bb.systems)
        self.target = bb.target["employee_id"]
        # raw[system][(source, account)] -> decayed weight. Accounts map to people at scoring time,
        # so a later identity fix (Critic -> Resolver) re-attributes everything without re-querying.
        self.raw: dict = defaultdict(lambda: defaultdict(float))
        self.raw_last: dict = defaultdict(dict)       # system -> (source, account) -> last activity
        self.threads: dict = defaultdict(list)        # system -> [thread dicts]
        self.done: set[tuple] = set()

    # ------------------------------------------------------------ helpers
    def accounts(self, eid: str, source: str) -> list[str]:
        ns = self.bb.source_map.get("_namespaces", {}).get(source, source)
        return [a["account"] for a in (self.bb.identities.get(eid) or {}).get(ns, [])]

    def owner(self, source: str, account: str | None) -> str:
        if account is None:
            return "?"
        ns = self.bb.source_map.get("_namespaces", {}).get(source, source)
        info = self.bb.account_owner.get((ns, str(account)))
        return info["person"] if info and info.get("person") else "?"

    def add(self, system: str, account: str | None, source: str, kind: str, ref: str, title: str, at: str | None,
            qid: str, weight: float | None = None, count: int = 1) -> None:
        w = (weight if weight is not None else WEIGHTS.get(kind, 1.0)) * count * decay(at, self.bb.as_of)
        key = (source, str(account) if account is not None else "?")
        self.raw[system][key] += w
        prev = self.raw_last[system].get(key)
        if at and (not prev or str(at) > prev):
            self.raw_last[system][key] = str(at)
        person = self.owner(source, account)
        if person == self.target or kind in ("chore", "access"):
            self.bb.add_evidence(Evidence(f"{source}:{kind}:{ref}", source, kind, system, None if person == "?" else person,
                                          str(ref), title, str(at or ""), round(w, 3), qid))

    def person_weights(self, system: str) -> dict[str, dict[str, float]]:
        """person (or "?") -> source -> weight, using the identity map as it stands now."""
        out: dict = defaultdict(lambda: defaultdict(float))
        for (src, acct), w in self.raw.get(system, {}).items():
            out[self.owner(src, None if acct == "?" else acct)][src] += w
        return {k: dict(v) for k, v in out.items()}

    def last_at(self, system: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for (src, acct), at in self.raw_last.get(system, {}).items():
            p = self.owner(src, None if acct == "?" else acct)
            if at and at > out.get(p, ""):
                out[p] = at
        return out

    def forget(self, source: str) -> None:
        """Drop cached probe runs that touched a source, so a retry re-queries it."""
        probe_sources = {"code": "github", "reviews": "github", "work": "jira", "conversation": "slack"}
        self.done = {k for k in self.done if probe_sources.get(k[0], k[0].split(":")[-1].split(".")[0]) != source}

    def _run_once(self, key: tuple) -> bool:
        if key in self.done:
            return False
        self.done.add(key)
        return True

    # ------------------------------------------------------------ footprint
    def footprint(self) -> dict[str, dict[str, float]]:
        """Where does the departing person show up at all? Returns system -> source -> weight."""
        bb, eid = self.bb, self.target
        fp: dict = defaultdict(lambda: defaultdict(float))
        logins = self.accounts(eid, "github")
        if logins and "code" in bb.probes_available:
            r = bb.sql(self.name, f"{bb.person_name(eid)}'s commits by system (12 months)",
                       "SELECT sc.system_id AS system, COUNT(DISTINCT c.sha) AS n, MAX(c.committed_at) AS last_at "
                       "FROM github.commits c JOIN github.commit_files f ON f.sha = c.sha "
                       "JOIN github.service_catalog sc ON substr(f.path, 1, length(sc.repo_path)) = sc.repo_path "
                       f"WHERE c.author_login IN {in_list(logins)} AND c.committed_at >= {lit(self.cut)} "
                       "GROUP BY sc.system_id", numeric=("n",))
            for row in (r.rows if r else []):
                fp[row["system"]]["github"] += row["n"] * WEIGHTS["commit"] * decay(row["last_at"], bb.as_of)
        accts = self.accounts(eid, "jira")
        if accts and "work" in bb.probes_available:
            r = bb.sql(self.name, f"{bb.person_name(eid)}'s Jira work by component",
                       "SELECT component AS system, status, COUNT(*) AS n, MAX(updated) AS last_at FROM jira.issues "
                       f"WHERE assignee_id IN {in_list(accts)} AND created >= {lit(self.cut)} GROUP BY component, status",
                       numeric=("n",))
            for row in (r.rows if r else []):
                k = "issue_done" if row["status"] == "Done" else "issue_open"
                fp[row["system"]]["jira"] += row["n"] * WEIGHTS[k] * decay(row["last_at"], bb.as_of)
        sl = self.accounts(eid, "slack")
        if sl and "conversation" in bb.probes_available:
            r = bb.sql(self.name, f"{bb.person_name(eid)}'s Slack thread answers",
                       "SELECT ts, thread_ts, channel_name, text, created_at FROM slack.messages "
                       f"WHERE is_reply = 1 AND user_id IN {in_list(sl)} AND created_at >= {lit(self.cut)}")
            rows = r.rows if r else []
            roots = self._roots([x["thread_ts"] for x in rows])
            for row in rows:
                root = roots.get(row["thread_ts"], {})
                sysid, _ = self.attr.best(root.get("text", ""), row["channel_name"], allow_semantic=False, answer=row["text"])
                if sysid:
                    fp[sysid]["slack"] += WEIGHTS["slack_answer"] * decay(row["created_at"], bb.as_of)
        for probe in sorted(p for p in bb.probes_available if p.startswith("activity:")):
            table = probe.split(":", 1)[1]
            spec = bb.source_map[table]["activity"]
            src = table.split(".")[0]
            accts = self.accounts(eid, src)
            if not accts:
                continue
            r = bb.sql(self.name, f"{bb.person_name(eid)} in {table}",
                       f"SELECT {ident(spec['system_col'])} AS system, COUNT(*) AS n, MAX({ident(spec['time_col'])}) AS last_at "
                       f"FROM {table} WHERE {ident(spec['person_col'])} IN {in_list(accts)} "
                       f"AND {ident(spec['time_col'])} >= {lit(self.cut)} GROUP BY {ident(spec['system_col'])}", numeric=("n",))
            for row in (r.rows if r else []):
                if row["system"] in bb.systems:
                    fp[row["system"]][src] += row["n"] * WEIGHTS["activity"] * decay(row["last_at"], bb.as_of)
        return {k: dict(v) for k, v in fp.items()}

    def _roots(self, thread_ts: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        uniq = sorted(set(t for t in thread_ts if t))
        for i in range(0, len(uniq), 300):
            chunk = uniq[i:i + 300]
            r = self.bb.sql(self.name, f"Thread questions for {len(chunk)} answers",
                            f"SELECT ts, user_id, text FROM slack.messages WHERE is_reply = 0 AND ts IN {in_list(chunk)}")
            for row in (r.rows if r else []):
                out[row["ts"]] = row
        return out

    # --------------------------------------------------------------- shares
    def code(self, systems: list[str]) -> None:
        if "code" not in self.bb.probes_available or not self._run_once(("code", tuple(systems))):
            return
        r = self.bb.sql(self.name, f"Commit authorship for {len(systems)} systems (everyone)",
                        "SELECT sc.system_id AS system, c.author_login AS login, COUNT(DISTINCT c.sha) AS n, "
                        "MAX(c.committed_at) AS last_at FROM github.commits c JOIN github.commit_files f ON f.sha = c.sha "
                        "JOIN github.service_catalog sc ON substr(f.path, 1, length(sc.repo_path)) = sc.repo_path "
                        f"WHERE sc.system_id IN {in_list(systems)} AND c.committed_at >= {lit(self.cut)} "
                        "GROUP BY sc.system_id, c.author_login", numeric=("n",))
        for row in (r.rows if r else []):
            self.add(row["system"], row["login"], "github", "commit", f"{row['login']}@{row['system']}",
                     f"{row['n']} commits to {row['system']} by {row['login']}", row["last_at"], r.note, count=row["n"])

    def reviews(self, systems: list[str]) -> None:
        if "reviews" not in self.bb.probes_available or not self._run_once(("reviews", tuple(systems))):
            return
        paths = {s: (self.bb.systems[s].get("repo_path") or "") for s in systems if self.bb.systems[s].get("repo_path")}
        if not paths:
            return
        r = self.bb.sql(self.name, "Pull-request reviewers on those systems",
                        "SELECT number, author_login, reviewers, base_path, merged_at FROM github.pull_requests "
                        f"WHERE base_path IN {in_list(paths.values())} AND merged_at >= {lit(self.cut)}", numeric=("number",))
        by_path = {v: k for k, v in paths.items()}
        for row in (r.rows if r else []):
            sysid = by_path.get(row["base_path"])
            for login in [x.strip() for x in (row.get("reviewers") or "").split(",") if x.strip()]:
                self.add(sysid, login, "github", "review", f"pr{row['number']}:{login}", f"Reviewed PR #{row['number']}",
                         row["merged_at"], r.note)

    def work(self, systems: list[str]) -> None:
        if "work" not in self.bb.probes_available or not self._run_once(("work", tuple(systems))):
            return
        r = self.bb.sql(self.name, f"Jira work per component and assignee ({len(systems)} systems)",
                        "SELECT component AS system, assignee_id AS account, status, COUNT(*) AS n, MAX(updated) AS last_at "
                        f"FROM jira.issues WHERE component IN {in_list(systems)} AND created >= {lit(self.cut)} "
                        "AND assignee_id IS NOT NULL GROUP BY component, assignee_id, status", numeric=("n",))
        for row in (r.rows if r else []):
            kind = "issue_done" if row["status"] == "Done" else "issue_open"
            self.add(row["system"], row["account"], "jira", kind, f"{row['account']}@{row['system']}:{row['status']}",
                     f"{row['n']} {row['status']} issues on {row['system']}", row["last_at"], r.note, count=row["n"])

    def conversation(self, systems: list[str]) -> None:
        bb = self.bb
        if "conversation" not in bb.probes_available or not self._run_once(("conversation", tuple(systems))):
            return
        channels = sorted({bb.systems[s].get("slack_channel") for s in systems if bb.systems[s].get("slack_channel")})
        r = bb.sql(self.name, f"Slack thread answers in {', '.join('#' + c for c in channels)}",
                   "SELECT ts, thread_ts, channel_name, user_id, text, created_at FROM slack.messages "
                   f"WHERE is_reply = 1 AND channel_name IN {in_list(channels)} AND created_at >= {lit(self.cut)}")
        rows = r.rows if r else []
        roots = self._roots([x["thread_ts"] for x in rows])
        wanted = set(systems)
        semantic = 0
        for row in rows:
            root = roots.get(row["thread_ts"], {})
            sysid, how = self.attr.best(root.get("text", ""), row["channel_name"], answer=row["text"])
            semantic += how == "semantic"
            if sysid not in wanted:
                continue
            p = self.owner("slack", row["user_id"])
            txt = row["text"] or ""
            informative = len(txt) > 75 or (bool(TIP_HINT.search(txt)) and len(txt) > 45)
            self.add(sysid, row["user_id"], "slack", "slack_answer", f"{row['channel_name']}/{row['ts']}",
                     (root.get("text") or "")[:120], row["created_at"], r.note,
                     weight=WEIGHTS["slack_answer"] * (1.5 if informative else 1.0))
            self.threads[sysid].append({"ts": row["ts"], "channel": row["channel_name"], "question": root.get("text"),
                                        "asker": self.owner("slack", root.get("user_id")), "answer": row["text"],
                                        "answerer": p, "answer_account": row["user_id"], "asker_account": root.get("user_id"),
                                        "at": row["created_at"], "informative": informative,
                                        "query_id": r.note})
        bb.emit(self.name, "attribution", f"Attributed {sum(len(self.threads[s]) for s in systems)} Slack answers to "
                f"{len(systems)} systems ({semantic} by embedding similarity)", semantic=semantic,
                embedder=get_embedder().label)

    def activity(self, systems: list[str]) -> None:
        bb = self.bb
        for probe in sorted(p for p in bb.probes_available if p.startswith("activity:")):
            table = probe.split(":", 1)[1]
            if not self._run_once((probe, tuple(systems))):
                continue
            spec = bb.source_map[table]["activity"]
            src = table.split(".")[0]
            r = bb.sql(self.name, f"{table}: who handles these systems",
                       f"SELECT {ident(spec['system_col'])} AS system, {ident(spec['person_col'])} AS account, COUNT(*) AS n, "
                       f"MAX({ident(spec['time_col'])}) AS last_at FROM {table} WHERE {ident(spec['system_col'])} IN {in_list(systems)} "
                       f"AND {ident(spec['time_col'])} >= {lit(self.cut)} GROUP BY {ident(spec['system_col'])}, {ident(spec['person_col'])}",
                       numeric=("n",))
            for row in (r.rows if r else []):
                self.add(row["system"], row["account"], src, "activity", f"{row['account']}@{row['system']}",
                         f"{row['n']} records in {table} for {row['system']}", row["last_at"], r.note, count=row["n"])

    # ------------------------------------------------------------- context
    def docs(self, systems: list[str]) -> dict[str, dict]:
        bb = self.bb
        out: dict = {s: {"pages": [], "coverage": 0.0} for s in systems}
        if "docs" not in bb.probes_available:
            return out
        r = bb.sql(self.name, "Wiki pages: titles, authors, freshness",
                   "SELECT page_id, title, labels, author_id, last_editor_id, updated_at, body FROM docs.pages")
        as_of = datetime(bb.as_of.year, bb.as_of.month, bb.as_of.day, tzinfo=timezone.utc)
        for row in (r.rows if r else []):
            sysid, _ = self.attr.best(row["title"], allow_semantic=False, answer=row["body"])
            if sysid not in out:
                continue
            author = self.owner("docs", row["author_id"])
            editor = self.owner("docs", row["last_editor_id"])
            upd = _dt(row["updated_at"])
            age = (as_of - upd).days if upd else 999
            fresh = 1.0 if age <= 365 else 0.6 if age <= 540 else 0.3
            here = lambda e: e not in ("?", None) and bb.directory.get(e, {}).get("status") == "active" and e != self.target  # noqa: E731
            author_factor = 1.0 if (here(author) or here(editor)) else 0.5
            kind_w = {"runbook": 1.0, "howto": 0.8, "postmortem": 0.6, "adr": 0.5, "overview": 0.5}.get(row["labels"], 0.5)
            score = round(kind_w * fresh * author_factor, 2)
            page = {"page_id": row["page_id"], "title": row["title"], "kind": row["labels"], "updated_at": row["updated_at"],
                    "age_days": age, "author": bb.person_name(author), "author_id": author, "editor_id": editor,
                    "author_status": bb.directory.get(author, {}).get("status", "unknown"), "score": score,
                    "body": row["body"], "query_id": r.note}
            out[sysid]["pages"].append(page)
            out[sysid]["coverage"] = max(out[sysid]["coverage"], score)
            bb.add_evidence(Evidence(f"docs:doc:{row['page_id']}", "docs", "doc", sysid, author if author != "?" else None,
                                     row["page_id"], row["title"], row["updated_at"], score, r.note))
        return out

    def access(self) -> list[dict]:
        bb = self.bb
        if "access" not in bb.probes_available:
            return []
        mine = bb.sql(self.name, f"Privileged access held by {bb.person_name(self.target)}",
                      f"SELECT resource, level, granted_at FROM hr_pg.access_grants WHERE employee_id = {lit(self.target)}")
        rows = mine.rows if mine else []
        if not rows:
            return []
        res = [x["resource"] for x in rows]
        others = bb.sql(self.name, "Who else holds the same access (federated: grants x directory)",
                        "SELECT g.resource AS resource, g.level AS level, g.employee_id AS employee_id, e.full_name AS full_name, "
                        "e.status AS status FROM hr_pg.access_grants g JOIN hr_pg.employees_directory e ON e.employee_id = g.employee_id "
                        f"WHERE g.resource IN {in_list(res)} AND g.employee_id <> {lit(self.target)}")
        holders = defaultdict(list)
        for o in (others.rows if others else []):
            if o["level"] in ("admin", "key-holder", "owner") and o["status"] == "active" and o["employee_id"] not in bb.leaving:
                holders[o["resource"]].append(o["full_name"])
        out = []
        for g in rows:
            if g["level"] not in ("admin", "key-holder", "owner"):
                continue
            sysid, how = self.attr.best(g["resource"].replace("-", " "), allow_semantic=True)
            item = {"resource": g["resource"], "level": g["level"], "system": sysid, "mapped_by": how,
                    "other_holders": holders.get(g["resource"], []), "exclusive": not holders.get(g["resource"]),
                    "query_id": mine.note}
            out.append(item)
            if sysid:
                self.bb.add_evidence(Evidence(f"hr_pg:access:{g['resource']}", "hr_pg", "access", sysid, self.target,
                                              g["resource"], f"{g['level']} on {g['resource']}", g["granted_at"], 1.0, mine.note))
        return out

    def chores(self, systems: list[str]) -> dict[str, list]:
        bb = self.bb
        out: dict = defaultdict(list)
        if "chores" not in bb.probes_available:
            return out
        since = (bb.as_of - timedelta(days=120)).isoformat()
        r = bb.sql(self.name, "Recurring chores in the last 4 months",
                   "SELECT issue_key, component, summary, assignee_id, status, created FROM jira.issues "
                   f"WHERE labels LIKE '%recurring%' AND created >= {lit(since)}")
        latest: dict = {}
        for row in (r.rows if r else []):
            key = (row["component"], row["summary"])
            if key not in latest or row["created"] > latest[key]["created"]:
                latest[key] = row
        for (system, summary), row in latest.items():
            owner = self.owner("jira", row["assignee_id"]) if row["assignee_id"] else None
            state = "stops when they leave" if owner == self.target else "already orphaned" if not owner else "owned by someone else"
            item = {"summary": summary.replace("[Recurring] ", ""), "issue_key": row["issue_key"], "owner": bb.person_name(owner),
                    "owner_id": owner, "status": row["status"], "state": state, "last_created": row["created"],
                    "query_id": r.note}
            out[system].append(item)
            if owner == self.target or not owner:
                bb.add_evidence(Evidence(f"jira:chore:{row['issue_key']}", "jira", "chore", system, owner, row["issue_key"],
                                         summary, row["created"], WEIGHTS["chore"], r.note))
                # Chore tickets already count as Jira work; here they only become evidence and checklist items.
        return out


def tacit_items(inv: Investigators, system: str, limit: int = 8) -> list[dict]:
    """The departing person's most informative answers on a system, deduplicated, newest first."""
    seen, out = set(), []
    threads = [t for t in inv.threads.get(system, []) if inv.owner("slack", t.get("answer_account")) == inv.target]
    threads.sort(key=lambda t: (not t["informative"], not any(c.isdigit() for c in t["answer"] or ""),
                                -(len(t["answer"] or ""))))
    for t in threads:
        key = (t["answer"] or "")[:80]
        if key in seen or not t["informative"]:
            continue
        seen.add(key)
        out.append({"text": t["answer"], "question": (t["question"] or "").replace("<@", "@").split(">", 1)[-1].strip(),
                    "channel": t["channel"], "ts": t["ts"], "at": t["at"],
                    "asker": inv.bb.person_name(inv.owner("slack", t.get("asker_account"))),
                    "evidence": f"slack:slack_answer:{t['channel']}/{t['ts']}", "query_id": t["query_id"]})
        if len(out) >= limit:
            break
    return out
