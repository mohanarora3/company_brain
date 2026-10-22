"""Planner: decides what to investigate next, from the source map and the open requests.

It never runs queries itself. Round 1 is always a footprint sweep of the
departing person across every source the Cartographer found. After that, the
Planner turns other agents' requests into tasks and delegates them:

  corroborate -> conversation, incident and docs probes for those systems
  identity    -> the Resolver disambiguates the account by co-activity
  retry_source-> drop cached results for that source and re-run its probes
  tacit       -> extract the actual answers the person gave on that system

Requests that cannot be served (a probe with no source behind it) are dropped
with a reason, so the run always terminates.
"""
from __future__ import annotations

from .blackboard import Blackboard

FOOTPRINT_MIN = 2.0


class Planner:
    name = "Planner"

    def initial(self, bb: Blackboard, prior: dict) -> None:
        probes = sorted(bb.probes_available)
        steps = [
            f"Footprint: find every system {bb.target['full_name']} shows up in across {len(probes)} probes",
            "Ownership: who else works on those systems, from systems of record (commits, reviews, tickets)",
            "Critique: the Critic decides which labels need corroboration before anyone acts on them",
            "Corroboration: conversation, incidents and docs only where the Critic asked",
            "Risk and successors, then the handover plan and exit interview",
        ]
        if prior:
            steps.insert(0, f"Memory: H-MEM already holds interview answers for {', '.join(sorted(prior))}; count them as written knowledge")
        bb.outputs["plan"] = steps
        bb.emit(self.name, "plan", f"Plan for {bb.target['full_name']} ({len(steps)} steps)", steps=steps, probes=probes)

    def candidates(self, bb: Blackboard, footprint: dict, access: list, prior: dict) -> list[str]:
        totals = {s: sum(v.values()) for s, v in footprint.items()}
        grand = sum(totals.values()) or 1.0
        picked = [s for s, w in totals.items() if s in bb.systems and (w >= FOOTPRINT_MIN and w / grand >= 0.02)]
        for x in access:
            if x.get("system") and x["system"] not in picked:
                picked.append(x["system"])
        for s in prior:
            if s in bb.systems and s not in picked:
                picked.append(s)
        skipped = sorted((s for s in totals if s not in picked), key=lambda s: -totals[s])
        bb.emit(self.name, "candidates", f"{len(picked)} candidate systems; {len(skipped)} with only incidental activity skipped",
                candidates={s: round(totals.get(s, 0), 1) for s in picked},
                skipped={s: round(totals[s], 1) for s in skipped[:8]},
                via_access=[x["system"] for x in access if x.get("system")])
        return sorted(picked, key=lambda s: -totals.get(s, 0))

    def tasks(self, bb: Blackboard) -> dict:
        """Group open requests into delegated work for the next round."""
        out = {"corroborate": [], "identity": [], "retry_source": [], "tacit": []}
        for r in bb.open_requests():
            if r.kind in out:
                out[r.kind].append(r)
            else:
                r.status = "dropped"
        if any(out.values()):
            desc = []
            if out["corroborate"]:
                desc.append(f"corroborate {len(out['corroborate'])} areas with conversation/incident/docs probes")
            if out["identity"]:
                desc.append(f"Resolver: disambiguate {len({(r.payload['source'], r.payload['account']) for r in out['identity']})} accounts")
            if out["retry_source"]:
                desc.append("retry " + ", ".join(r.payload["source"] for r in out["retry_source"]))
            if out["tacit"]:
                desc.append(f"extract tacit knowledge for {len(out['tacit'])} areas")
            bb.emit(self.name, "delegate", "Round {}: ".format(bb.round + 1) + "; ".join(desc),
                    tasks={k: [r.id for r in v] for k, v in out.items() if v})
        return out
