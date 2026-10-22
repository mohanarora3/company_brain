"""Last Day command line.

    python -m lastday doctor                      # what is configured, what is missing
    python -m lastday generate --seed 42          # build a fictional company (5 fragmented systems + HR)
    python -m lastday serve                       # web app on http://localhost:8000
    python -m lastday run "Priya"                 # one investigation in the terminal
    python -m lastday ask "why does recon run at 03:40?"
    python -m lastday eval --seeds 42 7 13 21     # score the agents against planted ground truth
    python -m lastday saas                        # the SaaS APIs Zetaris registers as REST tables
    python -m lastday zetaris sql|register|check  # Zetaris registration and verification
    python -m lastday memory stats|reset          # Meterless H-MEM + World Model state
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import date
from pathlib import Path

from .agents.writer import interview_markdown
from .config import ROOT, SETTINGS

AGENT_COLORS = {
    "Orchestrator": "1;37", "Cartographer": "36", "Resolver": "34", "Planner": "35", "Investigator": "32",
    "Analyst": "33", "Critic": "1;31", "Risk officer": "31", "Successor scout": "32", "Archivist": "1;34",
    "Writer": "37", "Ask": "36",
}


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def _set_seed(seed: int | None) -> None:
    if seed is not None:
        SETTINGS.seed = seed


def ensure_data(seed: int | None = None, as_of: date | None = None) -> Path:
    """Generate the company for this seed if it is missing (idempotent, a few seconds)."""
    from .data.generator import write
    seed = SETTINGS.seed if seed is None else seed
    root = SETTINGS.data_dir / f"seed-{seed}"
    if not (root / "meta.json").exists():
        print(f"Generating Acme Pay (seed {seed}) ...", file=sys.stderr)
        write(seed, SETTINGS.data_dir, as_of=as_of or date(2026, 10, 22))
    return root


def _fed(engine: str | None):
    from .federation import FederationError, LocalFederation, connect, local_registered
    if (engine or SETTINGS.engine) != "zetaris":
        ensure_data()
    try:
        return connect(SETTINGS, engine)
    except FederationError as e:
        if engine == "zetaris":
            raise SystemExit(f"Zetaris: {e}")
        ensure_data()
        return LocalFederation(SETTINGS.seed_dir, local_registered(SETTINGS))


def _resolve_person(fed, who: str) -> str:
    rows = fed.query("SELECT employee_id AS employee_id, full_name AS full_name, status AS status "
                     "FROM hr_pg.employees_directory").rows
    exact = [r for r in rows if r["employee_id"].lower() == who.lower()]
    if exact:
        return exact[0]["employee_id"]
    hits = [r for r in rows if who.lower() in r["full_name"].lower()]
    if len(hits) == 1:
        return hits[0]["employee_id"]
    if not hits:
        raise SystemExit(f"Nobody called {who!r}. Try `python -m lastday people`.")
    raise SystemExit(f"{who!r} matches {', '.join(r['full_name'] for r in hits)}; use the employee id.")


# ------------------------------------------------------------------ commands
def cmd_generate(a) -> None:
    from .data.generator import write
    as_of = date.fromisoformat(a.as_of) if a.as_of else date(2026, 10, 22)
    for seed in a.seeds or [a.seed if a.seed is not None else SETTINGS.seed]:
        root = write(seed, SETTINGS.data_dir, as_of=as_of)
        meta = json.loads((root / "meta.json").read_text())
        print(f"seed {seed}: {root}  " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in meta["counts"].items()))


def cmd_people(a) -> None:
    fed = _fed(a.engine)
    rows = fed.query("SELECT e.employee_id AS employee_id, e.full_name AS full_name, e.title AS title, e.team AS team, "
                     "e.status AS status, d.last_day AS last_day FROM hr_pg.employees_directory e "
                     "LEFT JOIN hr_pg.departures d ON d.employee_id = e.employee_id").rows
    rows.sort(key=lambda r: (r["status"] == "active", r["full_name"]))
    for r in rows:
        tag = {"leaving": _c("1;31", "leaving"), "left": _c("2", "left")}.get(r["status"], "active")
        print(f"{r['employee_id']}  {r['full_name']:<20} {r['title']:<32} {r['team']:<18} {tag:<8} {r['last_day'] or ''}")


def cmd_run(a) -> None:
    from .agents.orchestrator import run_analysis
    fed = _fed(a.engine)
    eid = _resolve_person(fed, a.person)
    for src in a.fail or []:
        fed.inject_failure(src)
        print(_c("33", f"Simulating an outage of {src}: every query that touches it fails"))
    seen_round = [-1]

    def show(ev: dict) -> None:
        if a.quiet:
            return
        if ev["round"] != seen_round[0]:
            seen_round[0] = ev["round"]
            print(_c("2", f"--- round {ev['round']} ---"))
        agent = ev["agent"]
        line = f"{_c(AGENT_COLORS.get(agent, '37'), f'{agent:>15}')}  {ev['summary']}"
        if ev["kind"] == "query" and a.sql:
            line += "\n" + _c("2", " " * 17 + ev["data"].get("sql", "")[:300])
        elif ev["kind"] == "query":
            line += _c("2", f"  [{ev['data'].get('rows')} rows, {ev['data'].get('ms')} ms, {ev['data'].get('engine')}]")
        print(line)

    bb = run_analysis(fed, eid, on_event=show, use_memory=not a.no_memory)
    snap = bb.snapshot()
    snap["status"] = "done"
    out = Path(a.out) if a.out else SETTINGS.state_dir / "runs" / bb.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.json").write_text(json.dumps(snap, indent=1, default=str))
    (out / "events.jsonl").write_text("".join(json.dumps(e, default=str) + "\n" for e in bb.events))
    (out / "handover.md").write_text(snap["outputs"]["handover"]["markdown"])
    (out / "interview.md").write_text(interview_markdown(snap))
    print()
    print(_c("1", snap["outputs"]["handover"]["headline"]))
    for ar in snap["areas"]:
        mark = {"critical": _c("1;31", "CRITICAL"), "at_risk": _c("33", "AT RISK "), "covered": _c("32", "covered ")}[ar["label"]]
        print(f"  {mark} {ar['name']:<28} {ar['share']:>4.0%} theirs, best backup {ar['backup']:.0%}  ({ar['status']})")
    print(f"\n{len(bb.queries)} federated queries on {fed.engine}, {bb.round} rounds, {len(bb.evidence)} pieces of evidence, "
          f"{snap['duration_s']}s")
    print(f"Saved to {out}/ (handover.md, interview.md, run.json, events.jsonl)")



def cmd_ask(a) -> None:
    from .agents.ask import ask
    from .agents.orchestrator import namespace_for
    fed = _fed(a.engine)
    st = fed.status()
    as_of = date.fromisoformat(st["as_of"]) if st.get("as_of") else date.today()
    out = ask(fed, namespace_for(fed), a.question, as_of=as_of)
    print(_c("1", out["answer"]))
    print(_c("2", f"({out['mode']})"))
    for c in out["context"]:
        print(f"  [{c['n']}] {c['label']}: {c['text'][:140]}")


def cmd_eval(a) -> None:
    from .eval import evaluate, save
    summary = evaluate(a.seeds, use_memory=a.memory, verbose=not a.quiet)
    if a.out:
        save(summary, Path(a.out))
        print(f"saved {a.out}")


def cmd_serve(a) -> None:
    from . import server
    if a.engine:
        SETTINGS.engine = a.engine
    if SETTINGS.engine != "zetaris":
        ensure_data()
    print(f"Last Day on http://{a.host}:{a.port or SETTINGS.port}  (Ctrl+C to stop)")
    server.serve(a.port, a.host)


def cmd_saas(a) -> None:
    from .saas import mock_api
    ensure_data()
    print(f"Acme Pay SaaS APIs (Slack, Jira, GitHub, Docs, PagerDuty) on http://{a.host}:{a.port or SETTINGS.saas_port}, "
          f"seed {SETTINGS.seed}. Token: SAAS_TOKEN from .env")
    mock_api.serve(a.port, a.host)


def cmd_zetaris(a) -> None:
    from .federation import FederationError, LocalFederation, ZetarisFederation
    from .federation.manifest import TABLES
    from .federation.registration import ORDER, statements, write_files
    if a.action == "sql":
        out = ROOT / "zetaris" / ("sql" if a.template else "sql/generated")
        for p in write_files(SETTINGS, out, placeholders=a.template):
            print(p.relative_to(ROOT))
        if not a.template:
            print(f"Endpoints: SaaS {SETTINGS.saas_public_url}, HR {SETTINGS.hr_jdbc_url}. These files hold your SAAS_TOKEN "
                  "and HR password; zetaris/sql/generated/ is gitignored.")
        return
    if a.action == "register" and not a.yes:
        from dataclasses import replace
        masked = replace(SETTINGS, saas_token="${SAAS_TOKEN}", hr_pg_password="${HR_PG_PASSWORD}")
        for src in [a.source] if a.source else [x for x in ORDER if x != "pagerduty" or a.all]:
            print(_c("1", f"-- {src}"))
            for stmt in statements(src, masked, placeholders=False):
                print(stmt + ";\n")
        print(_c("2", "Dry run (secrets masked). Re-run with --yes to execute these statements on your Zetaris instance."))
        return
    if not SETTINGS.zetaris_configured:
        raise SystemExit("Zetaris is not configured. Set ZETARIS_ORG_ID and ZETARIS_API_KEY (+ ZETARIS_REST_URL or "
                         "ZETARIS_BASE_URL) in .env. See docs/ZETARIS_SETUP.md.")
    z = ZetarisFederation(SETTINGS)
    if a.action == "register":
        sources = [a.source] if a.source else [s for s in ORDER if s != "pagerduty" or a.all]
        for src in sources:
            print(_c("1", f"-- {src}"))
            for stmt in statements(src, SETTINGS, placeholders=False):
                first = stmt.split("\n")[0]
                try:
                    z.admin(stmt)
                    print(_c("32", "ok   ") + first)
                except FederationError as e:
                    if "already exist" in str(e).lower():
                        print(_c("33", "skip ") + first + "  (already exists)")
                    else:
                        print(_c("31", "FAIL ") + first + f"\n     {str(e)[:300]}")
                        raise SystemExit(1)
        return
    if a.action == "check":
        st = z.status()
        print(f"Zetaris {st.get('route')} at {st.get('endpoint')}: " + ("connected" if st.get("connected") else f"NOT connected: {st.get('error')}"))
        if not st.get("connected"):
            raise SystemExit(1)
        ensure_data()
        local = LocalFederation(SETTINGS.seed_dir, {t.source for t in TABLES})
        want = local.counts()
        ok = True
        for t in TABLES:
            try:
                got = z.query(f"SELECT COUNT(*) AS n FROM {t.qualified}", numeric=("n",)).first("n")
            except FederationError as e:
                got = f"error: {str(e)[:80]}"
            match = got == want.get(t.qualified)
            ok &= match or t.optional
            mark = _c("32", "ok  ") if match else (_c("2", "--  ") if t.optional else _c("31", "DIFF"))
            print(f"{mark} {t.qualified:<30} zetaris={got!s:<10} snapshot={want.get(t.qualified)}")
        cat = z.catalog()
        print(f"Catalog discovery: {len(cat)} tables visible to the Cartographer")
        raise SystemExit(0 if ok else 1)


def cmd_memory(a) -> None:
    from .agents.orchestrator import namespace_for
    from .meterless.client import Meterless, MeterlessUnavailable
    fed = _fed(None)
    ns = a.namespace or namespace_for(fed)
    m = Meterless(ns)
    try:
        h = m.health()
    except MeterlessUnavailable as e:
        raise SystemExit(str(e))
    if a.action == "stats":
        print(json.dumps({"bridge": h, "namespace": ns, "hmem": m.hmem_stats(), "world_model": m.wm_stats()}, indent=1))
    elif a.action == "reset":
        print(json.dumps(m.reset(), indent=1))
        idx = SETTINGS.state_dir / f"hmem-index-{ns}.json"
        idx.unlink(missing_ok=True)
        print(f"Memory for {ns} cleared.")


def cmd_doctor(a) -> None:
    from .federation import FederationError, ZetarisFederation
    from .llm.client import get_llm
    from .llm.embeddings import get_embedder
    from .meterless.client import Meterless, MeterlessUnavailable, _node_ok
    ok = lambda b: _c("32", "ok  ") if b else _c("31", "MISS")  # noqa: E731
    warn = _c("33", "info")
    print(f"{ok(sys.version_info >= (3, 10))} Python {sys.version.split()[0]} (3.10+)")
    try:
        import starlette  # noqa: F401
        import uvicorn  # noqa: F401
        print(f"{ok(True)} starlette + uvicorn installed")
    except ImportError:
        print(f"{ok(False)} pip install -r requirements.txt")
    node = shutil.which("node")
    print(f"{ok(bool(node and _node_ok(node)))} Node.js 22.7+ for the Meterless bridge ({node or 'not found'})")
    vend = (ROOT / "meterless-bridge" / "vendor" / "hmem" / "src" / "index.ts").exists()
    print(f"{ok(vend)} Meterless H-MEM + World Model engines vendored" + ("" if vend else ": cd meterless-bridge && npm run setup"))
    root = SETTINGS.seed_dir
    print(f"{ok((root / 'meta.json').exists())} Company data for seed {SETTINGS.seed} ({root})")
    try:
        from .agents.orchestrator import namespace_for
        from .federation import LocalFederation
        ns = namespace_for(LocalFederation(root)) if (root / "meta.json").exists() else "acme-seed-42"
        h = Meterless(ns).health()
        print(f"{ok(True)} Meterless bridge {SETTINGS.meterless_url} (engines @ {str(h.get('pinnedCommit', ''))[:12]}, Node {h.get('node', '')})")
    except MeterlessUnavailable as e:
        print(f"{ok(False)} Meterless bridge: {e}")
    if SETTINGS.zetaris_configured:
        st = ZetarisFederation(SETTINGS).status()
        print(f"{ok(st.get('connected'))} Zetaris {st.get('route')} at {st.get('endpoint')}"
              + ("" if st.get("connected") else f": {st.get('error', '')[:160]}"))
    else:
        print(f"{warn} Zetaris not configured: agents use the local snapshot. See docs/ZETARIS_SETUP.md")
    print(f"{ok(True) if get_llm().s.llm_enabled else warn} LLM: {get_llm().label}")
    print(f"{ok(True) if get_embedder().s.embed_enabled else warn} Embeddings: {get_embedder().label}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m lastday", description="Last Day: know what your company forgets before someone leaves.")
    p.add_argument("--seed", type=int, help="company dataset (default LASTDAY_SEED or 42)")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate a fictional company")
    g.add_argument("--seeds", type=int, nargs="*")
    g.add_argument("--as-of", help="YYYY-MM-DD (default 2026-10-22)")
    g.set_defaults(fn=cmd_generate)

    s = sub.add_parser("serve", help="web app")
    s.add_argument("--port", type=int)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--engine", choices=["auto", "zetaris", "local"])
    s.set_defaults(fn=cmd_serve)

    r = sub.add_parser("run", help="investigate one departure in the terminal")
    r.add_argument("person", help="employee id or part of a name")
    r.add_argument("--engine", choices=["auto", "zetaris", "local"])
    r.add_argument("--no-memory", action="store_true", help="skip Meterless (H-MEM / World Model)")
    r.add_argument("--sql", action="store_true", help="print every federated query")
    r.add_argument("--quiet", action="store_true")
    r.add_argument("--out", help="output folder (default .lastday/runs/<id>)")
    r.add_argument("--fail", action="append", metavar="SOURCE", help="simulate an outage of a source (repeatable)")
    r.set_defaults(fn=cmd_run)

    q = sub.add_parser("ask", help="successor Q&A from memory + live evidence")
    q.add_argument("question")
    q.add_argument("--engine", choices=["auto", "zetaris", "local"])
    q.set_defaults(fn=cmd_ask)

    pe = sub.add_parser("people", help="employee directory and departures")
    pe.add_argument("--engine", choices=["auto", "zetaris", "local"])
    pe.set_defaults(fn=cmd_people)

    e = sub.add_parser("eval", help="score the agents against planted ground truth")
    e.add_argument("--seeds", type=int, nargs="+", default=[42, 7, 13, 21])
    e.add_argument("--memory", action="store_true", help="run with Meterless memory (also checks conflict detection)")
    e.add_argument("--out", help="write the summary JSON here")
    e.add_argument("--quiet", action="store_true")
    e.set_defaults(fn=cmd_eval)

    sa = sub.add_parser("saas", help="serve the mock Slack/Jira/GitHub/Docs/PagerDuty APIs for Zetaris")
    sa.add_argument("--port", type=int)
    sa.add_argument("--host", default="0.0.0.0")
    sa.set_defaults(fn=cmd_saas)

    z = sub.add_parser("zetaris", help="register the sources in Zetaris and verify them")
    z.add_argument("action", choices=["sql", "register", "check"])
    z.add_argument("--source", help="only this source (hr_pg, slack, jira, github, docs, pagerduty)")
    z.add_argument("--all", action="store_true", help="include the optional PagerDuty source")
    z.add_argument("--yes", action="store_true", help="execute (default is a dry run)")
    z.add_argument("--template", action="store_true", help="write placeholder templates to zetaris/sql/")
    z.set_defaults(fn=cmd_zetaris)

    m = sub.add_parser("memory", help="Meterless memory state")
    m.add_argument("action", choices=["stats", "reset"])
    m.add_argument("--namespace")
    m.set_defaults(fn=cmd_memory)

    d = sub.add_parser("doctor", help="check the setup")
    d.set_defaults(fn=cmd_doctor)

    args = p.parse_args(argv)
    _set_seed(args.seed)
    t0 = time.time()
    try:
        args.fn(args)
    except KeyboardInterrupt:
        print()
    finally:
        if args.cmd in ("run", "eval") and not getattr(args, "quiet", False):
            print(_c("2", f"({time.time() - t0:.1f}s)"))


if __name__ == "__main__":
    main()
