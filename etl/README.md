# ETL

## Database Schema
Originally Proposed Version:
* projects(project_id, title, abstract, pi, cois, keywords, stage, start_date, end_date, source, created_at, updated_at)
* people(person_id, name, affiliation, email, orcid, role) 
* pubs(pub_id, project_id, pmid, title, journal, year, authors_json) 
* grants(grant_id, project_id, agency, mechanism, url, deadline, fit_score, notes)
* links(link_id, project_id, type, url) 
* tags(project_id, tag)
* Indexes: projects(title), pubs(pmid), grants(deadline), tags(tag)

Refined Version (Sep 25):
![alt text](../figures/schema.png)

## Project Tracker Main Database Setup (SQLite)

This project uses SQLite for a lightweight prototype database.
**Create the DB:**
```bash
sqlite3 tracker.db < etl/schema.sql
# or
cd etl
python init_db.py

# inspect db (run under the parent folder)
sqlite3 tracker.db ".tables"
sqlite3 tracker.db "SELECT * FROM projects LIMIT 5;"
```

## Grants Opportunity Database

The system includes a separate database for tracking grants.gov opportunities with detailed information including descriptions, award amounts, eligibility requirements, and contact information.

### Initialize Grants Opportunity Database

```bash
# Create the grants opportunity database
cd etl
python init_grants_opportunity_db.py
```

### Fetch and Load Grants Data

The `grantsgov.py` script can fetch grants.gov opportunities and optionally load them directly into the database:

```bash
# Basic search - saves to JSON file
cd -
python etl/grantsgov.py \
  --keyword "vascular OR aneurysm OR carotid OR peripheral arterial disease" \
  --statuses "posted|forecasted" \
  --rows 50 \
  --pages 2 \
  -o data/sample_data/grantsgov_health_vascular.json

# With ALN filter
python etl/grantsgov.py \
  --keyword "abdominal aortic aneurysm OR peripheral arterial disease" \
  --aln 93.837 \
  --statuses "posted|forecasted" \
  --rows 10 \
  -o data/sample_data/grantsgov_aaa_pad_nih.json
```

#### Fetch Detailed Information
```bash
python etl/grantsgov.py \
  --keyword "vascular OR aneurysm OR carotid OR peripheral arterial disease" \
  --statuses "posted|forecasted" \
  --rows 50 \
  --pages 2 \
  --details \
  -o data/sample_data/grantsgov_health_vascular_details.json
```

#### Direct Database Loading
```bash
# Load directly into database (recommended)
python etl/grantsgov.py \
  --keyword "health research" \
  --statuses "posted|forecasted" \
  --rows 20 \
  --pages 1 \
  --details \
  --load-db
```

### Query Grants Data

```bash
# View summary statistics
python tests/query_grants_opportunity.py --stats

# Query opportunities with filters
python tests/query_grants_opportunity.py \
  --status "posted" \
  --agency "NIH" \
  --keyword "health" \
  --limit 5

# View all recent opportunities
python tests/query_grants_opportunity.py --limit 10
```

### Available Data Fields

The grants opportunity database captures comprehensive information:

**Basic Fields:**
- Opportunity ID, number, title
- Agency information (code, name)
- Status (posted, forecasted, closed, archived)
- Dates (open, close, post, archive)
- Document type

**Detailed Fields (with --details flag):**
- Full description/abstract
- Award amounts (ceiling, floor)
- Cost sharing requirements
- Applicant eligibility requirements
- Agency contact information (name, phone, email)
- Funding description links
- Revision and metadata

**Categorical Data:**
- Funding instruments (Grant, Cooperative Agreement, etc.)
- Funding activity categories (Health, Education, etc.)
- Applicant types (Universities, Non-profits, etc.)
- CFDA numbers and program titles