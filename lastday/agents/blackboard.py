"""Shared state for one Last Day run: the blackboard every agent reads and writes.

Agents never call each other directly. They post findings, verdicts and
requests here; the orchestrator decides who acts next. Every federated query,
decision and memory write is recorded as a trace event with its SQL, engine,
row count and timing, so the run can be replayed and audited.
"""
from __future__ import annotations

import itertools
import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable

from ..federation import Federation, FederationError
from ..federation.base import QueryResult
from ..federation.governance import GovernanceError

SOURCE_OF_TABLE = lambda q: q.split(".")[0]  # noqa: E731


@dataclass
class Evidence:
    id: str
    source: str            # github | slack | jira | docs | pagerduty | hr_pg
    kind: str              # commit | review | slack_answer | issue | chore | doc | incident | access
    system: str
    person: str | None     # HR employee id, when resolved
    ref: str               # sha, message ts, issue key, page id, incident id, resource
    title: str
    at: str = ""
    weight: float = 1.0
    query_id: str = ""
    url: str = ""


@dataclass
class QueryLog:
    id: str
    agent: str
    purpose: str
    sql: str
    engine: str
    rows: int
    ms: float
    round: int
    error: str = ""


@dataclass
class Request:
    """Work one agent asks another to do. The Planner turns these into tasks."""
    id: str
    by: str
    kind: str              # corroborate | identity | tacit | docs | access | retry_source
    system: str = ""
    detail: str = ""
    payload: dict = field(default_factory=dict)
    status: str = "open"   # open | done | dropped


@dataclass
class Area:
    system: str
    name: str
    kind: str
    tier: int
    team: str
    label: str = "unknown"            # critical | at_risk | covered
    provisional_label: str = ""
    share: float = 0.0                # target's share of evidence-weighted knowledge
    backup: float = 0.0               # strongest remaining person's share
    backups: list = field(default_factory=list)       # [{person, name, share, last_at}]
    by_source: dict = field(default_factory=dict)     # source -> {"target": w, "others": w}
    sources_used: list = field(default_factory=list)
    footprint: dict = field(default_factory=dict)     # target's own evidence weight by source
    doc_coverage: float = 0.0
    docs: list = field(default_factory=list)
    exclusive_access: list = field(default_factory=list)
    chores: list = field(default_factory=list)
    tacit: list = field(default_factory=list)          # [{text, question, evidence}]
    conflicts: list = field(default_factory=list)
    evidence_ids: list = field(default_factory=list)
    confidence: float = 0.5
    status: str = "proposed"                           # proposed | verified | downgraded | upgraded | accepted
    history: list = field(default_factory=list)        # verdict history across rounds
    priority: float = 0.0
    escalated: bool = False
    successors: list = field(default_factory=list)
    reason: str = ""


