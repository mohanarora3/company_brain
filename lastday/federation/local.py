"""Local snapshot federation on SQLite (standard library, zero setup).

Used when no Zetaris instance is configured, in tests, and as a fallback when
Zetaris is unreachable. Each source is an attached in-memory database, so the
qualified names are identical to Zetaris: `slack.messages`, `hr_pg.departures`.
Cross-source joins work the same way.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .base import Federation, FederationError, TableInfo
from .manifest import SOURCES, TABLES, Table


def _dig(rec: dict, path: str):
    cur = rec
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    if isinstance(cur, (dict, list)):
        return json.dumps(cur)
    if isinstance(cur, bool):
        return int(cur)
    return cur


class LocalFederation(Federation):
    engine = "local"

    def __init__(self, seed_dir: Path, registered: set[str] | None = None):
        self.seed_dir = Path(seed_dir)
        if not (self.seed_dir / "meta.json").exists():
            raise FederationError(f"no generated data in {self.seed_dir}; run `python -m lastday generate`")
        self.meta = json.loads((self.seed_dir / "meta.json").read_text())
        self._lock = threading.Lock()
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self.registered: set[str] = set()
        for src in SOURCES:
            self._db.execute(f"ATTACH DATABASE ':memory:' AS {src}")
        default = {t.source for t in TABLES if not t.optional}
        for src in sorted(registered if registered is not None else default):
            self.register(src)

    def register(self, source: str) -> list[str]:
        """Load one source's tables, the local equivalent of running its Zetaris registration SQL."""
        loaded = []
        with self._lock:
            for t in [t for t in TABLES if t.source == source]:
                self._load(t)
                loaded.append(t.qualified)
            self.registered.add(source)
        return loaded

    def _load(self, t: Table) -> None:
        payload = json.loads((self.seed_dir / t.file).read_text(encoding="utf-8"))
        records = payload.get(t.root, []) if isinstance(payload, dict) else payload
        cols = list(t.columns)
        types = {"int": "INTEGER", "float": "REAL", "string": "TEXT"}
        self._db.execute(f"DROP TABLE IF EXISTS {t.qualified}")
        self._db.execute(f"CREATE TABLE {t.qualified} ({', '.join(f'{c.name} {types[c.type]}' for c in cols)})")
        rows = [tuple(_dig(r, c.json_path) for c in cols) for r in records]
        self._db.executemany(f"INSERT INTO {t.qualified} VALUES ({', '.join('?' for _ in cols)})", rows)

    def status(self) -> dict:
        return {"engine": "local", "label": "Local snapshot (SQLite)", "connected": True,
                "seed": self.meta.get("seed"), "as_of": self.meta.get("as_of"),
                "sources": sorted(self.registered)}

    def catalog(self) -> list[TableInfo]:
        out = []
        with self._lock:
            for src in sorted(self.registered):
                names = [r[0] for r in self._db.execute(
                    f"SELECT name FROM {src}.sqlite_master WHERE type='table' ORDER BY name")]
                for name in names:
                    cols = [{"name": r[1], "type": (r[2] or "TEXT").lower()}
                            for r in self._db.execute(f"PRAGMA {src}.table_info({name})")]
                    spec = next((t for t in TABLES if t.source == src and t.name == name), None)
                    out.append(TableInfo(src, name, cols, spec.kind if spec else "table",
                                         spec.description if spec else "", "sqlite_master"))
        return out

    def _execute(self, sql: str, columns: list[str] | None):
        with self._lock:
            try:
                cur = self._db.execute(sql)
            except sqlite3.Error as e:
                raise FederationError(f"local engine: {e}") from e
            names = [d[0] for d in cur.description or []]
            rows = [dict(zip(names, tuple(r))) for r in cur.fetchall()]
        return names, rows

    def counts(self) -> dict[str, int]:
        out = {}
        with self._lock:
            for t in TABLES:
                if t.source in self.registered:
                    out[t.qualified] = self._db.execute(f"SELECT COUNT(*) FROM {t.qualified}").fetchone()[0]
        return out
