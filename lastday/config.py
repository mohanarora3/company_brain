"""Settings, read from the environment and an optional .env file.

Nothing here is secret by default. Keys live in .env (gitignored); .env.example
documents every variable with a placeholder.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env reader: KEY=VALUE lines, no interpolation, never overrides the real environment."""
    for candidate in [path] if path else [ROOT / ".env", ROOT / ".env.local"]:
        if not candidate or not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)


load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


@dataclass
class Settings:
    # Data
    seed: int = env_int("LASTDAY_SEED", 42)
    data_dir: Path = Path(env("LASTDAY_DATA_DIR", str(ROOT / "data")))
    state_dir: Path = Path(env("LASTDAY_STATE_DIR", str(ROOT / ".lastday")))

    # Federation engine: "zetaris" or "local". "auto" picks Zetaris when it is configured.
    engine: str = env("LASTDAY_ENGINE", "auto")
    zetaris_rest_url: str = env("ZETARIS_REST_URL")              # direct API, e.g. http://localhost:8888/api/v1.0
    zetaris_base_url: str = env("ZETARIS_BASE_URL")              # UI proxy origin, e.g. http://localhost:3000
    zetaris_org_id: str = env("ZETARIS_ORG_ID")
    zetaris_api_key: str = env("ZETARIS_API_KEY")
    zetaris_username: str = env("ZETARIS_USERNAME")
    zetaris_password: str = env("ZETARIS_PASSWORD")
    zetaris_engine_id: str = env("ZETARIS_ENGINE_ID")
    zetaris_limit: int = env_int("ZETARIS_QUERY_LIMIT", 20000)

    # SaaS gateway (mock Slack/Jira/GitHub/Docs/PagerDuty APIs) and HR Postgres, as Zetaris sees them.
    saas_port: int = env_int("SAAS_PORT", 8787)
    saas_public_url: str = env("SAAS_PUBLIC_URL", "http://host.docker.internal:8787")
    saas_token: str = env("SAAS_TOKEN", "lastday-demo-token")
    hr_jdbc_url: str = env("HR_JDBC_URL", "jdbc:postgresql://host.docker.internal:5433/acme_hr")
    hr_pg_user: str = env("HR_PG_USER", "lastday")
    hr_pg_password: str = env("HR_PG_PASSWORD", "lastday")

    # Meterless bridge (H-MEM + World Model engines)
    meterless_url: str = env("METERLESS_BRIDGE_URL", "http://127.0.0.1:7077")
    meterless_autostart: bool = env("METERLESS_AUTOSTART", "1") not in ("0", "false", "no")

    # LLM: any OpenAI-compatible endpoint. Default is NVIDIA NIM.
    llm_base_url: str = env("LLM_BASE_URL", "https://integrate.api.nvidia.com/v1")
    llm_api_key: str = env("LLM_API_KEY") or env("NVIDIA_API_KEY")
    llm_model: str = env("LLM_MODEL", "meta/llama-3.3-70b-instruct")
    llm_timeout: int = env_int("LLM_TIMEOUT", 120)
    llm_extra_headers: str = env("LLM_EXTRA_HEADERS")            # "k: v; k2: v2" (e.g. meterless-app for Meterless Runtime)

    # Embeddings: NVIDIA NIM retrieval embeddings, local hashing fallback.
    embed_base_url: str = env("EMBED_BASE_URL", "https://integrate.api.nvidia.com/v1")
    embed_api_key: str = env("EMBED_API_KEY") or env("NVIDIA_API_KEY")
    embed_model: str = env("EMBED_MODEL", "nvidia/llama-3.2-nv-embedqa-1b-v2")

    port: int = env_int("PORT", 8000)

    @property
    def seed_dir(self) -> Path:
        return self.data_dir / f"seed-{self.seed}"

    @property
    def zetaris_configured(self) -> bool:
        return bool(self.zetaris_org_id and (
            (self.zetaris_rest_url and self.zetaris_api_key) or
            (self.zetaris_base_url and (self.zetaris_api_key or (self.zetaris_username and self.zetaris_password)))))

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key) or "127.0.0.1" in self.llm_base_url or "localhost" in self.llm_base_url

    @property
    def embed_enabled(self) -> bool:
        return bool(self.embed_api_key)


SETTINGS = Settings()


def reload() -> Settings:
    global SETTINGS
    SETTINGS = Settings()
    return SETTINGS
