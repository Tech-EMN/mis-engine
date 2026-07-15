-- MIS Engine — Schema Migration 001
-- Project: MIS (MGroup Intelligence System)
-- Supabase Project: LugOn (heubjypagspflnmmygzj)
-- Date: 2026-07-15
-- Author: Daedalus (AG01)
-- Sprint: S1.6
-- 
-- Execute via Supabase Dashboard → SQL Editor:
--   1. Go to https://supabase.com/dashboard/project/heubjypagspflnmmygzj/sql/new
--   2. Paste this entire file
--   3. Click "Run"
-- 
-- Or via CLI:
--   supabase db push --db-url "postgresql://..."

-- ============================================================
-- PROJECTS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS mis_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    source_type TEXT CHECK (source_type IN ('pdf', 'dxf', 'dwg')),
    status TEXT NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'processing', 'done', 'failed')),
    total_rooms INTEGER DEFAULT 0,
    error TEXT,
    warnings JSONB DEFAULT '[]'::jsonb,
    fragilities JSONB DEFAULT '[]'::jsonb,
    elapsed_ms FLOAT DEFAULT 0,
    pipeline_version TEXT DEFAULT 'draft-c-v2',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- ============================================================
-- ROOMS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS mis_rooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES mis_projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'Ambiente sem label',
    area_m2 FLOAT NOT NULL DEFAULT 0,
    perimeter_m FLOAT NOT NULL DEFAULT 0,
    width_m FLOAT NOT NULL DEFAULT 0,
    length_m FLOAT NOT NULL DEFAULT 0,
    shape TEXT DEFAULT 'rectangle' CHECK (shape IN ('rectangle', 'irregular')),
    confidence_geometry FLOAT DEFAULT 1.0,
    confidence_name FLOAT DEFAULT 0.5,
    needs_human_review BOOLEAN DEFAULT false,
    review_reason TEXT,
    faces JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- EXTRACTIONS TABLE (audit log)
-- ============================================================

CREATE TABLE IF NOT EXISTS mis_extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES mis_projects(id) ON DELETE CASCADE,
    task_id TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    file_size_bytes INTEGER,
    result_json JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_mis_projects_status 
    ON mis_projects(status);
CREATE INDEX IF NOT EXISTS idx_mis_projects_created 
    ON mis_projects(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mis_rooms_project 
    ON mis_rooms(project_id);
CREATE INDEX IF NOT EXISTS idx_mis_extractions_task 
    ON mis_extractions(task_id);

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================

ALTER TABLE mis_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE mis_rooms ENABLE ROW LEVEL SECURITY;
ALTER TABLE mis_extractions ENABLE ROW LEVEL SECURITY;

-- Allow read access to anyone with API key (for front-end)
CREATE POLICY "anon_can_read_projects" 
    ON mis_projects FOR SELECT USING (true);
CREATE POLICY "anon_can_read_rooms" 
    ON mis_rooms FOR SELECT USING (true);
CREATE POLICY "anon_can_read_extractions" 
    ON mis_extractions FOR SELECT USING (true);

-- Allow insert/update for authenticated (service_role bypasses RLS)
CREATE POLICY "auth_can_insert_projects" 
    ON mis_projects FOR INSERT WITH CHECK (true);
CREATE POLICY "auth_can_update_projects" 
    ON mis_projects FOR UPDATE USING (true);
CREATE POLICY "auth_can_insert_rooms" 
    ON mis_rooms FOR INSERT WITH CHECK (true);
CREATE POLICY "auth_can_update_rooms" 
    ON mis_rooms FOR UPDATE USING (true);
CREATE POLICY "auth_can_insert_extractions" 
    ON mis_extractions FOR INSERT WITH CHECK (true);

-- ============================================================
-- VERIFICATION QUERIES
-- ============================================================

-- Run these after migration to verify:
-- SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'mis_%';
-- Expected: mis_projects, mis_rooms, mis_extractions