class Blackboard:
    def __init__(self, fed: Federation, target: dict, as_of: date, run_id: str | None = None,
                 on_event: Callable[[dict], None] | None = None):
        self.fed = fed
        self.run_id = run_id or uuid.uuid4().hex[:10]
        self.target = target                     # {employee_id, full_name, last_day, team, ...}
        self.as_of = as_of
        self.round = 0
        self.catalog: list = []
        self.source_map: dict = {}
        self.probes_available: set[str] = set()
        self.directory: dict[str, dict] = {}     # employee_id -> directory row
        self.leaving: set[str] = set()           # employee ids leaving or already left
        self.identities: dict = {}               # employee_id -> {system: [{id, method, confidence}]}
        self.account_owner: dict = {}            # (system, account_id) -> {person, confidence, method, candidates}
        self.systems: dict[str, dict] = {}       # service catalog rows
        self.evidence: dict[str, Evidence] = {}
        self.queries: list[QueryLog] = []
        self.requests: list[Request] = []
        self.areas: dict[str, Area] = {}
        self.findings: list[dict] = []
        self.escalations: list[dict] = []
        self.failed_sources: dict[str, str] = {}
        self.memory_log: list[dict] = []
        self.outputs: dict = {}
        self.events: list[dict] = []
        self.started = time.time()
        self._seq = itertools.count(1)
        self._lock = threading.RLock()
        self._on_event = on_event

    # -------------------------------------------------------------- tracing
    def emit(self, agent: str, kind: str, summary: str, **data: Any) -> dict:
        ev = {"seq": next(self._seq), "t": round(time.time() - self.started, 3), "round": self.round,
              "agent": agent, "kind": kind, "summary": summary, "data": _jsonable(data)}
        with self._lock:
            self.events.append(ev)
        if self._on_event:
            try:
                self._on_event(ev)
            except Exception:  # a slow UI must never break a run
                pass
        return ev

    # ---------------------------------------------------------------- query
    def sql(self, agent: str, purpose: str, sql: str, numeric: tuple = (), retries: int = 1) -> QueryResult | None:
        """Run one governed federated query and log it. Returns None if the source is down."""
        qid = f"q{len(self.queries) + 1:03d}"
        tables = sorted(set(_tables_in(sql)))
        sources = sorted({SOURCE_OF_TABLE(t) for t in tables})
        attempt = 0
        while True:
            try:
                res = self.fed.query(sql, numeric=numeric)
                log = QueryLog(qid, agent, purpose, res.sql, res.engine, len(res.rows), res.elapsed_ms, self.round)
                with self._lock:
                    self.queries.append(log)
                self.emit(agent, "query", purpose, query_id=qid, sql=res.sql, engine=res.engine, rows=len(res.rows),
                          ms=res.elapsed_ms, sources=sources, sample=res.rows[:3])
                res.note = qid
                return res
            except GovernanceError as e:
                with self._lock:
                    self.queries.append(QueryLog(qid, agent, purpose, sql, self.fed.engine, 0, 0, self.round, f"blocked: {e}"))
                self.emit(agent, "blocked", f"Governance blocked a query: {e}", query_id=qid, sql=sql)
                return None
            except FederationError as e:
                attempt += 1
                if attempt <= retries:
                    self.emit(agent, "retry", f"{purpose}: source error, retrying ({e})", query_id=qid, sources=sources)
                    time.sleep(0.4 * attempt)
                    continue
                # Blame only the source the error names (a failed Jira x HR join is a Jira outage, not an HR one).
                named = [s for s in sources if re.search(rf"\b{re.escape(s)}\b", str(e))]
                culprits = named or sources
                with self._lock:
                    self.queries.append(QueryLog(qid, agent, purpose, sql, self.fed.engine, 0, 0, self.round, str(e)))
                    for s in culprits:
                        self.failed_sources.setdefault(s, str(e)[:200])
                self.emit(agent, "error", f"{purpose}: {', '.join(culprits)} unavailable after retry", query_id=qid,
                          error=str(e)[:300], sources=culprits)
                return None

    # ------------------------------------------------------------ evidence
    def add_evidence(self, ev: Evidence) -> str:
        with self._lock:
            self.evidence.setdefault(ev.id, ev)
        return ev.id

    def request(self, by: str, kind: str, system: str = "", detail: str = "", **payload: Any) -> Request:
        with self._lock:
            for r in self.requests:
                if r.kind == kind and r.system == system and r.status == "open" and r.payload == payload:
                    return r
            req = Request(f"r{len(self.requests) + 1:02d}", by, kind, system, detail, payload)
            self.requests.append(req)
        verb = {"corroborate": "asks for corroboration of", "identity": "asks the Resolver to identify accounts on",
                "tacit": "asks for what only they know about", "retry_source": "asks to retry a failed source",
                "docs": "asks for the docs on", "access": "asks who else has access to"}.get(kind, f"asks for {kind} on")
        self.emit(by, "request", verb + (f" {system}" if system else "") + (f": {detail}" if detail else ""),
                  request_id=req.id, request_kind=kind, system=system)
        return req

    def open_requests(self) -> list[Request]:
        return [r for r in self.requests if r.status == "open"]

    def person_name(self, eid: str | None) -> str:
        if not eid:
            return "unattributed"
        return (self.directory.get(eid) or {}).get("full_name", eid)

    def active_people(self) -> list[str]:
        return [e for e, r in self.directory.items() if r.get("status") == "active"]

    def snapshot(self) -> dict:
        """Everything the UI and the report need, as plain JSON."""
        return {
            "run_id": self.run_id, "target": self.target, "as_of": self.as_of.isoformat(), "round": self.round,
            "engine": self.fed.engine, "areas": [asdict(a) for a in sorted(self.areas.values(), key=lambda a: -a.priority)],
            "requests": [asdict(r) for r in self.requests], "escalations": self.escalations,
            "queries": [asdict(q) for q in self.queries], "failed_sources": self.failed_sources,
            "identities": self.identities, "source_map": self.source_map, "memory_log": self.memory_log,
            "outputs": self.outputs, "evidence_count": len(self.evidence),
            "evidence": {k: asdict(v) for k, v in list(self.evidence.items())},
            "findings": self.findings, "duration_s": round(time.time() - self.started, 2),
        }


def _tables_in(sql: str) -> list[str]:
    import re
    return [m.group(1).lower() for m in re.finditer(r"\b(?:from|join)\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)", sql, re.I)]


def _jsonable(x: Any) -> Any:
    try:
        json.dumps(x)
        return x
    except TypeError:
        if isinstance(x, dict):
            return {k: _jsonable(v) for k, v in x.items()}
        if isinstance(x, (list, tuple, set)):
            return [_jsonable(v) for v in x]
        if isinstance(x, (date, datetime)):
            return x.isoformat()
        return str(x)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
