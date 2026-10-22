"""Zetaris federation client.

Talks to a Zetaris instance over its HTTP API and runs Lightning SQL against the
sources registered there (see zetaris/sql/). Two routes are supported, matching
the official getting-started helpers:

  rest   POST {ZETARIS_REST_URL}/sql-editor/sqls/run          (direct API, :8888/api/v1.0)
  proxy  POST {ZETARIS_BASE_URL}/api/proxy/sql-editor/sqls/run-query   (UI proxy, :3000)

Both use a GUI-created API key (Bearer), the numeric organisation id
(X-Org-ID) and a fresh X-Request-ID per call. The proxy route can also log in
with username and password.

Zetaris returns values as strings and does not always include column headers,
so result columns come from the response when present, otherwise from the
query's own SELECT aliases (every agent query aliases its columns).
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import Settings
from .base import Federation, FederationError, TableInfo, select_aliases
from .manifest import BY_NAME, TABLES

HEADER_KEYS = ("columns", "columnNames", "column_names", "header", "headers", "fields", "schema", "meta", "metadata")


class ZetarisFederation(Federation):
    engine = "zetaris"

    def __init__(self, s: Settings, cache_ttl: float = 300.0):
        self.s = s
        self.mode = "rest" if (s.zetaris_rest_url and s.zetaris_api_key) else "proxy"
        self._token: str | None = s.zetaris_api_key or None
        self._cache: dict[str, tuple[float, list, list]] = {}
        self._cache_ttl = cache_ttl
        self._lock = threading.Lock()
        self.last_raw_keys: list[str] = []
        self.version: str = ""

    # ---------------------------------------------------------------- HTTP
    def _url(self) -> str:
        if self.mode == "rest":
            return self.s.zetaris_rest_url.rstrip("/") + "/sql-editor/sqls/run"
        return self.s.zetaris_base_url.rstrip("/") + "/api/proxy/sql-editor/sqls/run-query"

    def _login(self) -> str:
        body = json.dumps({"username": self.s.zetaris_username, "password": self.s.zetaris_password}).encode()
        req = Request(self.s.zetaris_base_url.rstrip("/") + "/api/auth/login", data=body, method="POST",
                      headers={"Content-Type": "application/json", "X-Request-ID": str(uuid.uuid4())})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        token = data.get("idToken") or data.get("token") or data.get("accessToken") if isinstance(data, dict) else None
        if not token:
            m = re.search(r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", json.dumps(data))
            token = m.group(0) if m else None
        if not token:
            raise FederationError("Zetaris login did not return a token")
        return token

    def _post(self, sql: str, limit: int) -> Any:
        if not self._token:
            self._token = self._login()
        if self.mode == "rest":
            body = {"queryId": str(uuid.uuid4()), "sql": sql, "source": "SqlEditor", "limit": limit}
        else:
            body = {"sql": sql, "limit": limit}
            if self.s.zetaris_engine_id:
                body["engineId"] = self.s.zetaris_engine_id
        req = Request(self._url(), data=json.dumps(body).encode(), method="POST", headers={
            "Authorization": f"Bearer {self._token}", "X-Org-ID": self.s.zetaris_org_id,
            "X-Request-ID": str(uuid.uuid4()), "Content-Type": "application/json"})
        last: Exception | None = None
        for attempt in range(3):
            try:
                with urlopen(req, timeout=180) as resp:
                    text = resp.read().decode() or "null"
                return json.loads(text)
            except HTTPError as e:
                detail = e.read(600).decode(errors="replace")
                if e.code in (502, 503, 504) and attempt < 2:
                    last = e
                    time.sleep(1.5 * (attempt + 1))
                    continue
                hint = {401: " (API key rejected: create a new one under Management > API Tokens)",
                        400: " (check ZETARIS_ORG_ID is the numeric organisation id)"}.get(e.code, "")
                raise FederationError(f"Zetaris HTTP {e.code}{hint}: {' '.join(detail.split())[:300]}") from e
            except (URLError, OSError, TimeoutError) as e:
                last = e
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
        raise FederationError(f"cannot reach Zetaris at {self._url()}: {getattr(last, 'reason', last)}")

    # ------------------------------------------------------------- parsing
    def _parse(self, raw: Any, sql: str, hint: list[str] | None) -> tuple[list[str], list[dict]]:
        payload, header = raw, None
        if isinstance(raw, dict):
            self.last_raw_keys = sorted(raw.keys())
            if isinstance(raw.get("error"), str) or raw.get("status") in ("ERROR", "FAILED"):
                raise FederationError(f"Zetaris query failed: {raw.get('error') or raw.get('message')}")
            for k in HEADER_KEYS:
                if raw.get(k):
                    header = raw[k]
                    break
            payload = raw.get("data", raw.get("rows", raw.get("result", [])))
            if isinstance(payload, dict):
                for k in HEADER_KEYS:
                    if payload.get(k) and header is None:
                        header = payload[k]
                payload = payload.get("rows", payload.get("data", payload.get("records", [])))
        rows = payload if isinstance(payload, list) else []
        if rows and isinstance(rows[0], dict):
            cols = list(rows[0].keys())
            return cols, [dict(r) for r in rows]
        names: list[str] = []
        if header:
            for h in header:
                names.append(h.get("name") or h.get("columnName") or h.get("label") or str(h)
                             if isinstance(h, dict) else str(h))
        if not names:
            names = hint or select_aliases(sql)
        width = max((len(r) for r in rows if isinstance(r, list)), default=len(names))
        if len(names) < width:
            names = names + [f"c{i}" for i in range(len(names), width)]
        return names, [dict(zip(names, r)) for r in rows if isinstance(r, list)]

    def _execute(self, sql: str, columns: list[str] | None):
        now = time.time()
        with self._lock:
            hit = self._cache.get(sql)
            if hit and now - hit[0] < self._cache_ttl:
                return list(hit[1]), [dict(r) for r in hit[2]]
        raw = self._post(sql, self.s.zetaris_limit)
        cols, rows = self._parse(raw, sql, columns)
        with self._lock:
            self._cache[sql] = (now, cols, rows)
        return cols, rows

    def admin(self, sql: str) -> list[list]:
        """Registration statements (CREATE ...). Not available to agents; used by `lastday zetaris register`."""
        raw = self._post(sql, 100)
        cols, rows = self._parse(raw, sql, None)
        return [list(r.values()) for r in rows]

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    # -------------------------------------------------------------- status
    def status(self) -> dict:
        info = {"engine": "zetaris", "label": "Zetaris", "route": self.mode,
                "endpoint": self._url().rsplit("/sql-editor", 1)[0].rsplit("/api/proxy", 1)[0]}
        try:
            r = self.query("SELECT 1 AS one")
            info["connected"] = str(r.first("one")) == "1"
            if not self.version:
                try:
                    v = self._parse(self._post("SHOW SERVER VERSION", 10), "SHOW SERVER VERSION", ["version"])[1]
                    self.version = str(next(iter(v[0].values()))) if v else ""
                except FederationError:
                    self.version = ""
            info["version"] = self.version
            info["response_keys"] = self.last_raw_keys
        except FederationError as e:
            info["connected"] = False
            info["error"] = str(e)
        return info

    # ------------------------------------------------------------- catalog
    def _rows(self, sql: str, hint: list[str]) -> list[dict]:
        try:
            cols, rows = self._parse(self._post(sql, 2000), sql, hint)
            return rows
        except FederationError:
            return []

    def catalog(self) -> list[TableInfo]:
        """Discover what is queryable, the way an operator would in the SQL Editor.

        Convention used by zetaris/sql/: REST sources live in Lightning database `<source>_api`
        as `<table>_raw`, flattened by SchemaStore views `<source>.<table>`. JDBC sources are
        datasources (`hr_pg`). Anything registered later with the same convention is discovered.
        """
        out: list[TableInfo] = []
        seen: set[str] = set()
        dbs = self._rows("SHOW LIGHTNING DATABASES", ["name", "description", "id"])
        for db in dbs:
            dbname = str(db.get("name") or next(iter(db.values()), "")).lower()
            if not dbname.endswith("_api"):
                continue
            source = dbname[: -len("_api")]
            for t in self._rows(f"SHOW LIGHTNING TABLES {dbname}", ["name", "type", "endpoint", "format", "id"]):
                raw_name = str(t.get("name") or next(iter(t.values()), "")).lower()
                view = raw_name[: -len("_raw")] if raw_name.endswith("_raw") else raw_name
                q = f"{source}.{view}"
                if q in seen:
                    continue
                seen.add(q)
                out.append(TableInfo(source, view, self._columns(q), "rest", str(t.get("endpoint") or ""),
                                     f"SHOW LIGHTNING TABLES {dbname}"))
        for ds in self._rows("SHOW DATASOURCES", ["name", "description", "id"]):
            dsname = str(ds.get("name") or next(iter(ds.values()), "")).lower()
            for t in self._rows(f"SHOW DATASOURCE TABLES {dsname}", ["name"]):
                tname = str(t.get("name") or t.get("tableName") or next(iter(t.values()), "")).lower()
                tname = tname.split(".")[-1]
                q = f"{dsname}.{tname}"
                if q in seen or q == "hr_pg.employees":
                    continue
                seen.add(q)
                out.append(TableInfo(dsname, tname, self._columns(q), "jdbc", str(ds.get("description") or ""),
                                     f"SHOW DATASOURCE TABLES {dsname}"))
        return out

    def _columns(self, qualified: str) -> list[dict]:
        rows = self._rows(f"DESCRIBE DATASOURCE TABLE {qualified}", ["col_name", "data_type", "comment"])
        cols = []
        for r in rows:
            vals = list(r.values())
            name = str(r.get("col_name") or r.get("name") or (vals[0] if vals else "")).strip()
            if name and not name.startswith("#"):
                cols.append({"name": name, "type": str(r.get("data_type") or (vals[1] if len(vals) > 1 else ""))})
        if cols:
            return cols
        spec = BY_NAME.get(qualified)
        if spec:
            return [{"name": c.name, "type": c.type} for c in spec.columns]
        return []


def manifest_tables() -> list[str]:
    return [t.qualified for t in TABLES]
