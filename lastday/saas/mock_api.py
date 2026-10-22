"""Acme Pay's SaaS tools, served as HTTP APIs that Zetaris registers as REST tables.

    python -m lastday saas            # http://localhost:8787

Each route returns the same JSON shape the real product's API returns
(Slack `{"ok": true, "messages": [...]}`, Jira `{"issues": [...]}`, ...), from
the generated snapshot in data/seed-N/. Requests need `Authorization: Bearer
<SAAS_TOKEN>`, like the real APIs need a token.

`POST /admin/fail?source=jira&mode=502` makes one system fail, so the demo can
show agents retrying, re-planning around a missing source and lowering their
confidence. `POST /admin/fail?source=jira&mode=off` restores it.
"""
from __future__ import annotations

import json
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from ..config import SETTINGS
from ..federation.manifest import TABLES

FAILING: dict[str, str] = {}


def _load(seed_dir: Path, rel: str) -> dict:
    return json.loads((seed_dir / rel).read_text(encoding="utf-8"))


def make_app(seed_dir: Path | None = None, token: str | None = None) -> Starlette:
    seed_dir = Path(seed_dir or SETTINGS.seed_dir)
    token = token or SETTINGS.saas_token
    cache: dict[str, dict] = {}

    def authorized(request: Request) -> bool:
        return request.headers.get("authorization", "") == f"Bearer {token}"

    def endpoint_for(t):
        async def handler(request: Request):
            if not authorized(request):
                return JSONResponse({"ok": False, "error": "invalid_auth"}, status_code=401)
            mode = FAILING.get(t.source)
            if mode:
                code = int(mode) if mode.isdigit() else 503
                return JSONResponse({"ok": False, "error": f"{t.source} unavailable (injected)"}, status_code=code)
            if t.file not in cache:
                cache[t.file] = _load(seed_dir, t.file)
            payload = cache[t.file]
            limit = request.query_params.get("limit")
            if limit and limit.isdigit():
                payload = dict(payload)
                payload[t.root] = payload[t.root][: int(limit)]
            return JSONResponse(payload)
        return handler

    async def page_markdown(request: Request):
        if not authorized(request):
            return JSONResponse({"error": "invalid_auth"}, status_code=401)
        p = seed_dir / "docs" / f"{request.path_params['page_id']}.md"
        if not p.exists():
            return JSONResponse({"error": "not found"}, status_code=404)
        return PlainTextResponse(p.read_text(encoding="utf-8"), media_type="text/markdown")

    async def fail(request: Request):
        source = request.query_params.get("source", "")
        mode = request.query_params.get("mode", "503")
        if mode in ("off", "0", "none"):
            FAILING.pop(source, None)
        else:
            FAILING[source] = mode
        return JSONResponse({"failing": FAILING})

    async def health(request: Request):
        meta = _load(seed_dir, "meta.json")
        return JSONResponse({"ok": True, "seed": meta["seed"], "as_of": meta["as_of"], "failing": FAILING,
                             "endpoints": [t.endpoint for t in TABLES if t.kind == "rest"]})

    routes = [Route(t.endpoint, endpoint_for(t), methods=["GET"]) for t in TABLES if t.kind == "rest"]
    routes += [
        Route("/docs/wiki/pages/{page_id}.md", page_markdown, methods=["GET"]),
        Route("/admin/fail", fail, methods=["POST"]),
        Route("/healthz", health, methods=["GET"]),
    ]
    return Starlette(routes=routes)


def serve(port: int | None = None, host: str = "0.0.0.0") -> None:
    import uvicorn
    uvicorn.run(make_app(), host=host, port=port or SETTINGS.saas_port, log_level="warning")
