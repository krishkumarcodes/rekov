-- ====================================================================
-- MediVERSE: Create Receipts Storage Bucket & Public RLS Policies
-- Run this in your Supabase SQL Editor (one time only)
-- ====================================================================

-- 1. Create the receipts bucket (IF NOT EXISTS equivalent for storage)
INSERT INTO storage.buckets (id, name, public, avif_autodetection, allowed_mime_types)
VALUES (
  'receipts',
  'receipts',
  true,
  false,
  ARRAY['application/pdf', 'image/png', 'image/jpeg']
)
ON CONFLICT (id) DO NOTHING;

-- 2. Allow any user to READ (download) receipts
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

-- 3. Allow any user to UPLOAD receipts (kiosk self-service)
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

-- 4. Allow updates (upsert overwrite of same file)
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

-- Done! Verify with:
-- SELECT * FROM storage.buckets WHERE id = 'receipts';
