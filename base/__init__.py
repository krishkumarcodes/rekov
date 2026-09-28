"""
base/ — Database & Infrastructure Layer
========================================
Centralises all database concerns for REKOV:
  - SQLAlchemy engine + session factory
  - All ORM models
  - Pydantic schemas
  - SQL migrations
  - Seed data

Usage (from anywhere in the project):
    from base import get_db, Base, engine
    from base.models import TicketModel, DoctorCredentials
    from base.schemas.kiosk import TicketCreateRequest
"""

from base.database import get_db, Base, engine, SessionLocal, init_db
from base.models import (
    TicketModel,
    WhatsappSession,
    BotSession,
    DoctorCredentials,
    MobileSession,
)

__all__ = [
    "get_db",
    "Base",
    "engine",
    "SessionLocal",
    "init_db",
    "TicketModel",
    "WhatsappSession",
    "BotSession",
    "DoctorCredentials",
    "MobileSession",
]
