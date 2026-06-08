"""Deprecated Gradio entrypoint.

ZhiYu now uses:
- Backend: api_server.py (FastAPI)
- Frontend: ai/ (Next.js)
"""

from __future__ import annotations

import sys


if __name__ == "__main__":
    print("=" * 60)
    print("Deprecated entrypoint: app.py")
    print()
    print("Use one of these commands instead:")
    print("  Backend:  uvicorn api_server:app --host 0.0.0.0 --port 8000")
    print("  Or:       python api_server.py")
    print("  Frontend: cd ai && npm run dev")
    print("=" * 60)
    sys.exit(1)
