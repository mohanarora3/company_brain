"""LLM access through any OpenAI-compatible endpoint.

Default: NVIDIA NIM (https://integrate.api.nvidia.com/v1) with NVIDIA_API_KEY.
Also works with the Meterless Runtime (local models, `meterless/auto`), xAI, OpenAI
or a self-hosted NIM: set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL.

Without a key every agent still runs: wording falls back to deterministic
templates over the same evidence, and the UI says so. The reasoning (queries,
scores, critique, escalation) never depends on the LLM.
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import SETTINGS, Settings


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, s: Settings | None = None):
        self.s = s or SETTINGS
        self.calls = 0
        self.failures = 0
        self.last_error = ""
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.s.llm_enabled and self.failures < 3

    @property
    def label(self) -> str:
        if not self.s.llm_enabled:
            return "offline templates (no LLM key)"
        host = re.sub(r"^https?://", "", self.s.llm_base_url).split("/")[0]
        provider = "NVIDIA NIM" if "nvidia" in host else "Meterless Runtime" if self.s.llm_model.startswith("meterless/") else host
        return f"{provider} · {self.s.llm_model}"

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.s.llm_api_key:
            h["Authorization"] = f"Bearer {self.s.llm_api_key}"
        for part in (self.s.llm_extra_headers or "").split(";"):
            if ":" in part:
                k, v = part.split(":", 1)
                h[k.strip()] = v.strip()
        return h

    def chat(self, system: str, user: str, *, max_tokens: int = 900, temperature: float = 0.2) -> str:
        if not self.enabled:
            raise LLMError("LLM disabled")
        body = {"model": self.s.llm_model, "temperature": temperature, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        url = self.s.llm_base_url.rstrip("/") + "/chat/completions"
        last = ""
        for attempt in range(3):
            req = Request(url, data=json.dumps(body).encode(), method="POST", headers=self._headers())
            try:
                with urlopen(req, timeout=self.s.llm_timeout) as resp:
                    data = json.loads(resp.read().decode())
                with self._lock:
                    self.calls += 1
                msg = data["choices"][0]["message"]
                text = msg.get("content") or ""
                return re.sub(r"(?s)<think>.*?</think>", "", text).strip()
            except HTTPError as e:
                last = f"HTTP {e.code}: {e.read(300).decode(errors='replace')}"
                if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                break
            except (URLError, OSError, TimeoutError, KeyError, ValueError) as e:
                last = str(e)
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
        with self._lock:
            self.failures += 1
            self.last_error = last
        raise LLMError(last)

    def json(self, system: str, user: str, **kw) -> Any:
        text = self.chat(system + "\nRespond with JSON only. No prose, no code fences.", user, **kw)
        return extract_json(text)


def extract_json(text: str) -> Any:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError("model did not return JSON")


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm


def reset_llm() -> None:
    global _llm
    _llm = None
