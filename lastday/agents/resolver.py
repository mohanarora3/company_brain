"""Resolver: works out which accounts in which systems belong to which employee.

Every tool knows people differently: Slack hides some emails, Jira hides most,
commits carry personal or noreply addresses, and two people show up as
"Rahul V". The Resolver links them in three passes:

  1. federated joins on email (HR x Slack, HR x Jira, HR x PagerDuty, and
     HR x GitHub commit authors) run as single cross-source queries;
  2. name and handle matching for the rest, with a confidence score;
  3. ambiguous accounts are left unassigned with their candidates, until the
     Critic asks for disambiguation, which uses co-activity (which systems the
     account works on versus each candidate's team and other accounts).

The identity map is what makes every later share and backup number honest.
"""
from __future__ import annotations

import re
from collections import defaultdict

from ..federation.base import ident, lit
from .blackboard import Blackboard


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z ]", " ", (s or "").lower()).strip()


def jaro_winkler(a: str, b: str) -> float:
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if not la or not lb:
        return 0.0
    rng = max(la, lb) // 2 - 1
    am, bm = [False] * la, [False] * lb
    m = 0
    for i, ca in enumerate(a):
        for j in range(max(0, i - rng), min(lb, i + rng + 1)):
            if not bm[j] and b[j] == ca:
                am[i] = bm[j] = True
                m += 1
                break
    if not m:
        return 0.0
    t, k = 0, 0
    for i in range(la):
        if am[i]:
            while not bm[k]:
                k += 1
            if a[i] != b[k]:
                t += 1
            k += 1
    jaro = (m / la + m / lb + (m - t / 2) / m) / 3
    prefix = 0
    for ca, cb in zip(a[:4], b[:4]):
        if ca != cb:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


def name_score(candidate: str, full_name: str) -> float:
    """How well an account's name or handle matches an employee's full name."""
    c, f = _norm(candidate), _norm(full_name)
    if not c or not f:
        return 0.0
    ft = f.split()
    first, last = ft[0], ft[-1]
    ct = c.split()
    if c == f:
        return 0.95
    if len(ct) >= 2 and ct[0] == first and (ct[-1] == last[0] or ct[-1] == last[:len(ct[-1])]):
        return 0.78                                   # "Priya R" / "Priya Ra"
    handle = c.replace(" ", "")
    patterns = {first + last, first[0] + last, first + last[0], last + first[0], last, f"{first}{last[:1]}"}
    if handle in patterns or any(handle.startswith(p) and len(p) >= 5 for p in patterns if len(p) >= 5):
        return 0.74
    if len(ct) == 1 and ct[0] == first:
        return 0.6
    jw = jaro_winkler(c, f)
    return 0.8 if jw >= 0.93 else 0.0


