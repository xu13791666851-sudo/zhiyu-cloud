# ZhiYu

ZhiYu is a RAG-based academic document assistant. The current architecture is frontend/backend separated and ready for local Docker Compose deployment.

## Architecture

- Backend: FastAPI, entrypoint `api_server.py`
- Frontend: Next.js, under `ai/`
- Database: PostgreSQL in Docker Compose, SQLite fallback when `DATABASE_URL` is not set
- Retrieval: Dify, RAGFlow, local knowledge base fallback
- Optional local reverse proxy: Caddy profile

## Key Files

```text
zhiyu-cloud/
├── api_server.py          # FastAPI backend
├── api.py                 # Retrieval orchestration
├── config.py              # Environment config
├── Dockerfile             # Backend image
├── docker-compose.yml     # One-command local stack
├── Caddyfile              # Optional local reverse proxy
├── .env.example           # Environment template
├── start.ps1              # Windows Docker Compose startup script
├── 启动知域.bat           # Double-click Windows launcher
└── ai/
    ├── Dockerfile         # Frontend image
    ├── next.config.mjs
    └── app/
```

## Environment

Copy `.env.example` to `.env` and fill in real keys.

Important variables:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection used by the backend |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | PostgreSQL container credentials |
| `NEXT_PUBLIC_API_BASE_URL` | API base URL used by the browser |
| `ALLOWED_ORIGINS` | Frontend origins allowed by FastAPI CORS |
| `HUNYUAN_API_KEY` | Tencent Hunyuan API key |
| `DIFY_API_URL` / `DIFY_API_KEY` / `DIFY_DATASET_ID` | Dify retrieval config |
| `RAGFLOW_API_URL` / `RAGFLOW_API_KEY` / `RAGFLOW_KB_ID` | RAGFlow retrieval config |

## One-Command Startup

Default stack:

```bash
docker compose up -d --build
```

Or on Windows:

```powershell
.\start.ps1
```

Optional local cloud-like reverse proxy:

```powershell
.\start.ps1 -WithProxy
```

The proxy exposes a unified entry at:

```text
http://localhost:8080
```

## Services

| Service | URL / Port | Health Check |
| --- | --- | --- |
| frontend | http://localhost:3001 | container healthcheck hits `/` |
| backend | http://localhost:8000 | http://localhost:8000/health |
| postgres | localhost:5432 | `pg_isready` |
| caddy optional | http://localhost:8080 | `/health` through proxy |

## Useful Commands

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f postgres
docker compose down
```

Start with optional proxy manually:

```bash
docker compose --profile proxy up -d --build
```

## Local Development Without Docker

Backend:

```bash
pip install -r requirements.txt
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd ai
npm install
npm run dev
```

## Deprecated Entrypoint

`app.py` is the old Gradio entrypoint and no longer starts the app.
