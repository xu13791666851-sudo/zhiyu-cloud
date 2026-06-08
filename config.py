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
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str = "") -> list[str]:
    value = os.environ.get(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


_load_dotenv()


# LLM
HUNYUAN_API_KEY = os.environ.get("HUNYUAN_API_KEY", "")
HUNYUAN_BASE_URL = os.environ.get(
    "HUNYUAN_BASE_URL",
    "https://api.hunyuan.cloud.tencent.com/v1",
)
HUNYUAN_MODEL = os.environ.get("HUNYUAN_MODEL", "hunyuan-lite")


# Retrieval providers
RAGFLOW_API_URL = os.environ.get("RAGFLOW_API_URL", "")
RAGFLOW_API_KEY = os.environ.get("RAGFLOW_API_KEY", "")
RAGFLOW_KB_ID = os.environ.get("RAGFLOW_KB_ID", "")
USE_RAGFLOW_RETRIEVAL = _env_bool(
    "USE_RAGFLOW_RETRIEVAL",
    bool(RAGFLOW_API_URL and RAGFLOW_API_KEY and RAGFLOW_KB_ID),
)

DIFY_API_URL = os.environ.get("DIFY_API_URL", "")
DIFY_API_KEY = os.environ.get("DIFY_API_KEY", "")
DIFY_DATASET_ID = os.environ.get("DIFY_DATASET_ID", "")
USE_DIFY_RETRIEVAL = _env_bool(
    "USE_DIFY_RETRIEVAL",
    bool(DIFY_API_URL and DIFY_API_KEY and DIFY_DATASET_ID),
)


# Server
ALLOWED_ORIGINS = _env_list(
    "ALLOWED_ORIGINS",
    "http://localhost:3001,http://127.0.0.1:3001",
)
DATABASE_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "zhiyu.db"))
DATABASE_URL = os.environ.get("DATABASE_URL", "")


def load_knowledge_base() -> list[dict]:
    kb_path = BASE_DIR / "knowledge_base.json"
    if not kb_path.exists():
        return []
    with kb_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


KNOWLEDGE_BASE = load_knowledge_base()
