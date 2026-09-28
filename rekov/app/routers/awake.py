"""
rekov/app/routers/awake.py
===========================
REKOV Awake System — FastAPI router.

Exposes:
  GET  /api/v1/awake/stats     — live stats JSON (used by frontend /awake page)
  GET  /api/v1/awake/ping      — manual trigger (fires one ping cycle immediately)
  GET  /api/v1/awake/health    — simple alive check for the awake system itself

The AwakeKeeper is started during backend lifespan (wired in rekov/main.py).
"""

import sys
import time
from pathlib import Path
from fastapi import APIRouter

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

try:
    from awake.stats  import get_stats
    from awake.keeper import _ping_supabase, _ping_render, _load_config, _resolve_supabase, _resolve_render
    _AWAKE_OK = True
except ImportError:
    _AWAKE_OK = False
    def get_stats(): return {"error": "awake package not found"}

router = APIRouter(prefix="/awake", tags=["Awake System"])


@router.get("/stats")
def awake_stats():
    """
    Return live keep-alive stats for the frontend /awake page.
    Includes: uptime, supabase ping counts, render ping counts, last OK times.
    """
    return get_stats()


@router.get("/ping")
def awake_manual_ping():
    """
    Manually trigger one ping cycle to both Supabase and Render.
    Returns immediate results — useful for debugging.
    """
    if not _AWAKE_OK:
        return {"error": "awake package not available"}

    cfg = _load_config()
    sb_url, sb_key = _resolve_supabase(cfg)
    rd_url         = _resolve_render(cfg)

    t0 = time.time()
    sb_ok, sb_ms, sb_msg = _ping_supabase(sb_url, sb_key)
    rd_ok, rd_ms, rd_msg = _ping_render(rd_url)

    return {
        "triggered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "supabase": {
            "url":    sb_url,
            "ok":     sb_ok,
            "ms":     sb_ms,
            "msg":    sb_msg,
        },
        "render": {
            "url":    rd_url,
            "ok":     rd_ok,
            "ms":     rd_ms,
            "msg":    rd_msg,
        },
        "elapsed_ms": int((time.time() - t0) * 1000),
    }


@router.get("/health")
def awake_health():
    """Simple alive check — returns 200 if the awake module is loaded."""
    return {
        "awake_module": "ok" if _AWAKE_OK else "unavailable",
        "server_time":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
