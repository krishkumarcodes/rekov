"""
base/database.py — SQLAlchemy Engine & Session Factory
=======================================================
Canonical single source of truth for all DB connections in REKOV.

  - SQLite for local / offline use  (data/database/local.db)
  - DATA_DIR env override for custom paths
  - Auto-creates tables and runs migrations on first import
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timedelta

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))           # .../base/
ROOT_DIR = os.path.dirname(BASE_DIR)                            # .../rekov-6.0.0/

DATA_DIR = (
    os.getenv("DATA_DIR")
    or os.path.join(ROOT_DIR, "base", "data")
)
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH               = os.path.join(DATA_DIR, "local.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# ── Engine & Session ──────────────────────────────────────────────────────────
engine       = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ── DB Session Dependency (FastAPI / manual use) ──────────────────────────────
def get_db():
    """Yield a database session, always closing it on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Initialise & Migrate ──────────────────────────────────────────────────────
def init_db():
    """
    Create all tables from the ORM models and apply any missing
    column migrations (safe ALTER TABLE for SQLite).
    """
    # Import models so Base.metadata has them registered
    from base import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    from sqlalchemy import inspect, text
    try:
        inspector = inspect(engine)

        # ── tickets table: add missing columns ────────────────────────────────
        if "tickets" in inspector.get_table_names():
            columns = [c["name"] for c in inspector.get_columns("tickets")]
            with engine.connect() as conn:
                if "patient_phone" not in columns:
                    conn.execute(text("ALTER TABLE tickets ADD COLUMN patient_phone VARCHAR"))
                if "expires_at" not in columns:
                    conn.execute(text("ALTER TABLE tickets ADD COLUMN expires_at DATETIME"))
                if "receipt_pdf_url" not in columns:
                    conn.execute(text("ALTER TABLE tickets ADD COLUMN receipt_pdf_url VARCHAR"))
                conn.commit()

            # Purge tickets expired > 24 h ago
            now_iso = datetime.utcnow().isoformat()
            with engine.connect() as conn:
                conn.execute(
                    text("DELETE FROM tickets WHERE expires_at IS NOT NULL AND expires_at < :now"),
                    {"now": now_iso},
                )
                conn.commit()

    except Exception as e:
        print(f"[base/database] Migration warning: {e}")

    # Seed default doctors
    db = SessionLocal()
    try:
        from base.models import DoctorCredentials
        import hashlib

        if not db.query(DoctorCredentials).first():
            defaults = [
                {"doctor_id": "doc_1", "username": "dr.vance",   "password": "rekov123"},
                {"doctor_id": "doc_2", "username": "dr.rostova", "password": "rekov123"},
                {"doctor_id": "doc_3", "username": "dr.thorne",  "password": "rekov123"},
                {"doctor_id": "doc_4", "username": "dr.jenkins", "password": "rekov123"},
            ]
            for d in defaults:
                db.add(DoctorCredentials(
                    doctor_id=d["doctor_id"],
                    username=d["username"],
                    password_hash=hashlib.sha256(d["password"].encode()).hexdigest(),
                ))
            db.commit()
    finally:
        db.close()


def purge_stale_sessions(max_age_hours: int = 24):
    """Purge BotSession rows not updated within max_age_hours."""
    from base.models import BotSession
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        db.query(BotSession).filter(BotSession.updated_at < cutoff).delete()
        db.commit()
    except Exception as e:
        print(f"[base/database] Purge warning: {e}")
    finally:
        db.close()


# ── Auto-init on import ───────────────────────────────────────────────────────
try:
    init_db()
except Exception as _e:
    print(f"[base/database] Auto init warning: {_e}")
