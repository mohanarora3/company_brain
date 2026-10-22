"""Query governance applied before anything reaches an engine.

Zetaris already exposes only the governed HR directory view. This guard is the
second layer: agents may only run read-only statements, and any statement that
names a blocked table or a sensitive HR column is refused and logged.
"""
from __future__ import annotations

import re

from .manifest import BLOCKED_COLUMNS, BLOCKED_TABLES

READ_ONLY = re.compile(r"^\s*(select|with|show|describe)\b", re.I)
WRITE_WORDS = re.compile(r"\b(insert|update|delete|drop|create|alter|grant|revoke|register|upsert|truncate|merge)\b", re.I)


class GovernanceError(PermissionError):
    pass


def _strip_literals(sql: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def check_sql(sql: str) -> None:
    if not READ_ONLY.match(sql):
        raise GovernanceError("agents may only run SELECT, WITH, SHOW or DESCRIBE statements")
    body = _strip_literals(sql)
    if WRITE_WORDS.search(body) and not body.lower().lstrip().startswith(("show", "describe")):
        raise GovernanceError("write keywords are not allowed in agent queries")
    low = body.lower()
    for t in BLOCKED_TABLES:
        if re.search(rf"\b{re.escape(t)}\b", low):
            raise GovernanceError(f"{t} is not exposed to agents; use hr_pg.employees_directory")
    for c in BLOCKED_COLUMNS:
        if re.search(rf"\b{c}\b", low):
            raise GovernanceError(f"column {c} is sensitive HR data and is blocked by policy")


def policy() -> dict:
    return {
        "read_only": True,
        "blocked_tables": sorted(BLOCKED_TABLES),
        "blocked_columns": sorted(BLOCKED_COLUMNS),
        "hr_exposure": "hr_pg.employees_directory (governed view), hr_pg.departures, hr_pg.access_grants",
    }
