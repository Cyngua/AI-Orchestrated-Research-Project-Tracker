-- Migration script to add AI-generated fields to projects table
-- Run this to add support for cached AI outputs

ALTER TABLE projects ADD COLUMN ai_summary TEXT;
ALTER TABLE projects ADD COLUMN ai_keywords TEXT;  -- JSON array stored as text
ALTER TABLE projects ADD COLUMN ai_stage_guess TEXT;
ALTER TABLE projects ADD COLUMN ai_suggested_mechanisms TEXT;  -- JSON array stored as text
ALTER TABLE projects ADD COLUMN ai_generated_at DATETIME;
ALTER TABLE projects ADD COLUMN ai_manual_override BOOLEAN DEFAULT 0;  -- Flag for manual edits

-- Index for faster queries on AI-generated content
CREATE INDEX IF NOT EXISTS idx_projects_ai_generated ON projects(ai_generated_at);

