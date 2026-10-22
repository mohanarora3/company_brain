"""Federation layer: Zetaris in production, a SQLite snapshot as the zero-setup fallback."""
from __future__ import annotations

import json
from pathlib import Path

from ..config import SETTINGS, Settings
from .base import Federation, FederationError, QueryResult, TableInfo, in_list, lit
from .local import LocalFederation
from .zetaris import ZetarisFederation

__all__ = ["Federation", "FederationError", "QueryResult", "TableInfo", "lit", "in_list", "connect",
           "LocalFederation", "ZetarisFederation"]


def _registered_file(s: Settings) -> Path:
    return s.state_dir / f"local-registered-seed-{s.seed}.json"


def local_registered(s: Settings) -> set[str] | None:
    p = _registered_file(s)
    if p.exists():
        return set(json.loads(p.read_text()))
    return None


def save_local_registered(s: Settings, sources: set[str]) -> None:
    s.state_dir.mkdir(parents=True, exist_ok=True)
    _registered_file(s).write_text(json.dumps(sorted(sources)))


def connect(s: Settings | None = None, engine: str | None = None) -> Federation:
    """Pick the engine: explicit choice, else Zetaris when configured, else the local snapshot."""
    s = s or SETTINGS
    choice = (engine or s.engine or "auto").lower()
    if choice == "zetaris" or (choice == "auto" and s.zetaris_configured):
        if not s.zetaris_configured:
            raise FederationError("LASTDAY_ENGINE=zetaris but ZETARIS_ORG_ID and an API key (or login) are not set")
        return ZetarisFederation(s)
    return LocalFederation(s.seed_dir, local_registered(s))
