"""
base/models.py — All SQLAlchemy ORM Models
===========================================
Single file that defines every database table for REKOV.
Import from here; never define models in routers or services.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from datetime import datetime, timedelta
from base.database import Base


# ── Ticket (Queue Entry) ──────────────────────────────────────────────────────
class TicketModel(Base):
    __tablename__ = "tickets"

    id                = Column(Integer, primary_key=True, index=True)
    ticket_id         = Column(String, unique=True, index=True)
    token_number      = Column(String, index=True)
    department_id     = Column(String)
    department_name   = Column(String)
    doctor_id         = Column(String, nullable=True)
    doctor_name       = Column(String)
    room_number       = Column(String)
    patient_name      = Column(String)
    patient_phone     = Column(String, nullable=True)
    status            = Column(String, default="WAITING")       # WAITING | IN_CONSULTATION | COMPLETED | CANCELLED
    priority_level    = Column(String, default="STANDARD")
    triage_score      = Column(Integer, default=1)
    combos_selected   = Column(String, default="[]")            # JSON string
    total_fee         = Column(Float, default=0.0)
    created_at        = Column(DateTime, default=datetime.utcnow)
    expires_at        = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(hours=24))
    estimated_call_time = Column(String)
    synced            = Column(Boolean, default=False)          # Offline → Supabase sync flag
    receipt_pdf_url   = Column(String, nullable=True)           # Supabase public PDF URL


# ── WhatsApp Session ──────────────────────────────────────────────────────────
class WhatsappSession(Base):
    __tablename__ = "whatsapp_sessions"

    id            = Column(Integer, primary_key=True, index=True)
    phone_number  = Column(String, index=True)
    status        = Column(String, default="pending")           # pending | consumed
    created_at    = Column(DateTime, default=datetime.utcnow)


# ── Bot Session (Telegram / WhatsApp conversation state) ─────────────────────
class BotSession(Base):
    __tablename__ = "bot_sessions"

    id          = Column(Integer, primary_key=True, index=True)
    session_id  = Column(String, unique=True, index=True)
    platform    = Column(String)                                # 'telegram' | 'whatsapp'
    chat_id     = Column(String, index=True)
    state       = Column(String, default="{}")                  # JSON-encoded state dict
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Doctor Credentials ────────────────────────────────────────────────────────
class DoctorCredentials(Base):
    __tablename__ = "doctor_credentials"

    id            = Column(Integer, primary_key=True, index=True)
    doctor_id     = Column(String, unique=True, index=True)
    username      = Column(String)
    password_hash = Column(String)
    role          = Column(String, default="doctor")
    created_at    = Column(DateTime, default=datetime.utcnow)


# ── Mobile Form Session (QR-linked kiosk ↔ phone pairing) ────────────────────
class MobileSession(Base):
    """Pairs a kiosk session to a phone-submitted form via rotating QR code."""
    __tablename__ = "mobile_sessions"

    id              = Column(Integer, primary_key=True, index=True)
    session_id      = Column(String, unique=True, index=True)   # UUID shown in QR
    status          = Column(String, default="PENDING")         # PENDING | SUBMITTED | EXPIRED
    patient_name    = Column(String, nullable=True)
    patient_phone   = Column(String, nullable=True)
    patient_dob     = Column(String, nullable=True)
    department_id   = Column(String, nullable=True)
    chief_complaint = Column(String, nullable=True)
    documents       = Column(String, default="[]")              # JSON list of {name, url, type}
    created_at      = Column(DateTime, default=datetime.utcnow)
    expires_at      = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(seconds=30))


# ── RITMO Chat History ────────────────────────────────────────────────────────
class RitmoHisModel(Base):
    __tablename__ = "ritmohis"

    id         = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    role       = Column(String)  # user | assistant
    content    = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(days=7))
