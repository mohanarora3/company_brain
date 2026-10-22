"""Risk officer: business priority, deadlines and escalation.

The Critic judges whether a label is supported. The Risk officer judges what
it means for the business: tier of the system, days until the last day,
chores that will silently stop, keys nobody else holds. It escalates what
cannot wait, and it pushes back on the Critic in one case: a downgrade on
knowledge grounds does not cover exclusive access. Knowledge can be shared
with a backup; a key cannot be used by someone who does not have it.
"""
from __future__ import annotations

from .analyst import days_left
from .blackboard import Blackboard

LABEL_W = {"critical": 1.0, "at_risk": 0.6, "covered": 0.12}
TIER_W = {1: 1.0, 2: 0.72, 3: 0.45}


class RiskOfficer:
    name = "Risk officer"

    def assess(self, bb: Blackboard) -> None:
        dl = days_left(bb)
        urgency = 1.0 if dl <= 14 else 0.85 if dl <= 30 else 0.7
        for a in bb.areas.values():
            stops = [c for c in a.chores if c["state"] == "stops when they leave"]
            exclusive = [x for x in a.exclusive_access if x.get("exclusive")]
            if exclusive and a.label == "covered":
                a.label = "critical"
                a.reason = (a.reason + "; " if a.reason else "") + f"exclusive access: {', '.join(x['resource'] for x in exclusive)}"
                a.history.append({"round": bb.round, "stage": "risk:override",
                                  "notes": [f"Critic's knowledge-based label overridden: {a.name} has access only "
                                            f"{bb.person_name(bb.target['employee_id'])} holds"]})
                bb.emit(self.name, "challenge", f"{a.name}: knowledge is covered, but nobody else holds "
                        f"{', '.join(x['resource'] for x in exclusive)}. Keeping it critical.", system=a.system)
            a.priority = round(LABEL_W.get(a.label, 0.1) * TIER_W.get(a.tier, 0.6) * urgency
                               + (0.15 if stops else 0) + (0.1 if exclusive else 0)
                               - (0.1 if a.doc_coverage >= 0.8 else 0), 3)
            if a.label == "critical" and (a.tier == 1 or exclusive) and dl <= 21 and not a.escalated:
                a.escalated = True
                actions = []
                if exclusive:
                    actions.append(f"transfer {', '.join(x['resource'] for x in exclusive)} this week")
                if stops:
                    actions.append(f"reassign {len(stops)} recurring chore(s): " + "; ".join(c['summary'] for c in stops))
                if a.doc_coverage < 0.5:
                    actions.append("schedule a recorded walkthrough; no current runbook exists")
                actions.append("book the exit-interview questions for this area first")
                esc = {"system": a.system, "name": a.name, "tier": a.tier, "days_left": dl, "share": a.share,
                       "backup": a.backup, "actions": actions}
                bb.escalations.append(esc)
                bb.emit(self.name, "escalation", f"Escalate {a.name}: tier {a.tier}, {dl} days left, "
                        f"{a.share:.0%} of the knowledge, best backup {a.backup:.0%}", **esc)
        pre = [a for a in bb.areas.values() if any(c["state"] == "already orphaned" for c in a.chores)]
        for a in pre:
            bb.emit(self.name, "pre_existing_gap", f"{a.name}: a recurring chore has had no owner for months "
                    "(knowledge already lost before this departure)", system=a.system,
                    chores=[c for c in a.chores if c["state"] == "already orphaned"])
