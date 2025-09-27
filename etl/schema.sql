PRAGMA foreign_keys = ON;

-- =========================
-- People
-- =========================
CREATE TABLE IF NOT EXISTS people (
  id           INTEGER PRIMARY KEY,
  first_name   TEXT,
  last_name    TEXT,
  middle_name  TEXT,
  full_name    TEXT,
  affiliation  TEXT,
  email        TEXT,
  orcid        TEXT,
  role         TEXT
);
CREATE INDEX IF NOT EXISTS idx_people_last_first ON people(last_name, first_name);

-- =========================
-- Projects
-- =========================
CREATE TABLE IF NOT EXISTS projects (
  id           INTEGER PRIMARY KEY,
  title        TEXT NOT NULL,
  abstract     TEXT,
  cois         TEXT,
  stage        TEXT NOT NULL DEFAULT 'idea'
                 CHECK (stage IN ('idea', 'planning', 'data-collection', 'analysis', 'manuscript', 'submitted', 'funded', 'inactive')),
  start_date   DATE,
  end_date     DATE,
  source       TEXT,     -- 'pubmed','reporter','grants.gov','manual','synthetic'
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS trg_projects_updated_at
AFTER UPDATE ON projects
FOR EACH ROW
BEGIN
  UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE INDEX IF NOT EXISTS idx_projects_title ON projects(title);
CREATE INDEX IF NOT EXISTS idx_projects_stage ON projects(stage);

-- People Projects Relation (many to many)
CREATE TABLE IF NOT EXISTS people_project_relation (
  person_id  INTEGER NOT NULL REFERENCES people(id)   ON DELETE CASCADE,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  role       TEXT,   -- 'PI','Co-I','Contributor', etc.
  PRIMARY KEY (person_id, project_id)
);

-- Project tags
CREATE TABLE IF NOT EXISTS tags (
  id         INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  tag        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tags_project ON tags(project_id);
CREATE INDEX IF NOT EXISTS idx_tags_tag     ON tags(tag);

-- =========================
-- Publications (PubMed)
-- =========================
CREATE TABLE IF NOT EXISTS pubs (
  id           INTEGER PRIMARY KEY,
  pmid         TEXT UNIQUE,
  title        TEXT,
  topic        TEXT,  -- abdominal aortic aneurysm, peripheral arterial disease, etc.
  journal      TEXT,
  year         INTEGER,
  authors_json TEXT
);

-- Project Publication Relation (many to many)
CREATE TABLE IF NOT EXISTS project_pub_relation (
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  pub_id     INTEGER NOT NULL REFERENCES pubs(id)     ON DELETE CASCADE,
  PRIMARY KEY (project_id, pub_id)
);
CREATE INDEX IF NOT EXISTS idx_project_pub_pub ON project_pub_relation(pub_id);

-- Publication topics table (PubMed API)
CREATE TABLE IF NOT EXISTS topics (
  id    INTEGER PRIMARY KEY,
  name  TEXT UNIQUE NOT NULL
);

-- Publication and topics relation table
CREATE TABLE pub_topic_relation (
  pub_id   INTEGER NOT NULL REFERENCES pubs(id) ON DELETE CASCADE,
  topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  PRIMARY KEY (pub_id, topic_id)
);


-- =========================
-- Grants (NIH)
-- =========================
-- Core grant (one row per NIH core project number)
CREATE TABLE IF NOT EXISTS grants_core (
  id               INTEGER PRIMARY KEY,
  core_project_num TEXT NOT NULL UNIQUE,   -- e.g., 'K23DK128569'
  agency           TEXT NOT NULL DEFAULT 'NIH',
  organization     TEXT NOT NULL DEFAULT 'YALE UNIVERSITY'
  status           TEXT CHECK (status IN ('active','completed','pending','unknown')) DEFAULT 'unknown',
  mechanism        TEXT,                   -- R01, R21, K23, etc.
  deadline         DATE,                   -- only used for NOFOs (Grants.gov); NULL for funded awards
  fit_score        REAL,                   -- optional ranking
  notes            TEXT
);

-- Per-fiscal-year slice (yearly award facts)
CREATE TABLE IF NOT EXISTS grants_fy (
  id               INTEGER PRIMARY KEY,
  grant_id         INTEGER NOT NULL REFERENCES grants_core(id) ON DELETE CASCADE,
  project_num      TEXT NOT NULL,      -- e.g., '1K23DK128569-01A1'
  fiscal_year      INTEGER NOT NULL,
  award_amount     INTEGER,
  UNIQUE (grant_id, fiscal_year)
);
CREATE INDEX IF NOT EXISTS idx_grants_fy_year ON grants_fy(fiscal_year);

-- Project Grant Relation Table (many to many)
CREATE TABLE IF NOT EXISTS project_grant_relation (
  project_id  INTEGER NOT NULL REFERENCES projects(id)    ON DELETE CASCADE,
  grant_id    INTEGER NOT NULL REFERENCES grants_core(id) ON DELETE CASCADE,
  role        TEXT,          -- 'primary support','supplement','related'
  source      TEXT,          -- 'manual','pubmed to reporter','reporter-only','inferred'
  notes       TEXT,
  PRIMARY KEY (project_id, grant_id)
);
CREATE INDEX IF NOT EXISTS idx_project_grant_grant ON project_grant_relation(grant_id);

CREATE TABLE IF NOT EXISTS links (
  link_id     INTEGER PRIMARY KEY,
  project_id  INTEGER REFERENCES projects(id)    ON DELETE CASCADE,
  grant_id    INTEGER REFERENCES grants_core(id) ON DELETE CASCADE,
  type        TEXT,    -- 'reporter','nofo','protocol','registry','drive','figshare', ...
  url         TEXT NOT NULL,
  CHECK (
    (project_id IS NOT NULL AND grant_id IS NULL) OR
    (project_id IS NULL AND grant_id IS NOT NULL)
  )
);
