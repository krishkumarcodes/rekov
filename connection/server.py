"""
connection/server.py
====================
Unified REKOV server -- everything on port 3000.

FastAPI mounts at /api/v1/...
Next.js static export is served from /

Run:
    python connection/server.py

Or via interface.py -> 2 (Web UI) which auto-detects this file.
"""

import os
import sys
import subprocess
import shutil

ROOT_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR  = os.path.join(ROOT_DIR, "rekov")
FRONTEND_DIR = os.path.join(ROOT_DIR, "rekoviu")

sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, BACKEND_DIR)

# ---------------------------------------------------------------------------
#  Load config into env
# ---------------------------------------------------------------------------
import json

def _load_config():
    for p in [os.path.join(ROOT_DIR, "config.json"),
              os.path.join(BACKEND_DIR, "config.json")]:
        if os.path.isfile(p):
            try:
                cfg = json.loads(open(p, encoding="utf-8").read())
                sb = cfg.get("supabase", {}) if isinstance(cfg.get("supabase"), dict) else {}
                url = sb.get("url") or cfg.get("SUPABASE_URL", "")
                key = sb.get("key") or cfg.get("SUPABASE_KEY", "")
                if url:
                    os.environ["SUPABASE_URL"]            = url
                    os.environ["NEXT_PUBLIC_SUPABASE_URL"] = url
                if key:
                    os.environ["SUPABASE_KEY"]            = key
                    os.environ["NEXT_PUBLIC_SUPABASE_KEY"] = key
                hf = cfg.get("hf_token") or cfg.get("HF_TOKEN") or ""
                if hf:
                    os.environ["HF_TOKEN"] = hf
                # Tell frontend/backend the API is under /api/v1 on the same origin
                os.environ["NEXT_PUBLIC_API_URL"] = "http://localhost:3000/api/v1"
                return
            except Exception:
                pass

_load_config()

# ---------------------------------------------------------------------------
#  Build the FastAPI app
# ---------------------------------------------------------------------------
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Import backend routers
os.chdir(BACKEND_DIR)
try:
    from rekov.app.routers import (
        health, kiosk, queue, ai_voice, auth,
        doctor, receptionist, session_log, settings, sync, awake,
    )
    _routers_ok = True
except Exception as e:
    print(f"[WRN] Could not import all routers: {e}")
    _routers_ok = False

app = FastAPI(title="REKOV", version="10.0.0", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
if _routers_ok:
    API_PREFIX = "/api/v1"
    app.include_router(health.router,       prefix=API_PREFIX, tags=["health"])
    app.include_router(kiosk.router,        prefix=API_PREFIX, tags=["kiosk"])
    app.include_router(queue.router,        prefix=API_PREFIX, tags=["queue"])
    app.include_router(ai_voice.router,     prefix=API_PREFIX, tags=["ai"])
    app.include_router(auth.router,         prefix=API_PREFIX, tags=["auth"])
    app.include_router(doctor.router,       prefix=API_PREFIX, tags=["doctor"])
    app.include_router(receptionist.router, prefix=API_PREFIX, tags=["receptionist"])
    app.include_router(session_log.router,  prefix=API_PREFIX, tags=["session"])
    app.include_router(settings.router,     prefix=API_PREFIX, tags=["settings"])
    app.include_router(sync.router,         prefix=API_PREFIX, tags=["sync"])
    app.include_router(awake.router,        prefix=API_PREFIX, tags=["awake"])

# Mount Next.js static export (if available)
NEXT_EXPORT = os.path.join(FRONTEND_DIR, "out")
NEXT_DOT    = os.path.join(FRONTEND_DIR, ".next")

if os.path.isdir(NEXT_EXPORT):
    # Production static export
    app.mount("/", StaticFiles(directory=NEXT_EXPORT, html=True), name="frontend")
    print(f"[OK]  Serving Next.js static export from {NEXT_EXPORT}")
else:
    # Dev fallback -- proxy to Next.js dev server (npm run dev) on port 3001
    import httpx
    from starlette.requests import Request
    from starlette.responses import StreamingResponse, HTMLResponse
    from fastapi.responses import FileResponse

    NEXT_DEV_URL = "http://localhost:3001"

    @app.api_route("/{path:path}", methods=["GET", "HEAD", "OPTIONS"])
    async def _next_proxy(request: Request, path: str):
        async with httpx.AsyncClient() as client:
            url = f"{NEXT_DEV_URL}/{path}"
            if request.url.query:
                url += f"?{request.url.query}"
            try:
                resp = await client.request(
                    method=request.method,
                    url=url,
                    headers=dict(request.headers),
                    timeout=60,
                )
                # Remove hop-by-hop and content-encoding headers to avoid double-encoding issues
                filtered_headers = {
                    k: v for k, v in resp.headers.items()
                    if k.lower() not in ("content-encoding", "content-length", "transfer-encoding", "connection")
                }
                return StreamingResponse(
                    content=iter([resp.content]),
                    status_code=resp.status_code,
                    headers=filtered_headers,
                )
            except Exception as e:
                if "favicon" in path:
                    return FileResponse(os.path.join(FRONTEND_DIR, "public", "favicon.ico"))
                return HTMLResponse(
                    content=f"<html><body style='background:#111;color:#fff;font-family:sans-serif;text-align:center;padding:50px;'><h2>Next.js UI is starting...</h2><p>Please wait a few seconds and refresh the page.</p><p style='color:#666;font-size:12px;'>Error: {str(e)}</p></body></html>",
                    status_code=502
                )

    print(f"[!]   No Next.js export found. Proxying /* to {NEXT_DEV_URL}")
    print(f"      Run 'npm run dev -- --port 3001' in rekoviu/ for the frontend.")


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    print()
    print("[REKOV] Unified server starting on http://localhost:3000")
    print("        API:      http://localhost:3000/api/v1")
    print("        API docs: http://localhost:3000/api/docs")
    print("        App:      http://localhost:3000/")
    print()
    uvicorn.run(app, host="0.0.0.0", port=3000, reload=False)
