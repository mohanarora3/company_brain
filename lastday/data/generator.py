"""Generate a fictional company as raw records in five separate systems.

    python -m lastday generate --seed 42

The output under data/seed-<n>/ mirrors what each system's API returns:
HR rows (also as Postgres SQL), Slack users/channels/messages, Jira users and
issues, GitHub users/commits/files/PRs plus a service catalog, Confluence-style
docs, and PagerDuty users/incidents. Identities are deliberately inconsistent
across systems (missing emails, nicknames, personal commit emails, two people
called "Rahul V"), because that is what real companies look like.

_ground_truth.json records what is actually at risk for each departing person.
Only the evaluation harness reads it; the agents never do.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import string
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import storylines as S

MONTHS = 18
SCALE = 2.2
DOMAIN = "acmepay.example"

SOURCE_MIX = {
    "system": {"github": 0.45, "slack": 0.25, "jira": 0.18, "pagerduty": 0.12},
    "process": {"github": 0.05, "slack": 0.42, "jira": 0.48, "pagerduty": 0.05},
    "customer": {"github": 0.0, "slack": 0.55, "jira": 0.45, "pagerduty": 0.0},
}


@dataclass
class Person:
    role: str
    team: str
    title: str
    name: str
    employee_id: str
    work_email: str
    slack_handle: str
    slack_display: str
    jira_name: str
    github: str | None
    alt_email: str | None = None
    hide_slack_email: bool = False
    contractor: bool = False
    senior: bool = False
    status: str = "active"           # active | leaving | left
    last_day: date | None = None
    start_date: date | None = None
    activity: dict = field(default_factory=dict)
    source_bias: dict = field(default_factory=dict)
    slack_id: str = ""
    jira_id: str = ""
    pd_id: str = ""


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rid(rng: random.Random, n: int, alphabet: str = string.ascii_uppercase + string.digits) -> str:
    return "".join(rng.choice(alphabet) for _ in range(n))


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def _slug(name: str) -> str:
    return name.lower().replace(" ", ".")


class Company:
    def __init__(self, seed: int = 42, as_of: date | None = None):
        self.seed = seed
        self.rng = random.Random(seed)
        self.as_of = as_of or date.today()
        self.now = datetime(self.as_of.year, self.as_of.month, self.as_of.day, 18, 0, tzinfo=timezone.utc)
        self.start = self.now - timedelta(days=30 * MONTHS)
        self.systems = {s[0]: {"id": s[0], "name": s[1], "kind": s[2], "team": s[3], "tier": s[4],
                               "aliases": s[5], "description": s[6]} for s in S.SYSTEMS}
        self.people: list[Person] = []
        self.by_role: dict[str, Person] = {}
        self._cast()

    # ------------------------------------------------------------------ cast
    def _cast(self) -> None:
        rng = self.rng
        cast = {k: dict(v) for k, v in S.CAST.items()}
        if self.seed != 42:
            # Shuffle people between roles inside each team, and bring in a few new names.
            for team in S.TEAMS:
                roles = [r["role"] for r in S.ROLES if r["team"] == team and not r.get("left")]
                people = [cast[r] for r in roles]
                rng.shuffle(people)
                for r, p in zip(roles, people):
                    cast[r] = p
            spare = list(S.SPARE_NAMES)
            rng.shuffle(spare)
            swappable = [r for r, p in cast.items() if not p["name"].startswith("Rahul")]
            for role in rng.sample(swappable, 3):
                name, handle = spare.pop()
                first = name.split()[0]
                cast[role] = {"name": name, "slack": handle, "slack_display": f"{first} {name.split()[1][0]}",
                              "jira": name, "github": handle.replace(".", "-") + "-acme"}

        ids = list(range(1001, 1001 + len(S.ROLES)))
        rng.shuffle(ids)
        for spec, eid in zip(S.ROLES, ids):
            c = cast[spec["role"]]
            jitter = 1.0 if self.seed == 42 else None
            activity = {k: v * (jitter or rng.uniform(0.75, 1.3)) for k, v in spec["activity"].items()}
            p = Person(
                role=spec["role"], team=spec["team"], title=spec["title"], name=c["name"],
                employee_id=f"E{eid}", work_email=f"{_slug(c['name'])}@{DOMAIN}",
                slack_handle=c["slack"], slack_display=c["slack_display"], jira_name=c["jira"],
                github=c.get("github"), alt_email=c.get("alt_email"), hide_slack_email=c.get("hide_slack_email", False),
                contractor=spec.get("contractor", False), senior=spec.get("senior", False),
                activity=activity, source_bias=spec.get("source_bias", {}),
            )
            p.start_date = (self.start - timedelta(days=rng.randint(60, 1400))).date()
            if spec.get("left"):
                p.status, p.last_day = "left", self.as_of - timedelta(days=240)
            p.slack_id = "U0" + _rid(rng, 8)
            p.jira_id = hashlib.sha1(f"{seed_salt(self.seed)}{p.name}".encode()).hexdigest()[:24]
            p.pd_id = "P" + _rid(rng, 6)
            self.people.append(p)
            self.by_role[p.role] = p

        # Who is leaving. Seed 42 is the demo story; other seeds pick at random.
        if self.seed == 42:
            leavers = [("payments-staff", 12), ("platform-principal", 37)]
        else:
            pool = [p.role for p in self.people if p.senior and p.status == "active"]
            picks = rng.sample(pool, 2)
            leavers = [(picks[0], rng.randint(7, 20)), (picks[1], rng.randint(25, 50))]
        for role, days in leavers:
            p = self.by_role[role]
            p.status, p.last_day = "leaving", self.as_of + timedelta(days=days)

    def active_until(self, p: Person) -> datetime:
        if p.status == "left" and p.last_day:
            return datetime(p.last_day.year, p.last_day.month, p.last_day.day, tzinfo=timezone.utc)
        return self.now

    def rand_time(self, lo: datetime, hi: datetime) -> datetime:
        span = max(1, int((hi - lo).total_seconds()))
        t = lo + timedelta(seconds=self.rng.randint(0, span))
        # Office hours, mostly.
        return t.replace(hour=self.rng.choice([4, 5, 6, 7, 8, 9, 10, 11, 12, 13]), minute=self.rng.randint(0, 59))

    def experts(self, system: str, exclude: Person | None = None) -> list[tuple[Person, float]]:
        out = [(p, p.activity.get(system, 0.0)) for p in self.people
               if p is not exclude and p.activity.get(system, 0) > 0]
        return sorted(out, key=lambda x: -x[1])

    def pick_weighted(self, items: list[tuple[Person, float]]) -> Person | None:
        if not items:
            return None
        total = sum(w for _, w in items)
        r = self.rng.uniform(0, total)
        for p, w in items:
            r -= w
            if r <= 0:
                return p
        return items[-1][0]

    def pick_asker(self, system: str, expert: Person) -> Person:
        team = self.systems[system]["team"]
        cands = [(p, (2.0 if p.team == team else 0.6) + p.activity.get(system, 0) * 0.3)
                 for p in self.people if p is not expert and p.status != "left"]
        return self.pick_weighted(cands) or expert

    # --------------------------------------------------------------- generate
    def generate(self) -> dict:
        rng = self.rng
        slack_msgs, jira_issues, commits, commit_files, pulls, incidents = [], [], [], [], [], []
        tip_cursor: dict[str, int] = {}
        channel_ids = {t: "C0" + _rid(rng, 8) for t in [v["slack"] for v in S.TEAMS.values()] + ["incidents", "random"]}
        issue_seq = {v["jira"]: 100 for v in S.TEAMS.values()}

        def channel_for(system: str) -> str:
            return S.TEAMS[self.systems[system]["team"]]["slack"]

        def new_issue_key(system: str) -> str:
            proj = S.TEAMS[self.systems[system]["team"]]["jira"]
            issue_seq[proj] += 1
            return f"{proj}-{issue_seq[proj]}"

        for p in self.people:
            until = self.active_until(p)
            for system, lam in p.activity.items():
                kind = self.systems[system]["kind"]
                bias = p.source_bias.get(system, {})
                for m in range(MONTHS):
                    lo = self.start + timedelta(days=30 * m)
                    hi = min(lo + timedelta(days=30), until)
                    if hi <= lo:
                        continue
                    frac = (hi - lo).total_seconds() / (30 * 86400)
                    for source, share in SOURCE_MIX[kind].items():
                        n = _poisson(rng, lam * share * SCALE * frac * bias.get(source, 1.0))
                        for _ in range(n):
                            t = self.rand_time(lo, hi)
                            if source == "github" and p.github:
                                self._commit(p, system, t, commits, commit_files)
                            elif source == "slack":
                                self._thread(p, system, t, slack_msgs, channel_ids, channel_for(system), tip_cursor)
                            elif source == "jira":
                                self._issue(p, system, t, jira_issues, new_issue_key(system))
                            elif source == "pagerduty" and system in S.INCIDENT_TITLES:
                                self._incident(p, system, t, incidents)

        # PRs: bundle commits per author+system into pull requests with reviewers.
        by_key: dict[tuple, list] = {}
        for c in commits:
            by_key.setdefault((c["author_login"], c["system"]), []).append(c)
        pr_no = 1000
        login_to_person = {p.github: p for p in self.people if p.github}
        for (login, system), cs in by_key.items():
            cs.sort(key=lambda c: c["committed_at"])
            for i in range(0, len(cs), 3):
                chunk = cs[i:i + 3]
                pr_no += 1
                author = login_to_person[login]
                revs = [q for q, _ in self.experts(system, exclude=author) if q.github and q.status != "left"
                        and datetime.fromisoformat(chunk[-1]["committed_at"].replace("Z", "+00:00")) < self.active_until(q)]
                reviewers = []
                for _ in range(rng.choice([1, 1, 2])):
                    r = self.pick_weighted([(q, q.activity.get(system, 0.1) + 0.2) for q in revs if q not in reviewers])
                    if r:
                        reviewers.append(r)
                if not reviewers:
                    mates = [q for q in self.people if q.team == author.team and q is not author and q.github
                             and q.status != "left"]
                    if mates:
                        reviewers.append(rng.choice(mates))
                merged = chunk[-1]["committed_at"]
                pulls.append({
                    "number": pr_no, "title": chunk[0]["message"].capitalize(), "author_login": login,
                    "created_at": chunk[0]["committed_at"], "merged_at": merged, "state": "merged",
                    "reviewers": ",".join(r.github for r in reviewers), "base_path": f"services/{system}/",
                })
                for c in chunk:
                    c["pr_number"] = pr_no

        self._recurring(jira_issues, new_issue_key)
        self._chatter(slack_msgs, channel_ids)
        docs = self._docs()

        for c in commits:
            c.pop("system", None)
        slack_msgs.sort(key=lambda m: m["ts"])
        jira_issues.sort(key=lambda i: i["created"])
        commits.sort(key=lambda c: c["committed_at"])
        incidents.sort(key=lambda i: i["created_at"])

        return {
            "slack_msgs": slack_msgs, "channel_ids": channel_ids, "jira_issues": jira_issues, "commits": commits,
            "commit_files": commit_files, "pulls": pulls, "incidents": incidents, "docs": docs,
        }

    # ------------------------------------------------------------- per source
    def _commit(self, p: Person, system: str, t: datetime, commits: list, files_out: list) -> None:
        rng = self.rng
        sha = hashlib.sha1(f"{self.seed}{p.github}{system}{t.isoformat()}{rng.random()}".encode()).hexdigest()
        if p.alt_email and rng.random() < 0.4:
            email = p.alt_email
        elif rng.random() < 0.12:
            email = f"{rng.randint(10000, 99999)}+{p.github}@users.noreply.github.com"
        else:
            email = p.work_email
        files = rng.sample(S.FILES.get(system, [f"{system}/main.py"]), k=min(len(S.FILES.get(system, [1])), rng.choice([1, 1, 2, 3])))
        msg = f"{rng.choice(S.COMMIT_VERBS)} {rng.choice(S.COMMIT_OBJECTS)} in {self.systems[system]['aliases'][0]}"
        commits.append({"sha": sha, "author_login": p.github, "author_name": p.name if rng.random() > 0.1 else p.name.split()[0],
                        "author_email": email, "committed_at": _iso(t), "message": msg, "system": system})
        for f in files:
            files_out.append({"sha": sha, "path": f"services/{system}/{f}", "additions": rng.randint(1, 120),
                              "deletions": rng.randint(0, 60)})

    def _thread(self, p: Person, system: str, t: datetime, msgs: list, chans: dict, channel: str, cursor: dict) -> None:
        rng = self.rng
        asker = self.pick_asker(system, p)
        tips = S.TIPS.get(system, [])
        use_tip = tips and rng.random() < 0.45
        if use_tip:
            i = cursor.get(system, 0) % len(tips)
            cursor[system] = i + 1
            q, a = tips[i]
        else:
            alias = rng.choice([self.systems[system]["name"]] + self.systems[system]["aliases"])
            q = rng.choice(S.GENERIC_QUESTIONS).format(system=alias)
            a = rng.choice(S.GENERIC_ANSWERS)
        if rng.random() < 0.3:
            q = f"<@{p.slack_id}> {q}"
        ts = t.timestamp()
        thread_ts = f"{ts:.6f}"
        cid = chans[channel]
        msgs.append({"ts": thread_ts, "thread_ts": thread_ts, "channel": cid, "channel_name": channel,
                     "user": asker.slack_id, "text": q, "created_at": _iso(t), "is_reply": 0,
                     "parent_user": None, "reply_count": 1})
        rt = t + timedelta(minutes=rng.randint(2, 90))
        msgs.append({"ts": f"{rt.timestamp():.6f}", "thread_ts": thread_ts, "channel": cid, "channel_name": channel,
                     "user": p.slack_id, "text": a, "created_at": _iso(rt), "is_reply": 1,
                     "parent_user": asker.slack_id, "reply_count": 0})
        # Sometimes someone else chimes in, which is how backups become visible.
        if rng.random() < 0.18:
            other = self.pick_weighted([(q2, w) for q2, w in self.experts(system, exclude=p)
                                        if q2.status != "left" and q2 is not asker])
            if other:
                ot = rt + timedelta(minutes=rng.randint(1, 60))
                msgs.append({"ts": f"{ot.timestamp():.6f}", "thread_ts": thread_ts, "channel": cid, "channel_name": channel,
                             "user": other.slack_id, "text": rng.choice(["+1", "Same here, that fixed it for me too.",
                                                                          "Adding to the runbook later."]),
                             "created_at": _iso(ot), "is_reply": 1, "parent_user": asker.slack_id, "reply_count": 0})

    def _issue(self, p: Person, system: str, t: datetime, issues: list, key: str) -> None:
        rng = self.rng
        name = self.systems[system]["name"]
        itype = rng.choice(["Bug", "Task", "Task", "Story"])
        summary = rng.choice([f"{name}: {rng.choice(S.COMMIT_OBJECTS)} issue", f"Investigate {name} alert",
                              f"Improve {rng.choice(S.COMMIT_OBJECTS)} for {name}", f"{name} follow-up from review"])
        reporter = self.pick_asker(system, p)
        resolved = t + timedelta(days=rng.randint(1, 21))
        done = resolved < self.now - timedelta(days=1)
        issues.append({
            "key": key, "project": key.split("-")[0], "component": system, "issue_type": itype, "summary": summary,
            "description": f"Raised by {reporter.name.split()[0]}. Context in #{S.TEAMS[self.systems[system]['team']]['slack']}.",
            "status": "Done" if done else rng.choice(["In Progress", "To Do"]), "labels": "",
            "assignee_id": p.jira_id, "reporter_id": reporter.jira_id, "created": _iso(t),
            "updated": _iso(resolved if done else t), "resolved": _iso(resolved) if done else None,
        })

    def _incident(self, p: Person, system: str, t: datetime, incidents: list) -> None:
        rng = self.rng
        dur = rng.randint(8, 240)
        incidents.append({
            "id": "Q" + _rid(rng, 7), "service": system, "title": rng.choice(S.INCIDENT_TITLES[system]),
            "urgency": "high" if self.systems[system]["tier"] == 1 else "low", "status": "resolved",
            "created_at": _iso(t), "resolved_at": _iso(t + timedelta(minutes=dur)), "resolved_by": p.pd_id,
            "escalated": 1 if rng.random() < 0.15 else 0,
        })

    def _recurring(self, issues: list, new_key) -> None:
        for system, title, role in S.RECURRING:
            owner = self.by_role[role]
            for m in range(MONTHS):
                t = self.start + timedelta(days=30 * m + 1)
                if t > self.now:
                    break
                assigned = t < self.active_until(owner)
                done = assigned and t < self.now - timedelta(days=3)
                issues.append({
                    "key": new_key(system), "project": S.TEAMS[self.systems[system]["team"]]["jira"],
                    "component": system, "issue_type": "Task", "summary": f"[Recurring] {title}",
                    "description": "Monthly chore. Steps are in the owner's head, see thread.",
                    "status": "Done" if done else "To Do", "labels": "recurring",
                    "assignee_id": owner.jira_id if assigned else None, "reporter_id": owner.jira_id,
                    "created": _iso(t), "updated": _iso(t + timedelta(days=2)),
                    "resolved": _iso(t + timedelta(days=2)) if done else None,
                })

    def _chatter(self, msgs: list, chans: dict) -> None:
        rng = self.rng
        actives = [p for p in self.people if p.status != "left"]
        for _ in range(400):
            p = rng.choice(actives)
            t = self.rand_time(self.start, self.now)
            ch = rng.choice(list(chans))
            ts = f"{t.timestamp():.6f}"
            msgs.append({"ts": ts, "thread_ts": ts, "channel": chans[ch], "channel_name": ch, "user": p.slack_id,
                         "text": rng.choice(S.CHATTER), "created_at": _iso(t), "is_reply": 0, "parent_user": None,
                         "reply_count": 0})

    def _docs(self) -> list:
        rng = self.rng
        pages = []
        for i, (system, title, kind, role, months_old, body) in enumerate(S.DOCS):
            author = self.by_role[role]
            updated = self.now - timedelta(days=30 * months_old + rng.randint(0, 20))
            created = updated - timedelta(days=rng.randint(30, 300))
            editor = author
            if rng.random() < 0.3:
                mates = [p for p in self.people if p.team == author.team and p.status != "left" and p is not author]
                if mates and updated < self.active_until(author):
                    editor = rng.choice(mates)
            if updated > self.active_until(author):
                updated = self.active_until(author) - timedelta(days=5)
            sysname = self.systems[system]["name"]
            pages.append({
                "id": str(4000 + i), "space": S.TEAMS[self.systems[system]["team"]]["jira"], "title": title,
                "labels": kind, "author_id": author.jira_id, "last_editor_id": editor.jira_id,
                "created_at": _iso(created), "updated_at": _iso(updated),
                "body": f"# {title}\n\nSystem: {sysname}\n\n{body}\n",
            })
        return pages

    # ----------------------------------------------------------------- truth
    def ground_truth(self, generated: dict) -> dict:
        active = [p for p in self.people if p.status != "left"]
        leaving = [p for p in self.people if p.status == "leaving"]
        resource_holders: dict[str, list] = {}
        for role, res, level in S.ACCESS:
            if level in ("admin", "key-holder", "owner"):
                resource_holders.setdefault(res, []).append(role)
        out = {"seed": self.seed, "as_of": self.as_of.isoformat(), "departures": {}, "identities": {},
               "planted_conflicts": [
                   {"system": "ledger-recon", "doc": "Recon alert handling", "doc_says": "silence for 24 hours",
                    "expert_says": "silence for 6 hours, never longer"},
               ],
               "pre_existing_gaps": ["bank-sftp"]}
        for p in self.people:
            out["identities"][p.employee_id] = {"name": p.name, "slack": p.slack_id, "jira": p.jira_id,
                                                "github": p.github, "pagerduty": p.pd_id}
        def effective(q: Person, system: str) -> float:
            """Knowledge as it actually shows up across systems (activity x source mix x bias)."""
            mix = SOURCE_MIX[self.systems[system]["kind"]]
            bias = q.source_bias.get(system, {})
            return q.activity.get(system, 0) * sum(w * bias.get(src, 1.0) for src, w in mix.items())

        for p in leaving:
            areas = []
            for system, a in sorted(p.activity.items(), key=lambda x: -x[1]):
                if a < 0.3:
                    continue
                total = sum(effective(q, system) for q in active)
                share = effective(p, system) / total
                others = [effective(q, system) / total for q in active if q is not p and q.status != "leaving"]
                backup = max(others) if others else 0.0
                res = [r for r, s in S.ACCESS_SYSTEM.items() if s == system]
                exclusive = any(resource_holders.get(r) == [p.role] for r in res)
                if (share >= 0.55 and backup < 0.25) or (exclusive and share >= 0.3):
                    label = "critical"
                elif share >= 0.35 or (backup < 0.25 and share >= 0.25):
                    label = "at_risk"
                else:
                    label = "covered"
                gh_bias = p.source_bias.get(system, {}).get("github", 1.0)
                gh_total = sum(q.activity.get(system, 0) * q.source_bias.get(system, {}).get("github", 1.0) for q in active)
                naive_commit_share = a * gh_bias / gh_total if gh_total else 0
                areas.append({"system": system, "label": label, "share": round(share, 3), "backup": round(backup, 3),
                              "exclusive_access": exclusive,
                              # A commit-only tool would call this critical; the other systems show backups.
                              "decoy": naive_commit_share >= 0.6 and label != "critical",
                              "naive_commit_share": round(naive_commit_share, 3)})
            # Keys and consoles only this person holds, even for systems they never touch.
            seen = {a["system"] for a in areas}
            for res, holders in resource_holders.items():
                system = S.ACCESS_SYSTEM.get(res)
                if holders == [p.role] and system and system not in seen:
                    areas.append({"system": system, "label": "critical", "share": 0.0, "backup": 0.0,
                                  "exclusive_access": True, "decoy": False, "naive_commit_share": 0.0,
                                  "reason": f"only holder of {res}"})
                    seen.add(system)
            out["departures"][p.employee_id] = {"name": p.name, "last_day": p.last_day.isoformat(), "areas": areas}
        return out


def seed_salt(seed: int) -> str:
    return f"acme-{seed}-"


# ---------------------------------------------------------------------- write
def write(seed: int = 42, out_dir: str | Path = "data", as_of: date | None = None) -> Path:
    co = Company(seed, as_of)
    g = co.generate()
    root = Path(out_dir) / f"seed-{seed}"
    for sub in ("hr", "slack", "jira", "github", "docs", "pagerduty"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    def dump(rel: str, obj) -> None:
        (root / rel).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    rng = random.Random(seed * 7 + 1)
    # HR: the full table holds sensitive columns that must never reach an agent.
    employees = []
    for p in co.people:
        mgr = next((q for q in co.people if q.team == p.team and q.role.endswith("-em")), None) or \
              next((q for q in co.people if q.team == p.team and q.senior and q is not p), None)
        employees.append({
            "employee_id": p.employee_id, "full_name": p.name, "preferred_name": p.name.split()[0],
            "work_email": p.work_email, "title": p.title, "team": S.TEAMS[p.team]["name"], "team_id": p.team,
            "manager_id": mgr.employee_id if mgr and mgr is not p else None,
            "employment_type": "contractor" if p.contractor else "employee", "status": p.status,
            "start_date": p.start_date.isoformat(), "last_day": p.last_day.isoformat() if p.last_day else None,
            "location": rng.choice(["Bengaluru", "Pune", "Remote", "Singapore", "Berlin"]),
            # sensitive (blocked by governance)
            "salary_band": rng.choice(["L3", "L4", "L5", "L6", "L7"]),
            "personal_email": f"{_slug(p.name)}{rng.randint(1, 99)}@mail.example",
            "home_city": rng.choice(["Indiranagar", "Koramangala", "Baner", "Kreuzberg", "Tampines"]),
            "performance_rating": rng.choice(["meets", "exceeds", "strong"]),
        })
    departures = [{"employee_id": p.employee_id, "notice_date": (p.last_day - timedelta(days=30)).isoformat(),
                   "last_day": p.last_day.isoformat(),
                   "reason_category": rng.choice(["resignation", "relocation", "internal transfer"]) if p.status == "leaving" else "resignation",
                   "backfill_status": "open" if p.status == "leaving" else "closed"}
                  for p in co.people if p.status in ("leaving", "left")]
    grants = []
    for role, res, level in S.ACCESS:
        p = co.by_role[role]
        grants.append({"employee_id": p.employee_id, "resource": res, "level": level,
                       "granted_at": (co.start - timedelta(days=rng.randint(10, 400))).date().isoformat()})
    alumnus = co.by_role["payments-alumnus"]
    grants.append({"employee_id": alumnus.employee_id, "resource": "unity-bank-sftp-keys", "level": "revoked",
                   "granted_at": (co.start - timedelta(days=500)).date().isoformat()})
    dump("hr/employees.json", {"employees": employees})
    dump("hr/departures.json", {"departures": departures})
    dump("hr/access_grants.json", {"access_grants": grants})
    (root / "hr" / "hr.sql").write_text(_hr_sql(employees, departures, grants), encoding="utf-8")

    # Slack
    members = []
    for p in co.people:
        hide = p.hide_slack_email or (co.seed != 42 and rng.random() < 0.2)
        members.append({"id": p.slack_id, "name": p.slack_handle, "real_name": p.name if rng.random() > 0.15 or p.role == "payments-eng-2" else p.name.split()[0],
                        "display_name": p.slack_display, "email": None if hide else p.work_email,
                        "deleted": 1 if p.status == "left" else 0, "tz": "Asia/Kolkata", "title": p.title})
    dump("slack/users.json", {"ok": True, "members": members})
    dump("slack/channels.json", {"ok": True, "channels": [{"id": cid, "name": name, "is_archived": 0}
                                                          for name, cid in g["channel_ids"].items()]})
    dump("slack/messages.json", {"ok": True, "messages": g["slack_msgs"]})

    # Jira (Atlassian accounts hide most emails)
    jusers = [{"account_id": p.jira_id, "display_name": p.jira_name, "active": 0 if p.status == "left" else 1,
               "email": p.work_email if rng.random() < 0.3 else None, "time_zone": "Asia/Kolkata"} for p in co.people]
    dump("jira/users.json", {"values": jusers})
    dump("jira/issues.json", {"total": len(g["jira_issues"]), "issues": g["jira_issues"]})

    # GitHub
    gusers = [{"login": p.github, "name": p.name if rng.random() > 0.3 else None, "type": "User"}
              for p in co.people if p.github]
    gusers += [{"login": "dependabot", "name": None, "type": "Bot"}, {"login": "acme-ci-bot", "name": "CI Bot", "type": "Bot"}]
    dump("github/users.json", {"items": gusers})
    dump("github/commits.json", {"total_count": len(g["commits"]), "items": g["commits"]})
    dump("github/commit_files.json", {"items": g["commit_files"]})
    dump("github/pulls.json", {"items": g["pulls"]})
    catalog = [{"system_id": s["id"], "name": s["name"], "kind": s["kind"], "owner_team": S.TEAMS[s["team"]]["name"],
                "tier": s["tier"], "repo_path": f"services/{s['id']}/" if s["kind"] != "customer" else None,
                "slack_channel": S.TEAMS[s["team"]]["slack"], "jira_component": s["id"],
                "pagerduty_service": s["id"] if s["id"] in S.INCIDENT_TITLES else None,
                "aliases": ",".join(s["aliases"]), "description": s["description"]}
               for s in co.systems.values()]
    dump("github/catalog.json", {"items": catalog})

    # Docs
    for page in g["docs"]:
        (root / "docs" / f"{page['id']}.md").write_text(page["body"], encoding="utf-8")
    dump("docs/pages.json", {"results": g["docs"]})

    # PagerDuty
    pd_users = [{"id": p.pd_id, "name": p.name, "email": p.work_email, "role": "user"}
                for p in co.people if any(co.systems[s]["kind"] == "system" for s in p.activity)]
    dump("pagerduty/users.json", {"users": pd_users})
    dump("pagerduty/incidents.json", {"incidents": g["incidents"]})

    truth = co.ground_truth(g)
    dump("_ground_truth.json", truth)
    meta = {"seed": seed, "as_of": co.as_of.isoformat(), "company": "Acme Pay (fictional)",
            "generated_at": _iso(datetime.now(timezone.utc)),
            "counts": {"employees": len(employees), "slack_messages": len(g["slack_msgs"]), "jira_issues": len(g["jira_issues"]),
                       "commits": len(g["commits"]), "pull_requests": len(g["pulls"]), "docs": len(g["docs"]),
                       "incidents": len(g["incidents"])}}
    dump("meta.json", meta)
    return root


def _sql_lit(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def _hr_sql(employees: list, departures: list, grants: list) -> str:
    lines = [
        "-- Acme Pay HR system (fictional). Loaded into Postgres; Zetaris registers it as datasource hr_pg.",
        "-- The employees table holds sensitive columns. Zetaris exposes only the employees_directory view.",
        "DROP TABLE IF EXISTS access_grants; DROP TABLE IF EXISTS departures; DROP TABLE IF EXISTS employees;",
        "CREATE TABLE employees (employee_id VARCHAR(16) PRIMARY KEY, full_name VARCHAR(120) NOT NULL, "
        "preferred_name VARCHAR(60), work_email VARCHAR(160), title VARCHAR(120), team VARCHAR(60), team_id VARCHAR(30), "
        "manager_id VARCHAR(16), employment_type VARCHAR(20), status VARCHAR(20), start_date DATE, last_day DATE, "
        "location VARCHAR(60), salary_band VARCHAR(8), personal_email VARCHAR(160), home_city VARCHAR(60), "
        "performance_rating VARCHAR(20));",
        "CREATE TABLE departures (employee_id VARCHAR(16) REFERENCES employees(employee_id), notice_date DATE, "
        "last_day DATE, reason_category VARCHAR(40), backfill_status VARCHAR(20));",
        "CREATE TABLE access_grants (employee_id VARCHAR(16) REFERENCES employees(employee_id), resource VARCHAR(80), "
        "level VARCHAR(20), granted_at DATE);",
    ]
    cols = list(employees[0].keys())
    for e in employees:
        lines.append(f"INSERT INTO employees ({', '.join(cols)}) VALUES ({', '.join(_sql_lit(e[c]) for c in cols)});")
    for d in departures:
        lines.append("INSERT INTO departures (employee_id, notice_date, last_day, reason_category, backfill_status) VALUES "
                     f"({', '.join(_sql_lit(d[c]) for c in ['employee_id', 'notice_date', 'last_day', 'reason_category', 'backfill_status'])});")
    for g in grants:
        lines.append("INSERT INTO access_grants (employee_id, resource, level, granted_at) VALUES "
                     f"({', '.join(_sql_lit(g[c]) for c in ['employee_id', 'resource', 'level', 'granted_at'])});")
    lines.append("-- Governed view: what Zetaris (and therefore every agent) is allowed to see.")
    lines.append("CREATE OR REPLACE VIEW employees_directory AS SELECT employee_id, full_name, preferred_name, work_email, "
                 "title, team, team_id, manager_id, employment_type, status, start_date, last_day, location FROM employees;")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import sys
    print(write(int(sys.argv[1]) if len(sys.argv) > 1 else 42))