class Resolver:
    name = "Resolver"

    def run(self, bb: Blackboard) -> None:
        bb.emit(self.name, "start", "Linking accounts across systems to HR employees")
        res = bb.sql(self.name, "Load the governed HR directory",
                     "SELECT employee_id, full_name, preferred_name, work_email, title, team, team_id, manager_id, "
                     "employment_type, status, last_day FROM hr_pg.employees_directory")
        for r in (res.rows if res else []):
            bb.directory[r["employee_id"]] = r
        dep = bb.sql(self.name, "Who is leaving (HR departures)",
                     "SELECT d.employee_id AS employee_id, d.last_day AS last_day, e.full_name AS full_name, "
                     "e.status AS status FROM hr_pg.departures d JOIN hr_pg.employees_directory e "
                     "ON e.employee_id = d.employee_id")
        bb.leaving = {r["employee_id"] for r in (dep.rows if dep else [])}

        smap = bb.source_map
        id_tables = {q: e for q, e in smap.items() if e["identity"] and e["source"] != "hr_pg"}
        accounts: dict[str, dict[str, dict]] = defaultdict(dict)   # source -> account id -> attrs
        self.id_col: dict[str, str] = {}
        for q, e in id_tables.items():
            src = e["source"]
            cols = e["columns"]
            idc = next((c for c in ("user_id", "account_id", "login", "id") if c in cols), cols[0])
            self.id_col[src] = idc
            sel = [idc] + [c for c in cols if c != idc and (c in e["roles"]["name"] or c in e["roles"]["email"]
                                                             or c in ("name", "account_type", "deleted", "active"))]
            r = bb.sql(self.name, f"Load {src} accounts", f"SELECT {', '.join(ident(c) for c in sel)} FROM {q}")
            for row in (r.rows if r else []):
                accounts[src][str(row[idc])] = row

        links: dict[tuple, dict] = {}

        def link(src: str, acct: str, eid: str, method: str, conf: float, query_id: str = "") -> None:
            cur = links.get((src, acct))
            if not cur or conf > cur["confidence"]:
                links[(src, acct)] = {"person": eid, "method": method, "confidence": round(conf, 2), "query_id": query_id}

        # Pass 1: federated email joins, one cross-source query per system.
        for q, e in id_tables.items():
            src, email_cols = e["source"], e["roles"]["email"]
            if not email_cols:
                continue
            idc, ec = self.id_col[src], email_cols[0]
            r = bb.sql(self.name, f"Federated join HR x {src} on email",
                       f"SELECT e.employee_id AS employee_id, u.{ident(idc)} AS account FROM hr_pg.employees_directory e "
                       f"JOIN {q} u ON lower(e.work_email) = lower(u.{ident(ec)})")
            for row in (r.rows if r else []):
                link(src, str(row["account"]), row["employee_id"], "email match (federated join)", 0.99, r.note)
        if "github.commits" in smap:
            r = bb.sql(self.name, "Federated join HR x GitHub commit authors on email",
                       "SELECT e.employee_id AS employee_id, c.author_login AS account, COUNT(*) AS n "
                       "FROM github.commits c JOIN hr_pg.employees_directory e ON lower(c.author_email) = lower(e.work_email) "
                       "GROUP BY e.employee_id, c.author_login", numeric=("n",))
            for row in (r.rows if r else []):
                link("github", str(row["account"]), row["employee_id"], "commit email match (federated join)", 0.97, r.note)
            names = bb.sql(self.name, "Commit author names per login",
                           "SELECT author_login AS login, author_name AS name, COUNT(*) AS n FROM github.commits "
                           "GROUP BY author_login, author_name", numeric=("n",))
            for row in (names.rows if names else []):
                acct = accounts["github"].setdefault(str(row["login"]), {"login": row["login"]})
                acct.setdefault("_names", []).append(row["name"])

        # Pass 2: names and handles for accounts nobody matched by email.
        ambiguous = []
        for src, accts in accounts.items():
            for acct, row in accts.items():
                if (src, acct) in links:
                    continue
                if str(row.get("account_type", "")).lower() == "bot":
                    links[(src, acct)] = {"person": None, "method": "bot account", "confidence": 1.0}
                    continue
                cand_names = [row.get(c) for c in ("real_name", "display_name", "name", "full_name") if row.get(c)]
                cand_names += row.get("_names", []) + [acct]
                scores = []
                for eid, d in bb.directory.items():
                    best = max((name_score(n, d["full_name"]) for n in cand_names), default=0.0)
                    if best > 0:
                        scores.append((best, eid))
                scores.sort(reverse=True)
                if not scores:
                    continue
                top, eid = scores[0]
                runner = scores[1][0] if len(scores) > 1 else 0.0
                if top >= 0.6 and top - runner >= 0.12:
                    link(src, acct, eid, "name/handle match", top)
                elif top >= 0.6:
                    cands = [e for s, e in scores if top - s < 0.12]
                    links[(src, acct)] = {"person": None, "method": "ambiguous name", "confidence": 0.0,
                                          "candidates": cands, "names": cand_names[:3]}
                    ambiguous.append((src, acct, cands))

        # Docs and other sources without their own user table: find whose ids they use.
        self._borrowed_namespaces(bb, accounts)

        bb.account_owner = links
        self._rebuild(bb)
        matched = sum(1 for v in links.values() if v.get("person"))
        bb.emit(self.name, "identities", f"Linked {matched} accounts to {len(bb.identities)} employees; "
                f"{len(ambiguous)} ambiguous", ambiguous=[{"source": s, "account": a, "candidates": [bb.person_name(c) for c in cs]}
                                                         for s, a, cs in ambiguous],
                methods=_count(v["method"] for v in links.values()))
        for s, a, cs in ambiguous:
            bb.findings.append({"agent": self.name, "kind": "identity_ambiguous", "source": s, "account": a,
                                "candidates": cs, "names": links[(s, a)].get("names")})

    def _borrowed_namespaces(self, bb: Blackboard, accounts: dict) -> None:
        """e.g. docs.pages.author_id holds Atlassian account ids, the same namespace as jira.users."""
        bb.source_map.setdefault("_namespaces", {})
        for q, e in bb.source_map.items():
            if q.startswith("_") or e.get("identity") or e["source"] in accounts or not e["roles"]["person"]:
                continue
            col = e["roles"]["person"][0]
            r = bb.sql(self.name, f"Which identity namespace does {q}.{col} use?",
                       f"SELECT DISTINCT {ident(col)} AS v FROM {q}")
            vals = {str(v) for v in (r.col("v") if r else []) if v}
            best = max(((len(vals & set(acc)) / max(1, len(vals)), src) for src, acc in accounts.items()), default=(0, ""))
            if best[0] >= 0.6:
                bb.source_map["_namespaces"][e["source"]] = best[1]
                bb.emit(self.name, "namespace", f"{q}.{col} uses {best[1]} account ids ({best[0]:.0%} overlap)",
                        table=q, namespace=best[1])

    def _rebuild(self, bb: Blackboard) -> None:
        ids: dict = defaultdict(lambda: defaultdict(list))
        for (src, acct), v in bb.account_owner.items():
            if v.get("person"):
                ids[v["person"]][src].append({"account": acct, "method": v["method"], "confidence": v["confidence"]})
        bb.identities = {k: dict(v) for k, v in ids.items()}

    # ------------------------------------------------------- disambiguation
    def disambiguate(self, bb: Blackboard, source: str, account: str) -> dict | None:
        """Resolve an ambiguous account by co-activity: what it works on versus each candidate."""
        info = bb.account_owner.get((source, account))
        if not info or not info.get("candidates"):
            return None
        cands = info["candidates"]
        systems = self._account_systems(bb, source, account)
        scores = {}
        for eid in cands:
            team = (bb.directory.get(eid) or {}).get("team_id")
            team_hits = sum(n for sysid, n in systems.items() if (bb.systems.get(sysid) or {}).get("owner_team", "").lower().startswith((team or "?")[:4]))
            overlap = 0
            for src2, accts in (bb.identities.get(eid) or {}).items():
                for a in accts:
                    other = self._account_systems(bb, src2, a["account"])
                    overlap += sum(min(n, other.get(s, 0)) for s, n in systems.items())
            total = max(1, sum(systems.values()))
            scores[eid] = round(0.6 * team_hits / total + 0.4 * min(1.0, overlap / total), 3)
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        best, second = ranked[0], ranked[1] if len(ranked) > 1 else (None, 0.0)
        decided = best[1] >= 0.4 and best[1] - second[1] >= 0.2
        verdict = {"source": source, "account": account, "scores": {bb.person_name(k): v for k, v in scores.items()},
                   "systems": systems, "decided": bool(decided), "person": best[0] if decided else None}
        if decided:
            bb.account_owner[(source, account)] = {"person": best[0], "method": "co-activity disambiguation",
                                                   "confidence": round(0.6 + 0.4 * best[1], 2), "candidates": cands}
            self._rebuild(bb)
        bb.emit(self.name, "disambiguation",
                f"{source} account '{', '.join(info.get('names') or [account])}' -> "
                + (f"{bb.person_name(best[0])} (team and co-activity)" if decided else "still ambiguous, left unattributed"),
                **verdict)
        return verdict

    def _account_systems(self, bb: Blackboard, source: str, account: str) -> dict:
        """Systems an account is active on, from whichever activity tables reference it."""
        out: dict[str, int] = defaultdict(int)
        if source == "jira":
            r = bb.sql(self.name, f"Components worked by jira account {account[:8]}",
                       f"SELECT component AS system, COUNT(*) AS n FROM jira.issues WHERE assignee_id = {lit(account)} "
                       "GROUP BY component", numeric=("n",))
            for row in (r.rows if r else []):
                out[row["system"]] += row["n"]
        elif source == "slack":
            r = bb.sql(self.name, f"Channels used by slack account {account}",
                       f"SELECT channel_name AS channel, COUNT(*) AS n FROM slack.messages WHERE user_id = {lit(account)} "
                       "GROUP BY channel_name", numeric=("n",))
            for row in (r.rows if r else []):
                for sid, s in bb.systems.items():
                    if s.get("slack_channel") == row["channel"]:
                        out[sid] += row["n"] / 4
        elif source == "github":
            r = bb.sql(self.name, f"Paths touched by github login {account}",
                       "SELECT sc.system_id AS system, COUNT(DISTINCT c.sha) AS n FROM github.commits c "
                       "JOIN github.commit_files f ON f.sha = c.sha JOIN github.service_catalog sc "
                       "ON substr(f.path, 1, length(sc.repo_path)) = sc.repo_path "
                       f"WHERE c.author_login = {lit(account)} GROUP BY sc.system_id", numeric=("n",))
            for row in (r.rows if r else []):
                out[row["system"]] += row["n"]
        return dict(out)


def _count(items) -> dict:
    out: dict = defaultdict(int)
    for i in items:
        out[i] += 1
    return dict(out)
