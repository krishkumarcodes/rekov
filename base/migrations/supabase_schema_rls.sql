-- ====================================================================
-- MediVERSE Supabase Database Schema, Storage Bucket & RLS Policies
-- ====================================================================

-- Enable UUID Extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. DEPARTMENTS TABLE
CREATE TABLE IF NOT EXISTS public.departments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    description TEXT,
    active_doctors_count INT DEFAULT 0,
    wait_time_minutes INT DEFAULT 5,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. DOCTORS TABLE (50 Doctors Registry)
CREATE TABLE IF NOT EXISTS public.doctors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    department_id TEXT REFERENCES public.departments(id) ON DELETE SET NULL,
    specialty TEXT NOT NULL,
    room_number TEXT NOT NULL,
    is_available BOOLEAN DEFAULT TRUE,
    estimated_wait_minutes INT DEFAULT 10,
    consultation_fee NUMERIC(10,2) DEFAULT 35.00,
    rating NUMERIC(3,2) DEFAULT 4.90,
    experience_years INT DEFAULT 10,
    arrival_time TEXT DEFAULT '08:00',
    pin TEXT DEFAULT '1234',
    shift_schedule TEXT DEFAULT '08:00 AM - 04:00 PM',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. SCHEDULES TABLE (Doctor Availability & Shift Timings)
CREATE TABLE IF NOT EXISTS public.schedules (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    doctor_id TEXT REFERENCES public.doctors(id) ON DELETE CASCADE,
    department_id TEXT REFERENCES public.departments(id) ON DELETE CASCADE,
    days_of_week TEXT DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat',
    shift_start TEXT DEFAULT '08:00 AM',
    shift_end TEXT DEFAULT '04:00 PM',
    room_number TEXT NOT NULL,
    max_daily_patients INT DEFAULT 40,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. PATIENTS TABLE (Patient Registry)
CREATE TABLE IF NOT EXISTS public.patients (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    national_id TEXT UNIQUE,
    name TEXT NOT NULL,
    phone TEXT,
    age INT,
    gender TEXT,
    blood_group TEXT,
    medical_history TEXT,
    abha_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. TICKETS TABLE (Queue & Appointment Records)
CREATE TABLE IF NOT EXISTS public.tickets (
    ticket_id TEXT PRIMARY KEY,
    token_number TEXT NOT NULL,
    department_id TEXT REFERENCES public.departments(id) ON DELETE CASCADE,
    doctor_id TEXT REFERENCES public.doctors(id) ON DELETE SET NULL,
    patient_name TEXT NOT NULL,
    patient_phone TEXT,
    status TEXT DEFAULT 'WAITING',
    priority_level INT DEFAULT 1,
    triage_score FLOAT DEFAULT 0.0,
    total_fee NUMERIC(10,2) DEFAULT 0.00,
    synced BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ====================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ====================================================================

ALTER TABLE public.departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.doctors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tickets ENABLE ROW LEVEL SECURITY;

-- Public Read Policies for Catalog & Doctor Schedules
CREATE POLICY "Public Read Departments" ON public.departments FOR SELECT USING (true);
CREATE POLICY "Public Read Doctors" ON public.doctors FOR SELECT USING (true);
CREATE POLICY "Public Read Schedules" ON public.schedules FOR SELECT USING (true);

-- Public Read/Write Policies for Kiosk Self-Service Registration & Tickets
CREATE POLICY "Public Read Patients" ON public.patients FOR SELECT USING (true);
CREATE POLICY "Public Insert Patients" ON public.patients FOR INSERT WITH CHECK (true);
CREATE POLICY "Public Update Patients" ON public.patients FOR UPDATE USING (true);

CREATE POLICY "Public Read Tickets" ON public.tickets FOR SELECT USING (true);
CREATE POLICY "Public Insert Tickets" ON public.tickets FOR INSERT WITH CHECK (true);
CREATE POLICY "Public Update Tickets" ON public.tickets FOR UPDATE USING (true);

-- ====================================================================
-- SUPABASE STORAGE BUCKET: patient-documents
-- ====================================================================

INSERT INTO storage.buckets (id, name, public) 
VALUES ('patient-documents', 'patient-documents', true)
ON CONFLICT (id) DO NOTHING;

-- Storage RLS Policies
CREATE POLICY "Public Read Patient Documents" 
ON storage.objects FOR SELECT 
USING (bucket_id = 'patient-documents');

CREATE POLICY "Public Upload Patient Documents" 
ON storage.objects FOR INSERT 
WITH CHECK (bucket_id = 'patient-documents');

-- ====================================================================
-- SUPABASE STORAGE BUCKET: receipts
-- ====================================================================

INSERT INTO storage.buckets (id, name, public, avif_autodetection, allowed_mime_types) 
VALUES (
  'receipts', 
  'receipts', 
  true,
  false,
  ARRAY['application/pdf', 'image/png', 'image/jpeg']
)
ON CONFLICT (id) DO NOTHING;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects'
    AND policyname = 'Public Read Receipts'
  ) THEN
    CREATE POLICY "Public Read Receipts"
    ON storage.objects FOR SELECT
    USING (bucket_id = 'receipts');
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects'
    AND policyname = 'Public Upload Receipts'
  ) THEN
    CREATE POLICY "Public Upload Receipts"
    ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'receipts');
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'storage' AND tablename = 'objects'
    AND policyname = 'Public Update Receipts'
  ) THEN
    CREATE POLICY "Public Update Receipts"
    ON storage.objects FOR UPDATE
    USING (bucket_id = 'receipts');
  END IF;
END $$;

