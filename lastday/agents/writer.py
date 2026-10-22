"""Writer: the handover plan and the exit interview, in words people can use.

Both are built from the blackboard, area by area, and every section carries
citations (evidence ids, which map back to the SQL that found them). With an
LLM configured, the summaries and questions are rewritten for readability; the
Critic then checks the citations survived, and falls back to the template text
if they did not. Without an LLM the templates are the output.
"""
from __future__ import annotations

from datetime import date

from ..llm.client import LLMError, get_llm
from .analyst import days_left
from .blackboard import Area, Blackboard

SYSTEM = ("You write handover notes for engineering managers. Plain, specific sentences. Keep every number and "
          "name you are given. Never invent facts. Keep the [cite:...] markers exactly where they are relevant.")


def _pct(x: float) -> str:
    return f"{x:.0%}"


def _short_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d %b %Y")
    except ValueError:
        return str(iso)[:10]


class Writer:
    name = "Writer"

    def handover(self, bb: Blackboard) -> dict:
        t = bb.target
        first = t["full_name"].split()[0]
        dl = days_left(bb)
        sections = []
        for a in sorted(bb.areas.values(), key=lambda x: -x.priority):
            if a.label == "covered":
                continue
            sections.append(self._section(bb, a, first))
        covered = [{"system": a.system, "name": a.name, "share": a.share, "backup": a.backup,
                    "backups": [b["name"] for b in a.backups[:2]], "status": a.status}
                   for a in bb.areas.values() if a.label == "covered"]
        headline = (f"{t['full_name']} leaves in {dl} days ({_short_date(t.get('last_day'))}). "
                    f"{sum(1 for s in sections if s['label'] == 'critical')} critical and "
                    f"{sum(1 for s in sections if s['label'] == 'at_risk')} at-risk areas need a handover; "
                    f"{len(covered)} areas are already covered by others.")
        doc = {"title": f"Handover plan: {t['full_name']}", "headline": headline, "days_left": dl,
               "last_day": t.get("last_day"), "areas": sections, "covered": covered,
               "escalations": bb.escalations, "llm": get_llm().label}
        self._polish(bb, doc)
        doc["markdown"] = self.markdown(bb, doc)
        return doc

    def _section(self, bb: Blackboard, a: Area, first: str) -> dict:
        cites = list(a.evidence_ids[:12])
        backups = ", ".join(f"{b['name']} {_pct(b['share'])}" + (" (stale)" if b["stale"] else "") for b in a.backups[:3]) or "nobody"
        src_list = ", ".join(a.sources_used)
        excl = [x for x in a.exclusive_access if x.get("exclusive")]
        if excl and a.share < 0.2:
            why = (f"{first} barely works on {a.name} (tier {a.tier}), but is the only person holding "
                   f"{', '.join(x['resource'] for x in excl)}. If that is not transferred, nobody can operate it after "
                   f"{_short_date(bb.target.get('last_day'))}. Current knowledge: {backups}.")
        else:
            why = (f"{first} holds {_pct(a.share)} of the evidence-weighted knowledge of {a.name} (tier {a.tier}); "
                   f"the strongest remaining person holds {_pct(a.backup)}. Backups: {backups}. Sources: {src_list}.")
        if a.reason:
            why += f" {a.reason[0].upper() + a.reason[1:]}."
        knows = [{"text": x["text"], "context": f"asked by {x['asker']} in #{x['channel']} on {_short_date(x['at'])}",
                  "cite": x["evidence"], "memory_id": x.get("memory_id")} for x in a.tacit]
        cites += [k["cite"] for k in knows]
        chores = [c for c in a.chores if c["state"] in ("stops when they leave", "already orphaned")]
        cites += [f"jira:chore:{c['issue_key']}" for c in chores if f"jira:chore:{c['issue_key']}" in bb.evidence]
        access = [x for x in a.exclusive_access if x.get("exclusive")]
        cites += [f"hr_pg:access:{x['resource']}" for x in access if f"hr_pg:access:{x['resource']}" in bb.evidence]
        docs_fix = []
        for d in a.docs:
            if d["age_days"] > 365 or d["author_status"] != "active":
                docs_fix.append({"page_id": d["page_id"], "title": d["title"],
                                 "issue": f"last updated {d['age_days'] // 30} months ago" + (
                                     f"; author {d['author']} has {'left' if d['author_status'] == 'left' else 'notice'}"
                                     if d["author_status"] != "active" else "")})
        for c in a.conflicts:
            docs_fix.append({"page_id": c["doc_source"].split(":")[-1], "title": c.get("doc_title", c["doc_source"]),
                             "issue": f"says \"{c['doc_claim']}\" but {first} told the team \"{c['expert_claim']}\""})
        has_runbook = any(d["kind"] == "runbook" and d["age_days"] <= 365 for d in a.docs)
        succ = a.successors[0] if a.successors else None
        checklist = []
        if succ:
            checklist.append(f"Pair {succ['name']} with {first} on {a.name} for the next {min(10, max(2, days_left(bb) - 2))} working days")
        for x in access:
            checklist.append(f"Transfer {x['resource']} ({x['level']}) to {succ['name'] if succ else 'a successor'}; nobody else holds it")
        for c in chores:
            if c["state"] == "stops when they leave":
                checklist.append(f"Reassign recurring chore '{c['summary']}' ({c['issue_key']})")
            else:
                checklist.append(f"Find an owner for '{c['summary']}': unowned since {c['owner']} left")
        if not has_runbook and a.kind != "customer":
            checklist.append(f"Write the {a.name} runbook from the tacit answers below, reviewed by {first}")
        for d in docs_fix:
            checklist.append(f"Fix wiki page '{d['title']}': {d['issue']}")
        if a.kind == "customer":
            checklist.append(f"Introduce {succ['name'] if succ else 'the new owner'} to the {a.name.replace(' account', '')} contacts before the last day")
        checklist.append("Answer the exit-interview questions for this area")
        return {"system": a.system, "name": a.name, "label": a.label, "tier": a.tier, "share": a.share, "backup": a.backup,
                "status": a.status, "confidence": a.confidence, "priority": a.priority, "why": why, "knows": knows,
                "chores": chores, "access": access, "docs_to_fix": docs_fix, "successor": succ,
                "other_candidates": a.successors[1:], "checklist": checklist, "citations": sorted(set(cites)),
                "history": a.history, "escalated": a.escalated}

    def _polish(self, bb: Blackboard, doc: dict) -> None:
        llm = get_llm()
        if not llm.enabled or not doc["areas"]:
            return
        try:
            payload = [{"system": s["system"], "why": s["why"], "knows": [k["text"] for k in s["knows"][:4]]} for s in doc["areas"]]
            out = llm.json(SYSTEM, "For each area write a two-sentence 'summary' a manager can act on. Return "
                                   '[{"system": ..., "summary": ...}]. Areas: ' + str(payload), max_tokens=1200)
            by = {o.get("system"): o.get("summary") for o in out if isinstance(o, dict)}
            for s in doc["areas"]:
                if by.get(s["system"]):
                    s["summary"] = by[s["system"]]
            bb.emit(self.name, "llm", f"Summaries rewritten by {llm.label}")
        except (LLMError, TypeError, AttributeError) as e:
            bb.emit(self.name, "llm_fallback", f"LLM unavailable for summaries, kept template text ({str(e)[:80]})")

    def markdown(self, bb: Blackboard, doc: dict) -> str:
        L = [f"# {doc['title']}", "", doc["headline"], ""]
        if doc["escalations"]:
            L += ["## Escalate this week", ""]
            for e in doc["escalations"]:
                L.append(f"- **{e['name']}** (tier {e['tier']}, {e['days_left']} days left): " + "; ".join(e["actions"]))
            L.append("")
        for s in doc["areas"]:
            L += [f"## {s['name']}: {s['label'].replace('_', ' ')}", "", s.get("summary") or s["why"], ""]
            if s["knows"]:
                L += ["**What they know that is not written down**", ""]
                L += [f"- {k['text']} _( {k['context']} )_" for k in s["knows"]]
                L.append("")
            if s["successor"]:
                L += [f"**Recommended successor:** {s['successor']['name']}: " + "; ".join(s["successor"]["reasons"]), ""]
            L += ["**Checklist**", ""] + [f"- [ ] {c}" for c in s["checklist"]] + [""]
            L += [f"<sub>Evidence: {', '.join(s['citations'][:8])}{' ...' if len(s['citations']) > 8 else ''} · "
                  f"confidence {s['confidence']:.0%} · Critic: {s['status']}</sub>", ""]
        if doc["covered"]:
            L += ["## Already covered", ""]
            L += [f"- {c['name']}: backups {', '.join(c['backups']) or 'n/a'}" for c in doc["covered"]]
        return "\n".join(L) + "\n"

    # ------------------------------------------------------------ interview
    def interview(self, bb: Blackboard, inv) -> dict:
        t = bb.target
        first = t["full_name"].split()[0]
        questions = []
        for a in sorted(bb.areas.values(), key=lambda x: -x.priority):
            if a.label == "covered":
                continue
            qs = []
            mine = [x for x in inv.threads.get(a.system, []) if inv.owner("slack", x.get("answer_account")) == t["employee_id"]]
            theirs = [x for x in inv.threads.get(a.system, []) if inv.owner("slack", x.get("answer_account")) not in (t["employee_id"], "?")]
            if len(mine) >= 3:
                chan = mine[0]["channel"]
                others = len(theirs)
                qs.append({"text": f"You answered {len(mine)} questions about {a.name} in #{chan} this year; "
                                   f"{'nobody else answered any' if not others else f'everyone else combined answered {others}'}. "
                                   "What are the three things people keep asking, and where should the answers live?",
                           "cites": [f"slack:slack_answer:{x['channel']}/{x['ts']}" for x in mine[:5]]})
            for k in [x for x in a.tacit if _has_number(x["text"])][:1]:
                qs.append({"text": f"On {_short_date(k['at'])} you told {k['asker']}: \"{_clip(k['text'], 170)}\" "
                                   "Is that still true, and what breaks if someone gets it wrong?", "cites": [k["evidence"]]})
            for c in a.conflicts[:1]:
                qs.append({"text": f"The wiki page '{c.get('doc_title')}' says \"{_clip(c['doc'], 140)}\" but you told the "
                                   f"team \"{_clip(c['expert'], 140)}\" Which is right today?",
                           "cites": [c["doc_source"], c["expert_source"]]})
            for c in [c for c in a.chores if c["state"] == "stops when they leave"][:1]:
                qs.append({"text": f"You run '{c['summary']}' {_cadence(c['summary'])} ({c['issue_key']}). Walk us through the "
                                   "steps, including anything you do outside the ticket.", "cites": [f"jira:chore:{c['issue_key']}"]})
            for x in [x for x in a.exclusive_access if x.get("exclusive")][:1]:
                qs.append({"text": f"You are the only one holding {x['resource']} ({x['level']}). Is anything tied to your "
                                   "personal accounts or devices, and who should hold it next?",
                           "cites": [f"hr_pg:access:{x['resource']}"]})
            if not any(d["kind"] == "runbook" and d["age_days"] <= 365 for d in a.docs) and a.kind != "customer":
                qs.append({"text": f"There is no current runbook for {a.name}. If it broke at 3am after you left, what "
                                   "should the on-call check first, second and third?", "cites": []})
            if a.kind == "customer":
                qs.append({"text": f"Who are the people at {a.name.replace(' account', '')} you call when something goes "
                                   "wrong, and what do they expect from us that isn't in the CRM?",
                           "cites": [x["evidence"] for x in a.tacit[:2]]})
            for q in qs[:4]:
                questions.append({"id": f"{a.system}:{len(questions) + 1}", "system": a.system, "area": a.name,
                                  "label": a.label, **q})
        bb.emit(self.name, "interview", f"Drafted {len(questions)} exit-interview questions for {first}, each citing evidence",
                count=len(questions))
        return {"person": t["full_name"], "questions": questions}


