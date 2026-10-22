"""Critic: refuses to let a label stand on thin or one-sided evidence.

It reviews every area after each scoring pass and either accepts it or sends
work back through the blackboard. Its rules are written down so a human can
argue with them:

  1. Systems-of-record bias. Commits and tickets alone over-credit whoever
     types the code. If an area is critical or at risk on that basis, or the
     person's own footprint there is mostly conversation or incidents, ask for
     corroboration from conversation, incident and docs evidence before
     accepting.
  2. Unresolved identities. If more than 5% of an area's activity comes from
     accounts nobody could attribute, ask the Resolver to disambiguate them.
  3. Missing sources. If a source failed, ask for one retry; if it fails again,
     accept with lowered confidence and say which evidence is missing.
  4. Critical areas need the actual knowledge, not just a number: ask for the
     tacit answers to be extracted before the handover is written.
  5. When a label changes between passes, record why (which source showed the
     backups), so the downgrade or upgrade is explainable.
  6. Every claim in the written handover must cite evidence that exists.
"""
from __future__ import annotations

from .blackboard import Area, Blackboard

CONVERSATIONAL = {"slack", "pagerduty"}


class Critic:
    name = "Critic"

    def review(self, bb: Blackboard, stage: str) -> int:
        """Returns the number of new requests raised."""
        raised = 0
        for area in sorted(bb.areas.values(), key=lambda a: a.system):
            notes = []
            fp = area.footprint or {}
            fp_total = sum(fp.values()) or 1.0
            conv_share = sum(v for k, v in fp.items() if k in CONVERSATIONAL) / fp_total
            used_conv = any(s in area.sources_used for s in CONVERSATIONAL)

            if stage == "provisional":
                if area.label in ("critical", "at_risk") or conv_share >= 0.35:
                    why = (f"{area.label.replace('_', ' ')} on commits and tickets alone" if area.label != "covered"
                           else f"{conv_share:.0%} of their footprint here is conversation, which this pass did not count")
                    bb.request(self.name, "corroborate", area.system, why)
                    raised += 1
                    notes.append(f"needs corroboration: {why}")
                else:
                    area.status = "accepted"
                    notes.append("covered on systems of record and no conversational footprint; accepted without further queries")
            elif area.status == "accepted" and area.label == "covered" and area.system not in {r.system for r in bb.requests}:
                continue
            else:
                first = next((h for h in area.history if h["stage"] == "provisional"), None)
                if first and first["label"] != area.label:
                    better = [b for b in area.backups[:2] if b["share"] >= 0.15]
                    who = ", ".join(f"{b['name']} ({b['share']:.0%}, via {'/'.join(b['sources'])})" for b in better) or "nobody"
                    if _rank(area.label) < _rank(first["label"]):
                        area.status = "downgraded"
                        notes.append(f"downgraded from {_words(first['label'])} to {_words(area.label)}: conversation and incident data show backups: {who}")
                    else:
                        area.status = "upgraded"
                        notes.append(f"upgraded from {_words(first['label'])} to {_words(area.label)}: the extra sources show nobody else answering")
                elif area.status not in ("downgraded", "upgraded"):
                    area.status = "verified"
                    notes.append(f"label holds across {len(area.sources_used)} sources: {', '.join(area.sources_used)}")
                unattributed = getattr(area, "unattributed", 0.0)
                if unattributed > 0.05 and area.label != "covered":
                    for f in bb.findings:
                        if f["kind"] == "identity_ambiguous" and not f.get("resolved"):
                            bb.request(self.name, "identity", area.system,
                                       f"{unattributed:.0%} of activity on {area.name} is from unattributed accounts",
                                       source=f["source"], account=f["account"])
                            raised += 1
                for src, err in bb.failed_sources.items():
                    if src in ("slack", "jira", "github", "pagerduty", "docs"):
                        tried = [r for r in bb.requests if r.kind == "retry_source" and r.payload.get("source") == src]
                        if not tried:
                            bb.request(self.name, "retry_source", "", f"{src} failed: {err[:80]}", source=src)
                            raised += 1
                        else:
                            notes.append(f"{src} unavailable: confidence lowered, evidence from {src} missing")
                if area.label == "critical" and not area.tacit and area.kind != "customer" and area.share >= 0.2:
                    if not any(r.kind == "tacit" and r.system == area.system for r in bb.requests):
                        bb.request(self.name, "tacit", area.system, "extract what they actually know before the handover")
                        raised += 1
                if area.label == "critical" and area.kind == "customer" and not area.tacit:
                    if not any(r.kind == "tacit" and r.system == area.system for r in bb.requests):
                        bb.request(self.name, "tacit", area.system, "customer relationship knowledge lives in conversation")
                        raised += 1
            last = next((h for h in reversed(area.history) if h.get("stage", "").startswith("critic:")), None)
            if notes and (not last or last.get("notes") != notes):
                area.history.append({"round": bb.round, "stage": f"critic:{stage}", "notes": notes})
                bb.emit(self.name, "verdict", f"{area.name}: {notes[0]}", system=area.system, label=area.label,
                        status=area.status, notes=notes)
        return raised

    def check_citations(self, bb: Blackboard, handover: dict) -> list[str]:
        """Rule 6: every section must cite evidence ids that exist on the blackboard."""
        problems = []
        for sec in handover.get("areas", []):
            cites = sec.get("citations", [])
            missing = [c for c in cites if c not in bb.evidence]
            if not cites:
                problems.append(f"{sec.get('system')}: no citations")
            elif missing:
                problems.append(f"{sec.get('system')}: unknown evidence {missing[:3]}")
        bb.emit(self.name, "citations", "Handover citations verified" if not problems else
                f"Handover has {len(problems)} citation problems", problems=problems)
        return problems


def _words(label: str) -> str:
    return label.replace("_", " ")


def _rank(label: str) -> int:
    return {"covered": 0, "at_risk": 1, "critical": 2}.get(label, 0)
