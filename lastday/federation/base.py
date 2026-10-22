"""The federation contract every engine implements.

Agents only ever talk to a Federation: list sources, list tables, describe
columns, run read-only SQL. Zetaris is the production engine; the local SQLite
snapshot is the zero-setup fallback. Both expose the same qualified names.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from .governance import check_sql


@dataclass
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    engine: str
    elapsed_ms: float
    note: str = ""

    def __len__(self) -> int:
        return len(self.rows)

    def first(self, key: str, default: Any = None) -> Any:
        return self.rows[0].get(key, default) if self.rows else default

    def col(self, key: str) -> list[Any]:
        return [r.get(key) for r in self.rows]


@dataclass
class TableInfo:
    source: str
    name: str
    columns: list[dict] = field(default_factory=list)     # [{"name":..., "type":...}]
    kind: str = ""                                        # rest | jdbc | view | file
    detail: str = ""                                      # endpoint, path, description
    discovered_via: str = ""

    @property
    def qualified(self) -> str:
        return f"{self.source}.{self.name}"


class FederationError(RuntimeError):
    pass


class Federation:
    engine = "base"

    def status(self) -> dict:
        raise NotImplementedError

    def catalog(self) -> list[TableInfo]:
        raise NotImplementedError

    def _execute(self, sql: str, columns: list[str] | None) -> tuple[list[str], list[dict]]:
        raise NotImplementedError

    def inject_failure(self, source: str, on: bool = True) -> dict:
        """Demo hook: make one source fail, the way a SaaS outage looks to the federation."""
        failing = self.__dict__.setdefault("_failing", set())
        (failing.add if on else failing.discard)(source)
        return {"failing": sorted(failing)}

    @property
    def failing(self) -> list[str]:
        return sorted(self.__dict__.get("_failing", set()))

    def query(self, sql: str, columns: list[str] | None = None, numeric: tuple = ()) -> QueryResult:
        """Run one governed, read-only statement. Numeric columns are coerced (Zetaris returns strings)."""
        sql = " ".join(sql.split())
        check_sql(sql)
        for src in self.failing:
            if re.search(rf"\b{src}\.[a-z_]", sql, re.I):
                raise FederationError(f"{src} unavailable: upstream API returned 503 (injected outage)")
        t0 = time.perf_counter()
        cols, rows = self._execute(sql, columns)
        if numeric:
            for r in rows:
                for k in numeric:
                    if k in r:
                        r[k] = to_number(r[k])
        for r in rows:
            for k, v in r.items():
                if isinstance(v, str) and v in ("null", "NULL", "None"):
                    r[k] = None
        return QueryResult(sql, cols, rows, self.engine, round((time.perf_counter() - t0) * 1000, 1))


def to_number(v: Any) -> Any:
    if v is None or isinstance(v, (int, float)):
        return v
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return int(f) if f.is_integer() and "e" not in str(v).lower() and "." not in str(v) else f


def lit(value: Any) -> str:
    """SQL string literal, quote-escaped. Agents never interpolate raw values."""
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def in_list(values) -> str:
    vals = [lit(v) for v in values if v is not None]
    return "(" + ", ".join(vals or ["NULL"]) + ")"


_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def ident(name: str) -> str:
    if not _IDENT.match(name or ""):
        raise FederationError(f"unsafe identifier: {name!r}")
    return name


def select_aliases(sql: str) -> list[str]:
    """Output column names of a top-level SELECT, for engines that return rows without headers."""
    s = sql.strip()
    m = re.match(r"(?is)^\s*(?:with\s.+?\)\s*)?select\s+(distinct\s+)?", s)
    if not m:
        return []
    depth, i, start, items = 0, m.end(), m.end(), []
    low = s.lower()
    while i < len(s):
        c = s[i]
        if c in "'\"`":
            j = s.find(c, i + 1)
            i = len(s) if j == -1 else j + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif depth == 0 and c == ",":
            items.append(s[start:i])
            start = i + 1
        elif depth == 0 and low.startswith("from", i) and (i == 0 or not low[i - 1].isalnum()) and \
                (i + 4 >= len(low) or not low[i + 4].isalnum() and low[i + 4] != "_"):
            items.append(s[start:i])
            break
        i += 1
    else:
        items.append(s[start:])
    out = []
    for it in items:
        it = it.strip()
        m2 = re.search(r"(?i)\bas\s+`?([A-Za-z_][A-Za-z0-9_]*)`?\s*$", it)
        if m2:
            out.append(m2.group(1))
        else:
            tok = re.split(r"[\s.]", it)[-1].strip("`")
            out.append(tok)
    return out
