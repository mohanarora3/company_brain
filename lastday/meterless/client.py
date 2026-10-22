"""Python client for the Meterless bridge (H-MEM memory + World Model engines).

The bridge is a small Node process (meterless-bridge/server.ts) that runs the
Meterless reference engines. The client starts it on demand when
METERLESS_AUTOSTART is on, so `python -m lastday serve` is still one command.
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import ROOT, SETTINGS, Settings

BRIDGE_DIR = ROOT / "meterless-bridge"
_proc: subprocess.Popen | None = None
_log = None
_start_lock = threading.Lock()


class MeterlessUnavailable(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _node_ok(node: str) -> bool:
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
        major, minor = (int(x) for x in out.lstrip("v").split(".")[:2])
        return (major, minor) >= (22, 7)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def start_bridge(s: Settings) -> None:
    """Start the bridge as a child process (it is stopped when Python exits)."""
    global _proc
    with _start_lock:
        if _proc and _proc.poll() is None:
            return
        node = shutil.which("node")
        if not node or not _node_ok(node):
            raise MeterlessUnavailable("Node.js 22.7+ is required for the Meterless bridge (node not found or too old)")
        if not (BRIDGE_DIR / "vendor" / "hmem" / "src" / "index.ts").exists():
            raise MeterlessUnavailable("Meterless engines are not vendored yet: cd meterless-bridge && npm run setup")
        env = dict(os.environ)
        env.setdefault("METERLESS_STATE_DIR", str(s.state_dir / "meterless"))
        env.setdefault("METERLESS_BRIDGE_PORT", s.meterless_url.rsplit(":", 1)[-1].strip("/"))
        s.state_dir.mkdir(parents=True, exist_ok=True)
        global _log
        _log = open(s.state_dir / "meterless-bridge.log", "a")
        _proc = subprocess.Popen([node, "--experimental-transform-types", "--no-warnings", "server.ts"],
                                 cwd=BRIDGE_DIR, env=env, stdout=_log, stderr=subprocess.STDOUT)
        atexit.register(stop_bridge)


def stop_bridge() -> None:
    global _proc, _log
    if _proc and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _proc = None
    if _log:
        _log.close()
        _log = None


class Meterless:
    """One namespace (= one company dataset) in H-MEM and the World Model."""

    def __init__(self, namespace: str, s: Settings | None = None):
        self.s = s or SETTINGS
        self.ns = namespace
        self.base = self.s.meterless_url.rstrip("/")
        self._health: dict | None = None

    # ------------------------------------------------------------ plumbing
    def _call(self, path: str, body: Any = None, timeout: float = 30) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.base + path, data=data, method="POST" if body is not None else "GET",
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode() or "null")
        except HTTPError as e:
            raise MeterlessUnavailable(f"bridge {path}: HTTP {e.code} {e.read(300).decode(errors='replace')}") from e
        except (URLError, OSError, TimeoutError) as e:
            raise MeterlessUnavailable(f"bridge not reachable at {self.base}: {getattr(e, 'reason', e)}") from e

    def health(self, start: bool = True) -> dict:
        try:
            self._health = self._call("/health", timeout=3)
            return self._health
        except MeterlessUnavailable:
            if not (start and self.s.meterless_autostart):
                raise
        start_bridge(self.s)
        for _ in range(40):
            time.sleep(0.25)
            try:
                self._health = self._call("/health", timeout=2)
                return self._health
            except MeterlessUnavailable:
                continue
        raise MeterlessUnavailable("the Meterless bridge did not start; see .lastday/meterless-bridge.log")

    def available(self) -> bool:
        try:
            self.health()
            return True
        except MeterlessUnavailable:
            return False

    # ---------------------------------------------------------------- H-MEM
    def remember(self, content: str, source: str, *, tags: list[str] | None = None, confidence: float = 0.7,
                 type: str = "factual", origin: str = "document", label: str = "", refs: list[str] | None = None,
                 mission: str | None = None, layer: str | None = None) -> dict:
        return self._call(f"/hmem/{self.ns}/add", {
            "content": content, "source": source, "tags": tags or [], "confidence": confidence, "type": type,
            "layer": layer, "missionId": mission,
            "provenance": {"origin": origin, "label": label or source, "refs": refs or []}})

    def recall(self, query: str, top_n: int = 6, threshold: float = 0.12) -> dict:
        return self._call(f"/hmem/{self.ns}/query", {"query": query, "topN": top_n, "threshold": threshold})

    def feedback(self, memory_id: str, kind: str) -> dict:
        return self._call(f"/hmem/{self.ns}/feedback", {"id": memory_id, "kind": kind})

    def audit(self, memory_id: str) -> dict:
        return self._call(f"/hmem/{self.ns}/audit/{memory_id}")

    def memories(self, tag: str | None = None, limit: int = 500) -> list:
        q = f"?limit={limit}" + (f"&tag={tag}" if tag else "")
        return self._call(f"/hmem/{self.ns}/memories{q}")

    def conflicts(self, auto_resolve: bool = False) -> dict:
        return self._call(f"/hmem/{self.ns}/conflicts", {"autoResolve": auto_resolve})

    def sleep(self, execute: bool = False) -> dict:
        return self._call(f"/hmem/{self.ns}/sleep", {"execute": execute})

    def hmem_stats(self) -> dict:
        return self._call(f"/hmem/{self.ns}/stats")

    # ---------------------------------------------------------- World Model
    def world(self, ops: list[dict]) -> list:
        out = []
        for i in range(0, len(ops), 200):
            out += self._call(f"/wm/{self.ns}/batch", {"ops": ops[i:i + 200]}, timeout=120)["results"]
        return out

    def neighbors(self, entity_id: str, via: str | None = None) -> list:
        q = f"?id={entity_id}" + (f"&via={via}" if via else "")
        return self._call(f"/wm/{self.ns}/neighbors{q}")

    def incoming(self, entity_id: str, via: str | None = None) -> list:
        q = f"?id={entity_id}" + (f"&via={via}" if via else "")
        return self._call(f"/wm/{self.ns}/incoming{q}")

    def facts(self, entity_id: str) -> list:
        return self._call(f"/wm/{self.ns}/facts/{entity_id}")

    def relationships(self, rel_type: str | None = None, entity_id: str | None = None) -> list:
        q = []
        if rel_type:
            q.append(f"type={rel_type}")
        if entity_id:
            q.append(f"id={entity_id}")
        return self._call(f"/wm/{self.ns}/relationships" + ("?" + "&".join(q) if q else ""))

    def wm_audit(self, limit: int = 100) -> list:
        return self._call(f"/wm/{self.ns}/audit?limit={limit}")

    def wm_stats(self) -> dict:
        return self._call(f"/wm/{self.ns}/stats")

    def reset(self) -> dict:
        return self._call(f"/reset/{self.ns}", {})


def prov(kind: str, by: str, at: str | None = None, url: str | None = None, run_id: str | None = None) -> dict:
    """World Model provenance: every write says where it came from. No provenance, no write."""
    p = {"kind": kind, "by": by, "at": at or now_iso()}
    if url:
        p["url"] = url
    if run_id:
        p["runId"] = run_id
    return p