def interview_markdown(snap: dict) -> str:
    """The exit interview as Markdown, from a run snapshot."""
    iv = snap["outputs"]["interview"]
    lines = [f"# Exit interview: {iv['person']}", ""]
    area = None
    for q in iv["questions"]:
        if q["area"] != area:
            area = q["area"]
            if lines[-1] != "":
                lines.append("")
            lines += [f"## {area} ({q['label'].replace('_', ' ')})", ""]
        lines.append(f"1. {q['text']}")
        if q["cites"]:
            lines.append(f"   <sub>Evidence: {', '.join(q['cites'][:4])}</sub>")
    return "\n".join(lines) + "\n"


def _has_number(text: str) -> bool:
    return any(ch.isdigit() for ch in text or "")


def _clip(text: str, n: int) -> str:
    """Quote at most n characters, cut at a word boundary, ending with sentence punctuation."""
    t = " ".join((text or "").split())
    if len(t) > n:
        t = t[:n].rsplit(" ", 1)[0].rstrip(",;:") + "..."
    return t if t.endswith((".", "!", "?", "...")) else t + "."


def _cadence(summary: str) -> str:
    low = (summary or "").lower()
    for word, phrase in (("daily", "every day"), ("weekly", "every week"), ("fortnightly", "every two weeks"),
                         ("monthly", "every month"), ("month-end", "every month-end"), ("quarterly", "every quarter"),
                         ("yearly", "every year"), ("annual", "every year")):
        if word in low:
            return phrase
    return "on a schedule"
