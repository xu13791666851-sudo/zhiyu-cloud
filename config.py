"""Runtime configuration for ZhiYu.

All secrets and deployment-specific values should come from environment
variables. A local .env file is loaded automatically for development.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def _load_dotenv(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str = "") -> list[str]:
    value = _env(name, default) or ""
    return [item.strip() for item in value.split(",") if item.strip()]


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, default)
    if value is None:
        return None
    return value.strip().strip('"').strip("'")


_load_dotenv()


# LLM
HUNYUAN_API_KEY = _env("HUNYUAN_API_KEY", "") or ""
HUNYUAN_BASE_URL = _env(
    "HUNYUAN_BASE_URL",
    "https://api.hunyuan.cloud.tencent.com/v1",
) or "https://api.hunyuan.cloud.tencent.com/v1"
HUNYUAN_MODEL = _env("HUNYUAN_MODEL", "hunyuan-lite") or "hunyuan-lite"


# Retrieval providers
RAGFLOW_API_URL = _env("RAGFLOW_API_URL", "") or ""
RAGFLOW_API_KEY = _env("RAGFLOW_API_KEY", "") or ""
RAGFLOW_KB_ID = _env("RAGFLOW_KB_ID", "") or ""
USE_RAGFLOW_RETRIEVAL = _env_bool(
    "USE_RAGFLOW_RETRIEVAL",
    bool(RAGFLOW_API_URL and RAGFLOW_API_KEY and RAGFLOW_KB_ID),
)

DIFY_API_URL = _env("DIFY_API_URL", "") or ""
DIFY_API_KEY = _env("DIFY_API_KEY", "") or ""
DIFY_DATASET_ID = _env("DIFY_DATASET_ID", "") or ""
USE_DIFY_RETRIEVAL = _env_bool(
    "USE_DIFY_RETRIEVAL",
    bool(DIFY_API_URL and DIFY_API_KEY and DIFY_DATASET_ID),
)


# Server
ALLOWED_ORIGINS = _env_list(
    "ALLOWED_ORIGINS",
    "http://localhost:3001,http://127.0.0.1:3001",
)
DATABASE_PATH = _env("DATABASE_PATH", str(BASE_DIR / "zhiyu.db")) or str(BASE_DIR / "zhiyu.db")
DATABASE_URL = _env("DATABASE_URL", "") or ""


def load_knowledge_base() -> list[dict]:
    kb_path = BASE_DIR / "knowledge_base.json"
    if not kb_path.exists():
        return []
    with kb_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


KNOWLEDGE_BASE = load_knowledge_base()
