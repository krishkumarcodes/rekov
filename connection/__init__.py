"""
connection/
===========
Unified REKOV connection layer.

Everything runs on port 3000:
  /api/v1/*  -> FastAPI backend routes
  /*         -> Next.js frontend (static export or dev proxy)

Files:
  server.py  - Main unified uvicorn server entry point

Usage:
    python connection/server.py
    # or via interface.py -> 2 (Web UI)
"""
