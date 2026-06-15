-- Run this in the Supabase SQL editor before querying or inserting inspections.
CREATE TABLE IF NOT EXISTS public.inspections (
  id uuid PRIMARY KEY,
  uploaded_filename text,
  uploaded_url text,
  result_url text,
  status text,
  severity text,
  checks jsonb,
  detections jsonb,
  mfg_text text,
  expiry_text text,
  detected_count integer,
  model_path text,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inspections_created_at ON public.inspections (created_at);
CREATE INDEX IF NOT EXISTS idx_inspections_status ON public.inspections (status);
CREATE INDEX IF NOT EXISTS idx_inspections_checks ON public.inspections USING GIN (checks);
CREATE INDEX IF NOT EXISTS idx_inspections_detections ON public.inspections USING GIN (detections);

-- Demo/local testing only: allows the Flask app to insert with SUPABASE_ANON_KEY.
-- For production, keep RLS enabled and use a service role key on the server.
ALTER TABLE public.inspections DISABLE ROW LEVEL SECURITY;
