"""Successor scout: who should take each area over, and why.

Candidates are active employees who are not leaving. The score blends:
  0.55 direct knowledge of the area (their share of its evidence)
  0.20 on the owning team, or knows its neighbouring systems
  0.12 how often the departing person answered their questions about it
       (they already learned from them; the handover is half done)
  0.13 headroom: fewer open tickets is better
Every recommendation lists the reasons with numbers, so a manager can disagree.
"""
from __future__ import annotations

from collections import Counter

from ..federation.base import lit
from .blackboard import Blackboard
from .investigators import Investigators


class SuccessorScout:
    name = "Successor scout"

    def run(self, bb: Blackboard, inv: Investigators) -> None:
        target = bb.target["employee_id"]
        open_load = self._open_load(bb, inv)
        for a in bb.areas.values():
            if a.label == "covered":
                continue
            team_systems = [s for s, m in bb.systems.items() if m.get("owner_team") == a.team and s != a.system]
            helped = Counter(inv.owner("slack", t.get("asker_account")) for t in inv.threads.get(a.system, [])
                             if inv.owner("slack", t.get("answer_account")) == target)
            helped.pop("?", None)
            helped.pop(target, None)
            max_help = max(helped.values(), default=0) or 1
            pw = inv.person_weights(a.system)
            total = sum(sum(v.values()) for v in pw.values()) or 1.0
            team_w = {s: inv.person_weights(s) for s in team_systems}
            cands = []
            for eid, row in bb.directory.items():
                if eid == target or eid in bb.leaving or row.get("status") != "active":
                    continue
                direct = sum(pw.get(eid, {}).values()) / total
                adj = 0.0
                for s in team_systems:
                    tot = sum(sum(v.values()) for v in team_w[s].values())
                    if tot:
                        adj = max(adj, sum(team_w[s].get(eid, {}).values()) / tot)
                same_team = (row.get("team") or "").lower() == (a.team or "").lower()
                help_score = helped.get(eid, 0) / max_help
                load = open_load.get(eid, 0)
                headroom = 1.0 / (1.0 + load / 6)
                owning_team = (bb.systems.get(a.system, {}).get("owner_team") or "").lower() == (row.get("team") or "").lower()
                score = (0.55 * min(1, direct * 2.5) + 0.2 * min(1, adj * 2 + (0.5 if owning_team else 0))
                         + 0.12 * help_score + 0.13 * headroom)
                if score < 0.12:
                    continue
                reasons = []
                if direct > 0.02:
                    reasons.append(f"{direct:.0%} of the {a.name} activity")
                if helped.get(eid):
                    reasons.append(f"{bb.person_name(target).split()[0]} answered their {a.name} questions "
                                   f"{helped[eid]} time{'s' if helped[eid] != 1 else ''}")
                if same_team:
                    reasons.append(f"on the owning team ({a.team})")
                if adj > 0.1:
                    reasons.append("works on neighbouring systems")
                reasons.append(f"{load} open ticket{'s' if load != 1 else ''}")
                cands.append({"person": eid, "name": row["full_name"], "title": row.get("title"), "score": round(score, 3),
                              "reasons": reasons})
            cands.sort(key=lambda c: -c["score"])
            a.successors = cands[:3]
            if cands:
                bb.emit(self.name, "successor", f"{a.name}: {cands[0]['name']} ({'; '.join(cands[0]['reasons'][:2])})",
                        system=a.system, top=cands[:3])

    def _open_load(self, bb: Blackboard, inv: Investigators) -> dict:
        if "work" not in bb.probes_available:
            return {}
        r = bb.sql(self.name, "Current open tickets per person (load)",
                   "SELECT assignee_id AS account, COUNT(*) AS n FROM jira.issues WHERE status <> 'Done' "
                   f"AND assignee_id IS NOT NULL AND created >= {lit(inv.cut)} GROUP BY assignee_id", numeric=("n",))
        out: dict = Counter()
        for row in (r.rows if r else []):
            p = inv.owner("jira", row["account"])
            if p != "?":
                out[p] += row["n"]
        return out
