"""Analyst: turns evidence weights into knowledge areas with a risk label.

For every candidate system it computes the departing person's share of the
evidence-weighted knowledge, the strongest remaining backup, and which sources
the numbers rest on. Labels use explicit, documented thresholds:

  critical  share >= 0.55 and best backup < 0.25, or exclusive access with share >= 0.30,
            or exclusive access to a system they barely touch (keys nobody else holds)
  at_risk   share >= 0.35, or no backup >= 0.25 and share >= 0.25
  covered   otherwise

Evidence from people who are also leaving counts toward the total but never
as a backup. Activity from accounts nobody could attribute counts toward the
total too, which is why the Critic pushes on unresolved identities.
"""
from __future__ import annotations

from datetime import date, timedelta

from .blackboard import Area, Blackboard
from .investigators import Investigators

CRIT_SHARE, CRIT_BACKUP, EXCL_SHARE = 0.55, 0.25, 0.30
RISK_SHARE, RISK_SHARE_NOBACKUP = 0.35, 0.25


def label_for(share: float, backup: float, exclusive: bool) -> str:
    if (share >= CRIT_SHARE and backup < CRIT_BACKUP) or (exclusive and share >= EXCL_SHARE):
        return "critical"
    if share >= RISK_SHARE or (backup < CRIT_BACKUP and share >= RISK_SHARE_NOBACKUP):
        return "at_risk"
    return "covered"


class Analyst:
    name = "Analyst"

    def score(self, bb: Blackboard, inv: Investigators, systems: list[str], stage: str) -> list[Area]:
        target = bb.target["employee_id"]
        stale_cut = (bb.as_of - timedelta(days=270)).isoformat()
        changed = []
        for sid in systems:
            meta = bb.systems.get(sid, {"name": sid, "kind": "system", "tier": 2, "owner_team": ""})
            area = bb.areas.get(sid) or Area(sid, meta.get("name", sid), meta.get("kind", "system"), int(meta.get("tier") or 2),
                                             meta.get("owner_team", ""))
            people = inv.person_weights(sid)
            last_map = inv.last_at(sid)
            by_source: dict = {}
            total = 0.0
            per_person: dict[str, float] = {}
            for p, srcs in people.items():
                if p != "?" and bb.directory.get(p, {}).get("status") == "left":
                    continue  # knowledge that already walked out is not part of what the company still has
                for src, w in srcs.items():
                    total += w
                    per_person[p] = per_person.get(p, 0.0) + w
                    slot = by_source.setdefault(src, {"target": 0.0, "others": 0.0, "unattributed": 0.0})
                    key = "target" if p == target else "unattributed" if p == "?" else "others"
                    slot[key] += w
            tw = per_person.get(target, 0.0)
            backups = []
            for p, w in per_person.items():
                if p in ("?", target) or p in bb.leaving or bb.directory.get(p, {}).get("status") != "active":
                    continue
                last = last_map.get(p, "")
                stale = bool(last) and last < stale_cut
                backups.append({"person": p, "name": bb.person_name(p), "share": round(w / total, 3) if total else 0.0,
                                "last_at": last, "stale": stale,
                                "sources": sorted(s for s, v in people.get(p, {}).items() if v > 0)})
            backups.sort(key=lambda b: -b["share"])
            share = tw / total if total else 0.0
            # A backup who has not touched the system in 9 months is only half a backup.
            backup = 0.0
            if backups:
                b0 = backups[0]
                backup = b0["share"] * (0.5 if b0["stale"] else 1.0)
            exclusive = [a for a in area.exclusive_access if a.get("exclusive")]
            label = label_for(share, backup, bool(exclusive))
            if exclusive and label != "critical":
                # Knowledge can be shared; a key nobody else holds cannot.
                label = "critical"
                area.reason = f"only holder of {', '.join(a['resource'] for a in exclusive)}"
            unattributed = sum(v["unattributed"] for v in by_source.values())
            area.share, area.backup, area.backups = round(share, 3), round(backup, 3), backups[:5]
            area.by_source = {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in by_source.items()}
            area.sources_used = sorted(k for k, v in by_source.items() if v["target"] + v["others"] + v["unattributed"] > 0)
            area.footprint = bb.outputs.get("footprint", {}).get(sid, area.footprint)
            area.evidence_ids = sorted(e.id for e in bb.evidence.values() if e.system == sid and (e.person == target or e.kind in ("chore", "access")))
            target_sources = [k for k, v in by_source.items() if v["target"] > 0]
            conf = 0.35 + 0.15 * min(3, len(target_sources)) + (0.1 if total > 10 else 0)
            if unattributed / total > 0.1 if total else False:
                conf -= 0.15
            for s in bb.failed_sources:
                if s in ("slack", "jira", "github", "pagerduty"):
                    conf -= 0.1
            area.confidence = round(max(0.1, min(0.95, conf)), 2)
            area.unattributed = round(unattributed / total, 3) if total else 0.0  # type: ignore[attr-defined]
            if stage == "provisional":
                area.provisional_label = label
            prev = area.label
            area.label = label
            area.history.append({"round": bb.round, "stage": stage, "label": label, "share": area.share,
                                 "backup": area.backup, "sources": area.sources_used})
            bb.areas[sid] = area
            if prev != label:
                changed.append(area)
        if stage == "init":
            return changed
        counts = {l: sum(1 for a in bb.areas.values() if a.label == l) for l in ("critical", "at_risk", "covered")}
        bb.emit(self.name, "scores", f"{stage} scores for {len(systems)} systems: "
                + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items()),
                areas=[{"system": a.system, "name": a.name, "tier": a.tier, "label": a.label, "share": a.share, "backup": a.backup,
                        "sources": a.sources_used} for a in bb.areas.values() if a.system in systems])
        return changed


def days_left(bb: Blackboard) -> int:
    ld = bb.target.get("last_day")
    if not ld:
        return 999
    return (date.fromisoformat(str(ld)[:10]) - bb.as_of).days
