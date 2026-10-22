"""Test settings: isolated state, a separate Meterless bridge port, no LLM or embedding calls.

Runs with the standard library only:  python -m unittest discover -s tests -v
(pytest also works: python -m pytest tests)
"""
import os
import tempfile

_STATE = tempfile.mkdtemp(prefix="lastday-test-")
os.environ["LASTDAY_STATE_DIR"] = _STATE
os.environ["METERLESS_BRIDGE_URL"] = "http://127.0.0.1:7178"
os.environ["METERLESS_BRIDGE_PORT"] = "7178"
os.environ["LASTDAY_ENGINE"] = "local"
os.environ["LASTDAY_SEED"] = "42"
# Never call paid or remote APIs from tests, even if the developer's .env has keys.
for k in ("LLM_API_KEY", "NVIDIA_API_KEY", "EMBED_API_KEY", "ZETARIS_API_KEY", "ZETARIS_ORG_ID",
          "ZETARIS_USERNAME", "ZETARIS_PASSWORD", "ZETARIS_REST_URL", "ZETARIS_BASE_URL"):
    os.environ[k] = ""
os.environ["LLM_BASE_URL"] = "https://llm.invalid/v1"
