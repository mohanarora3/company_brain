"""Last Day web app: API + UI.

    python -m lastday serve        # http://localhost:8000

Runs execute in a background thread; their trace streams to the browser over
server-sent events and is saved under .lastday/runs/<id>/ (run.json,
events.jsonl, handover.md) so any run can be reopened or downloaded.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import traceback
import uuid
from datetime import date
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import federation as fedmod
from .agents.archivist import Archivist
from .agents.ask import ask as ask_agent
from .agents.orchestrator import namespace_for, run_analysis
from .agents.writer import interview_markdown
from .config import ROOT, SETTINGS
from .federation import FederationError, LocalFederation, connect
from .federation.governance import policy
from .federation.manifest import TABLES
from .federation.registration import statements
from .llm.client import get_llm
from .llm.embeddings import get_embedder
from .meterless.client import Meterless, MeterlessUnavailable

WEB = ROOT / "web"


class State:
    def __init__(self):
        self.fed = None
        self.fed_error = ""
        self.runs: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.runs_dir = SETTINGS.state_dir / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.reconnect()
        self._load_saved()

    def reconnect(self) -> None:
        try:
            self.fed = connect(SETTINGS)
            self.fed_error = ""
        except FederationError as e:
            self.fed_error = str(e)
            self.fed = LocalFederation(SETTINGS.seed_dir, fedmod.local_registered(SETTINGS))

    def _load_saved(self) -> None:
        for p in sorted(self.runs_dir.glob("*/run.json")):
            try:
                snap = json.loads(p.read_text())
                self.runs[snap["run_id"]] = {"status": snap.get("status", "done"), "snapshot": snap, "events": [],
                                             "started": p.stat().st_mtime, "saved": True}
            except (OSError, ValueError, KeyError):
                continue

    @property
    def namespace(self) -> str:
        return namespace_for(self.fed)


S: State | None = None


def state() -> State:
    global S
    if S is None:
        S = State()
    return S


# ------------------------------------------------------------------ helpers
def _json(obj, status: int = 200) -> JSONResponse:
    return JSONResponse(obj, status_code=status)


def _run_or_404(run_id: str) -> dict:
    run = state().runs.get(run_id)
    if not run:
        raise KeyError(run_id)
    return run


def _snapshot(run: dict) -> dict:
    if run.get("bb") is not None and run["status"] == "running":
        snap = run["bb"].snapshot()
        snap["status"] = "running"
        return snap
    return run["snapshot"]


def _save(run_id: str, run: dict) -> None:
    d = state().runs_dir / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "run.json").write_text(json.dumps(run["snapshot"], indent=1, default=str))
    with open(d / "events.jsonl", "w") as f:
        for e in run["events"]:
            f.write(json.dumps(e, default=str) + "\n")
    md = run["snapshot"].get("outputs", {}).get("handover", {}).get("markdown")
    if md:
        (d / "handover.md").write_text(md)
    if run["snapshot"].get("outputs", {}).get("interview"):
        (d / "interview.md").write_text(interview_markdown(run["snapshot"]))


# --------------------------------------------------------------------- API
async def status(request: Request):
    st = state()
    fed_status = await asyncio.to_thread(st.fed.status)
    try:
        h = await asyncio.to_thread(Meterless(st.namespace).health)
        mem = {"online": True, **h}
        try:
            mem["hmem"] = await asyncio.to_thread(Meterless(st.namespace).hmem_stats)
            mem["world"] = await asyncio.to_thread(Meterless(st.namespace).wm_stats)
        except MeterlessUnavailable:
            pass
    except MeterlessUnavailable as e:
        mem = {"online": False, "error": str(e)}
    return _json({"federation": fed_status, "federation_error": st.fed_error, "failing": st.fed.failing,
                  "meterless": mem, "namespace": st.namespace, "llm": get_llm().label, "embeddings": get_embedder().label,
                  "governance": policy(), "seed": SETTINGS.seed})


async def people(request: Request):
    st = state()

    def q():
        d = st.fed.query("SELECT e.employee_id AS employee_id, e.full_name AS full_name, e.title AS title, e.team AS team, "
                         "e.status AS status, e.employment_type AS employment_type FROM hr_pg.employees_directory e")
        dep = st.fed.query("SELECT employee_id, last_day, notice_date, reason_category FROM hr_pg.departures")
        return d.rows, {r["employee_id"]: r for r in dep.rows}
    try:
        rows, deps = await asyncio.to_thread(q)
    except FederationError as e:
        return _json({"error": str(e)}, 503)
    meta = st.fed.status()
    as_of = date.fromisoformat(meta["as_of"]) if meta.get("as_of") else date.today()
    out = []
    for r in rows:
        dp = deps.get(r["employee_id"])
        if dp:
            r["last_day"] = dp["last_day"]
            r["days_left"] = (date.fromisoformat(str(dp["last_day"])[:10]) - as_of).days
            r["reason"] = dp.get("reason_category")
        out.append(r)
    out.sort(key=lambda r: (r.get("days_left") is None, r.get("days_left") if r.get("days_left") is not None else 0, r["full_name"]))
    latest = {}
    for rid, run in st.runs.items():
        snap = run.get("snapshot") or {}
        eid = (snap.get("target") or {}).get("employee_id") or run.get("employee_id")
        if eid and run["status"] == "done" and (eid not in latest or run["started"] > latest[eid]["started"]):
            latest[eid] = {"run_id": rid, "started": run["started"],
                           "critical": sum(1 for a in snap.get("areas", []) if a["label"] == "critical"),
                           "at_risk": sum(1 for a in snap.get("areas", []) if a["label"] == "at_risk")}
    for r in out:
        if r["employee_id"] in latest:
            r["latest_run"] = latest[r["employee_id"]]
    return _json({"as_of": as_of.isoformat(), "people": out})


async def start_run(request: Request):
    body = await request.json()
    eid = body.get("employee_id")
    if not eid:
        return _json({"error": "employee_id is required"}, 400)
    st = state()
    run_id = uuid.uuid4().hex[:10]
    run = {"status": "running", "events": [], "snapshot": {}, "bb": None, "started": time.time(), "employee_id": eid}
    with st.lock:
        st.runs[run_id] = run

    def on_event(ev):
        run["events"].append(ev)

    def work():
        try:
            bb = None

            def hook(ev):
                on_event(ev)
            run["bb"] = None
            bb = run_analysis(st.fed, eid, on_event=hook, run_id=run_id, use_memory=bool(body.get("use_memory", True)))
            run["bb"] = bb
            snap = bb.snapshot()
            snap["status"] = "done"
            run["snapshot"] = snap
            run["status"] = "done"
        except Exception as e:  # report the failure to the UI instead of dying silently
            run["status"] = "error"
            run["snapshot"] = {"run_id": run_id, "status": "error", "error": str(e), "trace": traceback.format_exc()[-2000:]}
            run["events"].append({"seq": len(run["events"]) + 1, "agent": "Orchestrator", "kind": "error",
                                  "summary": f"Run failed: {e}", "round": 0, "t": 0, "data": {}})
        finally:
            _save(run_id, run)
    threading.Thread(target=work, daemon=True).start()
    return _json({"run_id": run_id})


async def list_runs(request: Request):
    st = state()
    out = []
    for rid, run in sorted(st.runs.items(), key=lambda x: -x[1]["started"]):
        snap = run.get("snapshot") or {}
        out.append({"run_id": rid, "status": run["status"], "started": run["started"],
                    "target": snap.get("target") or {"employee_id": run.get("employee_id")},
                    "engine": snap.get("engine"), "areas": len(snap.get("areas", []))})
    return _json(out)


async def get_run(request: Request):
    try:
        run = _run_or_404(request.path_params["run_id"])
    except KeyError:
        return _json({"error": "unknown run"}, 404)
    return _json(_snapshot(run))


async def run_events(request: Request):
    try:
        run = _run_or_404(request.path_params["run_id"])
    except KeyError:
        return _json({"error": "unknown run"}, 404)
    if not run["events"] and run.get("saved"):
        p = state().runs_dir / request.path_params["run_id"] / "events.jsonl"
        if p.exists():
            run["events"] = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]

    async def stream():
        i = int(request.query_params.get("after", 0))
        while True:
            evs = run["events"]
            while i < len(evs):
                yield f"data: {json.dumps(evs[i], default=str)}\n\n"
                i += 1
            if run["status"] != "running":
                yield f"event: end\ndata: {json.dumps({'status': run['status']})}\n\n"
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.15)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


async def run_download(request: Request):
    rid, what = request.path_params["run_id"], request.path_params["what"]
    d = state().runs_dir / rid
    files = {"handover.md": "text/markdown", "interview.md": "text/markdown", "events.jsonl": "application/x-ndjson",
             "run.json": "application/json"}
    if what not in files or not (d / what).exists():
        return _json({"error": "not found"}, 404)
    return FileResponse(d / what, media_type=files[what], filename=f"lastday-{rid}-{what}")


async def save_answer(request: Request):
    try:
        run = _run_or_404(request.path_params["run_id"])
    except KeyError:
        return _json({"error": "unknown run"}, 404)
    body = await request.json()
    if not (body.get("answer") or "").strip():
        return _json({"error": "write an answer first"}, 400)
    snap = _snapshot(run)
    arch = Archivist(state().namespace)
    try:
        out = await asyncio.to_thread(arch.save_answer, None, snap, body.get("system", ""), body.get("question", ""),
                                      body["answer"].strip())
    except MeterlessUnavailable as e:
        return _json({"error": f"Meterless bridge unavailable: {e}"}, 503)
    answers = snap.setdefault("answers", {})
    answers[body.get("question_id", body.get("question", ""))] = {"answer": body["answer"], "memory_id": out["memory"]["id"],
                                                                  "conflicts": out["conflicts"]}
    if run["status"] != "running":
        _save(request.path_params["run_id"], run)
    return _json(out)


async def accept_handover(request: Request):
    try:
        run = _run_or_404(request.path_params["run_id"])
    except KeyError:
        return _json({"error": "unknown run"}, 404)
    body = await request.json()
    snap = _snapshot(run)
    arch = Archivist(state().namespace)
    try:
        out = await asyncio.to_thread(arch.accept_handover, snap, request.path_params["system"], body["successor_id"],
                                      body.get("by", "manager"))
    except MeterlessUnavailable as e:
        return _json({"error": f"Meterless bridge unavailable: {e}"}, 503)
    snap.setdefault("accepted", {})[request.path_params["system"]] = {"successor_id": body["successor_id"],
                                                                     "successor": body.get("successor_name")}
    if run["status"] != "running":
        _save(request.path_params["run_id"], run)
    return _json(out)


async def ask(request: Request):
    body = await request.json()
    q = (body.get("question") or "").strip()
    if not q:
        return _json({"error": "type a question"}, 400)
    st = state()
    meta = st.fed.status()
    as_of = date.fromisoformat(meta["as_of"]) if meta.get("as_of") else date.today()
    try:
        out = await asyncio.to_thread(ask_agent, st.fed, st.namespace, q, None, None, as_of)
    except FederationError as e:
        return _json({"error": str(e)}, 503)
    return _json(out)


async def feedback(request: Request):
    body = await request.json()
    try:
        out = await asyncio.to_thread(Meterless(state().namespace).feedback, body["memory_id"], body["kind"])
    except MeterlessUnavailable as e:
        return _json({"error": str(e)}, 503)
    return _json(out)


async def memory_audit(request: Request):
    try:
        out = await asyncio.to_thread(Meterless(state().namespace).audit, request.path_params["memory_id"])
    except MeterlessUnavailable as e:
        return _json({"error": str(e)}, 503)
    return _json(out)


async def world(request: Request):
    m = Meterless(state().namespace)
    what = request.path_params["what"]
    try:
        if what == "stats":
            out = await asyncio.to_thread(m.wm_stats)
        elif what == "audit":
            out = await asyncio.to_thread(m.wm_audit, int(request.query_params.get("limit", 60)))
        elif what == "ownership":
            out = await asyncio.to_thread(m.relationships, "owned_by", request.query_params.get("id"))
        else:
            return _json({"error": "unknown"}, 404)
    except MeterlessUnavailable as e:
        return _json({"error": str(e)}, 503)
    return _json(out)


async def sources(request: Request):
    st = state()
    fed = st.fed
    reg = sorted({t.source for t in TABLES})
    registered = sorted(fed.registered) if isinstance(fed, LocalFederation) else None
    counts = await asyncio.to_thread(fed.counts) if isinstance(fed, LocalFederation) else {}
    return _json({"engine": fed.engine, "all_sources": reg, "registered": registered, "counts": counts,
                  "failing": fed.failing, "governance": policy()})


async def register_source(request: Request):
    st = state()
    source = request.path_params["source"]
    sql = statements(source, SETTINGS, placeholders=False)
    if isinstance(st.fed, LocalFederation):
        tables = await asyncio.to_thread(st.fed.register, source)
        fedmod.save_local_registered(SETTINGS, set(st.fed.registered))
        return _json({"registered": tables, "engine": "local",
                      "note": "Loaded into the local snapshot. On Zetaris, these statements do the same:", "sql": sql})
    body = await request.json() if request.headers.get("content-length") else {}
    if not body.get("confirm"):
        return _json({"engine": "zetaris", "dry_run": True, "sql": sql,
                      "note": "Run with {\"confirm\": true} to execute these statements on your Zetaris instance."})
    done = []
    for stmt in sql:
        try:
            await asyncio.to_thread(st.fed.admin, stmt)
            done.append({"sql": stmt.split("\n")[0], "ok": True})
        except FederationError as e:
            done.append({"sql": stmt.split("\n")[0], "ok": "already exists" in str(e).lower(), "error": str(e)[:200]})
    st.fed.clear_cache()
    return _json({"engine": "zetaris", "results": done})


async def fail_source(request: Request):
    body = await request.json()
    out = state().fed.inject_failure(request.path_params["source"], bool(body.get("on", True)))
    return _json(out)


async def index(request: Request):
    return FileResponse(WEB / "index.html")


def make_app() -> Starlette:
    routes = [
        Route("/", index),
        Route("/api/status", status),
        Route("/api/people", people),
        Route("/api/runs", list_runs, methods=["GET"]),
        Route("/api/runs", start_run, methods=["POST"]),
        Route("/api/runs/{run_id}", get_run),
        Route("/api/runs/{run_id}/events", run_events),
        Route("/api/runs/{run_id}/files/{what}", run_download),
        Route("/api/runs/{run_id}/interview", save_answer, methods=["POST"]),
        Route("/api/runs/{run_id}/handover/{system}/accept", accept_handover, methods=["POST"]),
        Route("/api/ask", ask, methods=["POST"]),
        Route("/api/memory/feedback", feedback, methods=["POST"]),
        Route("/api/memory/{memory_id}/audit", memory_audit),
        Route("/api/world/{what}", world),
        Route("/api/sources", sources),
        Route("/api/sources/{source}/register", register_source, methods=["POST"]),
        Route("/api/sources/{source}/fail", fail_source, methods=["POST"]),
        Mount("/static", StaticFiles(directory=WEB), name="static"),
    ]
    app = Starlette(routes=routes)
    return app


def serve(port: int | None = None, host: str = "127.0.0.1") -> None:
    import uvicorn
    state()
    try:
        Meterless(state().namespace).health()
    except MeterlessUnavailable as e:
        print(f"warning: {e}")
    uvicorn.run(make_app(), host=host, port=port or SETTINGS.port, log_level="warning")
