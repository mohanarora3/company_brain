from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

from lastday.config import ROOT, SETTINGS
from lastday.data.generator import write

AS_OF = date(2026, 10, 22)


def seed_dir(seed: int) -> Path:
    root = SETTINGS.data_dir / f"seed-{seed}"
    meta = root / "meta.json"
    if not meta.exists() or json.loads(meta.read_text())["as_of"] != AS_OF.isoformat():
        write(seed, SETTINGS.data_dir, as_of=AS_OF)
    return root


def truth(seed: int) -> dict:
    return json.loads((seed_dir(seed) / "_ground_truth.json").read_text())


def node_ok() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    try:
        v = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout.strip().lstrip("v")
        major, minor = (int(x) for x in v.split(".")[:2])
        return (major, minor) >= (22, 7)
    except (OSError, ValueError):
        return False


def engines_vendored() -> bool:
    return (ROOT / "meterless-bridge" / "vendor" / "hmem" / "src" / "index.ts").exists()
