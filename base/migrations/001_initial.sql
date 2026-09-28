-- ============================================================
-- base/migrations/001_initial.sql
-- REKOV — Local SQLite Schema (Initial)
-- ============================================================
-- Run order: 001 → 002 → ...
-- Applied automatically by base/database.py on startup.
-- ============================================================

-- Tickets (queue entries)
CREATE TABLE IF NOT EXISTS tickets (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id           TEXT UNIQUE NOT NULL,
    token_number        TEXT NOT NULL,
    department_id       TEXT,
    department_name     TEXT,
    doctor_id           TEXT,
    doctor_name         TEXT,
    room_number         TEXT,
    patient_name        TEXT,
    patient_phone       TEXT,
    status              TEXT DEFAULT 'WAITING',
    priority_level      TEXT DEFAULT 'STANDARD',
    triage_score        INTEGER DEFAULT 1,
    combos_selected     TEXT DEFAULT '[]',
    total_fee           REAL DEFAULT 0.0,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at          DATETIME,
    estimated_call_time TEXT,
    synced              INTEGER DEFAULT 0,
    receipt_pdf_url     TEXT
);

-- WhatsApp sessions
CREATE TABLE IF NOT EXISTS whatsapp_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number TEXT,
    status       TEXT DEFAULT 'pending',
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Bot sessions (Telegram / WhatsApp)
CREATE TABLE IF NOT EXISTS bot_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    platform   TEXT,
    chat_id    TEXT,
    state      TEXT DEFAULT '{}',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Doctor credentials
CREATE TABLE IF NOT EXISTS doctor_credentials (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id     TEXT UNIQUE NOT NULL,
    username      TEXT,
    password_hash TEXT,
    role          TEXT DEFAULT 'doctor',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Mobile form sessions (QR pairing)
CREATE TABLE IF NOT EXISTS mobile_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT UNIQUE NOT NULL,
    status          TEXT DEFAULT 'PENDING',
    patient_name    TEXT,
    patient_phone   TEXT,
    patient_dob     TEXT,
    department_id   TEXT,
    chief_complaint TEXT,
    documents       TEXT DEFAULT '[]',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at      DATETIME
);
