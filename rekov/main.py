import sys
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.core.config import settings
from app.routers import kiosk, queue, doctor, health, auth, receptionist
import threading
import time
from app.core.database import init_db, purge_stale_sessions
from app.services.sync_service import start_sync_service
from app.services.backupverifier import start_backup_verifier

# Awake System
try:
    from awake.keeper import AwakeKeeper
    _awake_keeper = AwakeKeeper(verbose=True)
    _AWAKE_OK = True
except ImportError:
    _awake_keeper = None
    _AWAKE_OK = False

def purge_worker():
    while True:
        purge_stale_sessions(max_age_hours=24)
        time.sleep(3600)  # run every hour

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n--- REKOV Backend Startup Sequence ---")
    
    # Startup Database
    try:
        init_db()
        print("[SUCCESS] Database initialized.")
    except Exception as e:
        print(f"[FAILED] Database initialization: {e}")

    # Startup Sync Service
    try:
        start_sync_service()
        print("[SUCCESS] Offline Sync Service started.")
    except Exception as e:
        print(f"[FAILED] Offline Sync Service: {e}")

    # Startup Backup Verifier (CSV <-> Supabase bi-directional sync)
    try:
        start_backup_verifier()
        print("[SUCCESS] BackupVerifier started (CSV <-> Supabase bi-directional sync).")
    except Exception as e:
        print(f"[FAILED] BackupVerifier: {e}")
    
    # Start session purger
    try:
        t = threading.Thread(target=purge_worker, daemon=True)
        t.start()
        print("[SUCCESS] Session Purge Daemon started.")
    except Exception as e:
        print(f"[FAILED] Session Purge Daemon: {e}")

    # Start Awake System (keep Supabase + Render alive)
    try:
        if _AWAKE_OK and _awake_keeper:
            _awake_keeper.start()
            print("[SUCCESS] Awake System started (Supabase + Render keep-alive).")
    except Exception as e:
        print(f"[FAILED] Awake System: {e}")

    print("--------------------------------------\n")
    yield
    # Shutdown
    if _AWAKE_OK and _awake_keeper:
        _awake_keeper.stop()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS Middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
from app.routers import kiosk, queue, doctor, health, auth, receptionist, settings as settings_router, ai, ai_voice, sync as sync_router
from app.routers import session_log as session_log_router
from app.routers import mobile_session as mobile_session_router
from app.routers import awake as awake_router
from rekovbot.telegram.router import router as telegram_router
from rekovbot.whatsapp.router import router as whatsapp_router

app.include_router(health.router, prefix=settings.API_V1_STR)
app.include_router(kiosk.router, prefix=settings.API_V1_STR)
app.include_router(queue.router, prefix=settings.API_V1_STR)
app.include_router(doctor.router, prefix=settings.API_V1_STR)
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(receptionist.router, prefix=f"{settings.API_V1_STR}/receptionist")
app.include_router(settings_router.router, prefix=f"{settings.API_V1_STR}/settings")
app.include_router(sync_router.router, prefix=f"{settings.API_V1_STR}")
app.include_router(ai.router, prefix=f"{settings.API_V1_STR}")
app.include_router(ai_voice.router, prefix=f"{settings.API_V1_STR}")
app.include_router(session_log_router.router, prefix=f"{settings.API_V1_STR}")
app.include_router(mobile_session_router.router, prefix=f"{settings.API_V1_STR}")
app.include_router(awake_router.router, prefix=f"{settings.API_V1_STR}")
app.include_router(telegram_router, prefix=f"{settings.API_V1_STR}/bot")
app.include_router(whatsapp_router, prefix=f"{settings.API_V1_STR}/bot")

@app.get("/")
def root():
    return {
        "message": "Welcome to REKOV API",
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health",
        "awake":  f"{settings.API_V1_STR}/awake/stats",
        "frontend_url": "http://localhost:3000"
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=4040, reload=True)
