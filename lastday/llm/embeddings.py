"""Text embeddings: NVIDIA NIM retrieval embeddings, with a local fallback.

NIM model default: nvidia/llama-3.2-nv-embedqa-1b-v2 (asymmetric: passages and
queries are embedded with different input_type). Used to match Slack threads,
tickets and wiki pages to systems when nothing links them explicitly, to rank
evidence for the successor Q&A, and to compare candidate successors.

Fallback: hashed bag-of-words vectors (pure Python), so everything runs offline.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import SETTINGS, Settings

DIM = 512
_WORD = re.compile(r"[a-z0-9]+")
STOP = set("the a an and or of to in on for is it be at by with as this that are was were from not do does did "
           "we you i our they them their its if then so but can could should would will about into over".split())


def tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall((text or "").lower()) if w not in STOP and len(w) > 1]


def _hash_vec(text: str) -> list[float]:
    v = [0.0] * DIM
    toks = tokens(text)
    grams = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
    for g in grams:
        h = int(hashlib.md5(g.encode()).hexdigest()[:8], 16)
        v[h % DIM] += 1.0 if (h >> 9) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


class Embedder:
    def __init__(self, s: Settings | None = None):
        self.s = s or SETTINGS
        self._cache: dict[tuple, list[float]] = {}
        self._lock = threading.Lock()
        self.remote_ok = self.s.embed_enabled
        self.calls = 0
        self.last_error = ""

    @property
    def label(self) -> str:
        return f"NVIDIA NIM · {self.s.embed_model}" if self.remote_ok else "local hashed vectors (no NVIDIA key)"

    def _remote(self, texts: list[str], input_type: str) -> list[list[float]]:
        body = {"input": [t[:4000] for t in texts], "model": self.s.embed_model, "input_type": input_type,
                "encoding_format": "float", "truncate": "END"}
        req = Request(self.s.embed_base_url.rstrip("/") + "/embeddings", data=json.dumps(body).encode(), method="POST",
                      headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.s.embed_api_key}"})
        with urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        self.calls += 1
        vecs = [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
        out = []
        for v in vecs:
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out

    def embed(self, texts: list[str], kind: str = "passage") -> list[list[float]]:
        """kind: 'passage' for documents, 'query' for questions (NIM retrieval models are asymmetric)."""
        out: list[list[float] | None] = []
        missing: list[int] = []
        with self._lock:
            for i, t in enumerate(texts):
                hit = self._cache.get((kind, t))
                out.append(hit)
                if hit is None:
                    missing.append(i)
        if missing and self.remote_ok:
            try:
                for start in range(0, len(missing), 48):
                    idx = missing[start:start + 48]
                    vecs = self._remote([texts[i] for i in idx], kind)
                    for i, v in zip(idx, vecs):
                        out[i] = v
            except (HTTPError, URLError, OSError, TimeoutError, KeyError, ValueError) as e:
                # Never mix vector spaces: drop to the local embedder for everything from now on.
                self.remote_ok = False
                self.last_error = str(e)
                with self._lock:
                    self._cache.clear()
                out = [None] * len(texts)
                missing = list(range(len(texts)))
        for i in missing:
            if out[i] is None:
                out[i] = _hash_vec(texts[i])
        with self._lock:
            for i in missing:
                self._cache[(kind, texts[i])] = out[i]  # type: ignore[assignment]
        return out  # type: ignore[return-value]

    def similarity(self, query: str, passages: list[str]) -> list[float]:
        q = self.embed([query], "query")[0]
        ps = self.embed(passages, "passage")
        if len(q) != len(ps[0]) if ps else False:
            return [0.0] * len(passages)
        return [cosine(q, p) for p in ps]


_emb: Embedder | None = None


def get_embedder() -> Embedder:
    global _emb
    if _emb is None:
        _emb = Embedder()
    return _emb
