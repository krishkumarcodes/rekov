-- ============================================================
-- base/migrations/002_supabase_schema.sql
-- REKOV — Supabase (Cloud) Schema + RLS Policies
-- ============================================================
-- Run this in your Supabase SQL Editor (once, cloud-side).
-- This is a reference copy; original: /supabase_schema_rls.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Departments
CREATE TABLE IF NOT EXISTS public.departments (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    code                 TEXT NOT NULL UNIQUE,
    description          TEXT,
    active_doctors_count INT DEFAULT 0,
    wait_time_minutes    INT DEFAULT 5,
    created_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Doctors
CREATE TABLE IF NOT EXISTS public.doctors (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    department_id         TEXT REFERENCES public.departments(id) ON DELETE SET NULL,
    specialty             TEXT NOT NULL,
    room_number           TEXT NOT NULL,
    is_available          BOOLEAN DEFAULT TRUE,
    estimated_wait_minutes INT DEFAULT 10,
    consultation_fee      NUMERIC(10,2) DEFAULT 35.00,
    rating                NUMERIC(3,2) DEFAULT 4.90,
    experience_years      INT DEFAULT 10,
    arrival_time          TEXT DEFAULT '08:00',
    pin                   TEXT DEFAULT '1234',
    shift_schedule        TEXT DEFAULT '08:00 AM - 04:00 PM',
    created_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tickets (cloud mirror)
CREATE TABLE IF NOT EXISTS public.tickets (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticket_id           TEXT UNIQUE NOT NULL,
    token_number        TEXT NOT NULL,
    department_id       TEXT REFERENCES public.departments(id),
    department_name     TEXT,
    doctor_id           TEXT REFERENCES public.doctors(id),
    doctor_name         TEXT,
    room_number         TEXT,
    patient_name        TEXT,
    patient_phone       TEXT,
    status              TEXT DEFAULT 'WAITING',
    priority_level      TEXT DEFAULT 'STANDARD',
    triage_score        INT DEFAULT 1,
    total_fee           NUMERIC(10,2) DEFAULT 0.00,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at          TIMESTAMP WITH TIME ZONE,
    receipt_pdf_url     TEXT
);

-- Enable Row Level Security (public read, authenticated write)
ALTER TABLE public.tickets     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.doctors     ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read tickets"     ON public.tickets     FOR SELECT USING (true);
CREATE POLICY "Public insert tickets"   ON public.tickets     FOR INSERT WITH CHECK (true);
CREATE POLICY "Public update tickets"   ON public.tickets     FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY "Public read departments" ON public.departments FOR SELECT USING (true);
CREATE POLICY "Public read doctors"     ON public.doctors     FOR SELECT USING (true);

-- RITMO Chat History (Temporary Storage - 7 Days)
CREATE TABLE IF NOT EXISTS public.ritmohis (
    session_id          TEXT PRIMARY KEY,
    mode                TEXT,
    model               TEXT,
    started_at          TIMESTAMP WITH TIME ZONE,
    ended_at            TIMESTAMP WITH TIME ZONE,
    outcome             TEXT,
    turn_count          INT DEFAULT 0,
    messages            JSONB DEFAULT '[]'::JSONB,
    actions             JSONB DEFAULT '[]'::JSONB,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE public.ritmohis ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public access ritmohis" ON public.ritmohis FOR ALL USING (true) WITH CHECK (true);

