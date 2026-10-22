"""Orchestrator: runs the agents against the blackboard until nothing is left to verify.

    Cartographer -> Resolver -> Planner
    round 1  footprint (Investigators, parallel)          -> Planner picks candidates
    round 2  ownership from systems of record (parallel)  -> Analyst (provisional) -> Critic
    round 3+ Planner delegates the Critic's requests:
             corroborate / identity / retry_source / tacit -> Analyst -> Critic ...
             until the Critic raises nothing new (max 6 rounds)
    Risk officer (may overrule the Critic on exclusive access) -> Successor scout
    Archivist (Meterless H-MEM + World Model, conflict detection)
    Writer (handover + interview) -> Critic checks every citation
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Callable

from ..config import SETTINGS
from ..federation import Federation
from ..llm.client import get_llm
from ..llm.embeddings import get_embedder
from .analyst import Analyst
from .archivist import Archivist
from .blackboard import Blackboard
from .cartographer import Cartographer
from .critic import Critic
from .investigators import Investigators, tacit_items
from .planner import Planner
from .resolver import Resolver
from .risk import RiskOfficer
from .successor import SuccessorScout
from .writer import Writer

MAX_ROUNDS = 6


def namespace_for(fed: Federation) -> str:
    seed = fed.status().get("seed") if fed.engine == "local" else None
    return f"acme-seed-{seed}" if seed is not None else f"acme-zetaris-seed-{SETTINGS.seed}"


def run_analysis(fed: Federation, employee_id: str, as_of: date | None = None, on_event: Callable[[dict], None] | None = None,
                 use_memory: bool = True, run_id: str | None = None) -> Blackboard:
    as_of = as_of or _as_of(fed)
    bb = Blackboard(fed, {"employee_id": employee_id}, as_of, run_id=run_id, on_event=on_event)
    bb.emit("Orchestrator", "start", f"Last Day run {bb.run_id} on {fed.engine}", llm=get_llm().label,
            embeddings=get_embedder().label, as_of=as_of.isoformat())

    Cartographer().run(bb)
    resolver = Resolver()
    resolver.run(bb)
    if employee_id not in bb.directory:
        raise ValueError(f"unknown employee {employee_id}")
    d = bb.directory[employee_id]
    bb.target = {"employee_id": employee_id, "full_name": d["full_name"], "title": d.get("title"), "team": d.get("team"),
                 "last_day": d.get("last_day"), "status": d.get("status")}

    archivist = Archivist(namespace_for(fed))
    prior = {}
    handed = {}
    if use_memory and archivist.connect(bb):
        archivist.seed_world(bb)
        prior = archivist.prior(bb)
        handed = _handed_over(bb, archivist)
    bb.outputs["prior"] = {k: len(v) for k, v in prior.items()}

    planner, analyst, critic = Planner(), Analyst(), Critic()
    planner.initial(bb, prior)
    inv = Investigators(bb)

    # Round 1: footprint
    bb.round = 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_fp = pool.submit(inv.footprint)
        f_acc = pool.submit(inv.access)
        footprint, access = f_fp.result(), f_acc.result()
    bb.outputs["footprint"] = footprint
    candidates = planner.candidates(bb, footprint, access, prior)
    for x in access:
        if x.get("system"):
            analyst_area = bb.areas.get(x["system"])
            if analyst_area is None:
                analyst.score(bb, inv, [x["system"]], "init")
            bb.areas[x["system"]].exclusive_access.append(x)
    chores = inv.chores(candidates)

    # Round 2: ownership from systems of record
    bb.round = 2
    _parallel([lambda: inv.code(candidates), lambda: inv.reviews(candidates), lambda: inv.work(candidates)])
    analyst.score(bb, inv, candidates, "provisional")
    for sid in candidates:
        bb.areas[sid].chores = chores.get(sid, [])
        bb.areas[sid].footprint = footprint.get(sid, {})
    _apply_prior(bb, prior)
    critic.review(bb, "provisional")

    # Rounds 3..: delegate the Critic's requests until it is satisfied
    corroborated: set[str] = set()
    while bb.round < MAX_ROUNDS:
        tasks = planner.tasks(bb)
        if not any(tasks.values()):
            break
        bb.round += 1
        systems = sorted({r.system for r in tasks["corroborate"] if r.system} |
                         {r.system for r in tasks["tacit"] if r.system and r.system not in corroborated})
        if systems:
            _parallel([lambda: inv.conversation(systems), lambda: inv.activity(systems)])
            docs = inv.docs(systems)
            for sid in systems:
                bb.areas[sid].docs = docs.get(sid, {}).get("pages", [])
                bb.areas[sid].doc_coverage = docs.get(sid, {}).get("coverage", 0.0)
            corroborated |= set(systems)
        for r in tasks["identity"]:
            v = resolver.disambiguate(bb, r.payload["source"], r.payload["account"])
            for f in bb.findings:
                if f.get("kind") == "identity_ambiguous" and f["account"] == r.payload["account"]:
                    f["resolved"] = True
                    f["verdict"] = v
        for r in tasks["retry_source"]:
            src = r.payload["source"]
            bb.failed_sources.pop(src, None)
            inv.forget(src)
            redo = sorted(corroborated) or candidates
            _parallel([lambda: inv.code(candidates), lambda: inv.reviews(candidates), lambda: inv.work(candidates),
                       lambda: inv.conversation(redo), lambda: inv.activity(redo)])
            if src in bb.failed_sources:
                bb.emit("Planner", "degraded", f"{src} still unavailable: continuing with the other sources, confidence lowered",
                        source=src)
        for r in tasks["tacit"]:
            area = bb.areas.get(r.system)
            if area:
                area.tacit = tacit_items(inv, r.system)
                bb.emit("Investigator", "tacit", f"{area.name}: {len(area.tacit)} answers only "
                        f"{bb.target['full_name'].split()[0]} has given", system=r.system,
                        items=[t["text"][:90] for t in area.tacit])
        for r in tasks["corroborate"] + tasks["identity"] + tasks["retry_source"] + tasks["tacit"]:
            r.status = "done"
        analyst.score(bb, inv, sorted(bb.areas), "corroborated")
        _apply_prior(bb, prior)
        critic.review(bb, "final")

    for sid, who in handed.items():
        a = bb.areas.get(sid)
        if a and a.label != "covered":
            a.history.append({"round": bb.round, "stage": "handover", "notes": [f"handover accepted: World Model owned_by -> {who}"]})
            a.status, a.reason = "handed_over", f"handover accepted to {who}"
    RiskOfficer().assess(bb)
    for sid, who in handed.items():
        if sid in bb.areas and bb.areas[sid].status == "handed_over":
            bb.areas[sid].priority = round(bb.areas[sid].priority * 0.3, 3)
    SuccessorScout().run(bb, inv)
    if use_memory and archivist.ok:
        archivist.record(bb)

    writer = Writer()
    handover = writer.handover(bb)
    problems = critic.check_citations(bb, handover)
    if problems and any("no citations" in p for p in problems):
        for s in handover["areas"]:
            s.pop("summary", None)
        handover["markdown"] = writer.markdown(bb, handover)
    bb.outputs["handover"] = handover
    bb.outputs["interview"] = writer.interview(bb, inv)
    bb.outputs["citation_problems"] = problems
    bb.outputs["handed_over"] = handed
    labels = {l: [a.name for a in bb.areas.values() if a.label == l] for l in ("critical", "at_risk", "covered")}
    bb.emit("Orchestrator", "done", f"Done in {bb.round} rounds, {len(bb.queries)} federated queries: "
            f"{len(labels['critical'])} critical, {len(labels['at_risk'])} at risk, {len(labels['covered'])} covered",
            labels=labels, queries=len(bb.queries), evidence=len(bb.evidence))
    return bb


def _parallel(fns: list) -> None:
    with ThreadPoolExecutor(max_workers=min(4, len(fns))) as pool:
        for f in [pool.submit(fn) for fn in fns]:
            f.result()


def _apply_prior(bb: Blackboard, prior: dict) -> None:
    """Exit-interview answers already in H-MEM count as written knowledge: a backup that never leaves."""
    from .analyst import label_for
    for sid, answers in prior.items():
        a = bb.areas.get(sid)
        if not a or not answers:
            continue
        written = min(0.6, 0.15 * len(answers))
        share = a.share / (1 + written * a.share) if a.share else 0.0
        backup = max(a.backup, written * a.share / (1 + written * a.share))
        new = label_for(share, backup, any(x.get("exclusive") for x in a.exclusive_access))
        note = f"{len(answers)} exit-interview answers captured in H-MEM count as written knowledge"
        if new != a.label:
            note += f": {a.label.replace('_', ' ')} to {new.replace('_', ' ')}"
        a.share, a.backup, a.label = round(share, 3), round(backup, 3), new
        a.doc_coverage = max(a.doc_coverage, min(0.9, 0.3 + 0.15 * len(answers)))
        a.backups = [{"person": "written", "name": "Exit interview (H-MEM)", "share": round(backup, 3), "last_at": "",
                      "stale": False, "sources": ["hmem"]}] + [b for b in a.backups if b["person"] != "written"]
        if not a.history or a.history[-1].get("stage") != "memory":
            a.history.append({"round": bb.round, "stage": "memory", "notes": [note]})


def _handed_over(bb: Blackboard, archivist: Archivist) -> dict:
    """Areas whose World Model owned_by edge now points at someone other than the departing person."""
    out = {}
    try:
        rels = archivist.m.relationships("owned_by")
    except Exception:
        return out
    eid = bb.target["employee_id"]
    latest: dict = {}
    for r in rels:
        if r.get("validTo"):
            continue
        sid = r["from"].split(":")[-1]
        if not latest.get(sid) or r.get("validFrom", "") > latest[sid].get("validFrom", ""):
            latest[sid] = r
    for sid, r in latest.items():
        owner = r["to"].split(":")[-1]
        if owner != eid and (r.get("attrs") or {}).get("basis") == "handover accepted":
            out[sid] = bb.person_name(owner)
    if out:
        bb.emit("Archivist", "handover_state", f"World Model shows {len(out)} accepted handovers", handed=out)
    return out


def _as_of(fed: Federation) -> date:
    st = fed.status()
    if st.get("as_of"):
        return date.fromisoformat(st["as_of"])
    meta = Path(SETTINGS.seed_dir) / "meta.json"
    if meta.exists():
        return date.fromisoformat(json.loads(meta.read_text())["as_of"])
    return date.today()
