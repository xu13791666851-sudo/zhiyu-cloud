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


def _normalize_supabase_url(value: str | None) -> str:
    url = (value or "").strip().strip('"').strip("'").rstrip("/")
    for suffix in ("/rest/v1", "/storage/v1", "/auth/v1"):
        if url.endswith(suffix):
            return url[: -len(suffix)].rstrip("/")
    return url


_load_dotenv()


# LLM
HUNYUAN_API_KEY = _env("HUNYUAN_API_KEY", "") or ""
HUNYUAN_BASE_URL = _env(
    "HUNYUAN_BASE_URL",
    "https://api.hunyuan.cloud.tencent.com/v1",
) or "https://api.hunyuan.cloud.tencent.com/v1"
HUNYUAN_MODEL = _env("HUNYUAN_MODEL", "hunyuan-lite") or "hunyuan-lite"


# Embeddings
EMBEDDING_API_KEY = _env("EMBEDDING_API_KEY", "") or HUNYUAN_API_KEY
EMBEDDING_BASE_URL = _env("EMBEDDING_BASE_URL", "") or HUNYUAN_BASE_URL
EMBEDDING_MODEL = _env("EMBEDDING_MODEL", "") or ""
USE_EMBEDDING_RETRIEVAL = _env_bool("USE_EMBEDDING_RETRIEVAL", bool(EMBEDDING_API_KEY and EMBEDDING_MODEL))
EMBEDDINGS_AUTO_INDEX = _env_bool("EMBEDDINGS_AUTO_INDEX", False)
EMBEDDING_BATCH_SIZE = int(_env("EMBEDDING_BATCH_SIZE", "16") or "16")
EMBEDDING_MIN_SIMILARITY = float(_env("EMBEDDING_MIN_SIMILARITY", "0.15") or "0.15")


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
# Cloudflare Pages 每次部署都会生成随机子域（如 ab1bc852.zhiyu-cloud.pages.dev），
# 没法逐个列举，这里按正则匹配整个站点及其所有预览子域。
ALLOWED_ORIGIN_REGEX = _env(
    "ALLOWED_ORIGIN_REGEX",
    r"https://([a-z0-9-]+\.)?zhiyu-cloud\.pages\.dev",
) or ""
DATABASE_PATH = _env("DATABASE_PATH", str(BASE_DIR / "zhiyu.db")) or str(BASE_DIR / "zhiyu.db")
DATABASE_URL = _env("DATABASE_URL", "") or ""


# Supabase Storage
SUPABASE_URL = _normalize_supabase_url(_env("SUPABASE_URL", ""))
SUPABASE_SERVICE_ROLE_KEY = _env("SUPABASE_SERVICE_ROLE_KEY", "") or ""
SUPABASE_STORAGE_BUCKET = _env("SUPABASE_STORAGE_BUCKET", "documents") or "documents"
SUPABASE_STORAGE_PREFIX = (_env("SUPABASE_STORAGE_PREFIX", "documents") or "documents").strip("/")
SUPABASE_STORAGE_PUBLIC = _env_bool("SUPABASE_STORAGE_PUBLIC", False)
SUPABASE_STORAGE_TIMEOUT = int(_env("SUPABASE_STORAGE_TIMEOUT", "120") or "120")
USE_SUPABASE_STORAGE = _env_bool(
    "USE_SUPABASE_STORAGE",
    bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_STORAGE_BUCKET),
)


def load_knowledge_base() -> list[dict]:
    kb_path = BASE_DIR / "knowledge_base.json"
    if not kb_path.exists():
        return []
    with kb_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


KNOWLEDGE_BASE = load_knowledge_base()
