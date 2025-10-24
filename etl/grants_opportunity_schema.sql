-- =========================
-- Grants.gov Opportunities
-- =========================

-- Core opportunity table (one row per grants.gov opportunity)
CREATE TABLE IF NOT EXISTS grants_opportunity (
  id                     INTEGER PRIMARY KEY,
  grantsgov_id           TEXT NOT NULL UNIQUE,               -- e.g., '356164'
  opportunity_number     TEXT,                               -- e.g., 'RFA-OH-26-002'
  title                  TEXT NOT NULL,
  agency_code            TEXT,                               -- e.g., 'HHS-CDC-HHSCDCERA'
  agency_name            TEXT,                               -- e.g., 'Centers for Disease Control and Prevention - ERA'
  opp_status             TEXT CHECK (opp_status IN ('posted','forecasted','closed','archived')),
  doc_type               TEXT CHECK (doc_type IN ('synopsis','forecast','full_announcement')),
  open_date              DATE,                               -- Opportunity open date
  close_date             DATE,                               -- Application deadline
  post_date              DATE,                               -- When opportunity was posted
  archive_date           DATE,                               -- When opportunity was archived
  opportunity_category   TEXT,                               -- Opportunity category

  -- Detailed fields (from fetchOpportunity API)
  description            TEXT,                               -- Full opportunity description/abstract
  award_ceiling          TEXT,                               -- Maximum award amount (kept as TEXT per source)
  award_floor            TEXT,                               -- Minimum award amount (kept as TEXT per source)
  cost_sharing           BOOLEAN CHECK (cost_sharing IN (0,1)), -- Whether cost sharing is required (0/1)
  applicant_eligibility  TEXT,                               -- Eligibility requirements
  agency_contact_name    TEXT,                               -- Contact person name
  agency_contact_phone   TEXT,                               -- Contact phone number
  agency_contact_email   TEXT,                               -- Contact email
  funding_desc_link      TEXT,                               -- Link to full announcement

  -- Metadata
  revision               INTEGER,                            -- Revision number
  listed                 TEXT,                               -- Listed status
  publisher_uid          TEXT,                               -- Publisher identifier
  modified_comments      TEXT,                               -- Modification comments

  created_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Update trigger for grants_opportunity (guarded to avoid recursion/extra write loops)
DROP TRIGGER IF EXISTS trg_grants_opportunity_updated_at;
CREATE TRIGGER trg_grants_opportunity_updated_at
AFTER UPDATE ON grants_opportunity
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
  UPDATE grants_opportunity
  SET updated_at = CURRENT_TIMESTAMP
  WHERE id = NEW.id;
END;

-- Indexes for grants_opportunity
CREATE INDEX IF NOT EXISTS idx_grants_opportunity_number
  ON grants_opportunity(opportunity_number);
CREATE INDEX IF NOT EXISTS idx_grants_opportunity_status
  ON grants_opportunity(opp_status);
CREATE INDEX IF NOT EXISTS idx_grants_opportunity_agency
  ON grants_opportunity(agency_code);
CREATE INDEX IF NOT EXISTS idx_grants_opportunity_open_date
  ON grants_opportunity(open_date);
CREATE INDEX IF NOT EXISTS idx_grants_opportunity_close_date
  ON grants_opportunity(close_date);

-- =========================
-- Search queries table
-- =========================
CREATE TABLE IF NOT EXISTS grants_search_queries (
  id               INTEGER PRIMARY KEY,
  keyword          TEXT NOT NULL,
  statuses         TEXT,                                   -- e.g., 'posted|forecasted'
  agencies         TEXT,                                   -- Agency filters (if any)
  category         TEXT,                                   -- Category filters (if any)
  aln              TEXT,                                   -- ALN filter (if any)
  rows_per_page    INTEGER,
  pages_requested  INTEGER,
  start_record     INTEGER,
  total_results    INTEGER,                                -- How many results were returned
  search_date      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  output_file      TEXT                                    -- Path to output JSON file
);

-- Indexes for search queries
CREATE INDEX IF NOT EXISTS idx_search_queries_date
  ON grants_search_queries(search_date);
CREATE INDEX IF NOT EXISTS idx_search_queries_keyword
  ON grants_search_queries(keyword);
