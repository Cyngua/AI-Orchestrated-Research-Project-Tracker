'''
helper functions to feed fetched data into the sqlite database
'''
import sqlite3
import json
from typing import List, Dict, Any, Optional

def connect_db(db_path: str) -> sqlite3.Connection:
    cxn = sqlite3.connect(db_path)
    cxn.execute("PRAGMA foreign_keys = ON;")
    return cxn

# ---------- PubMed Fetched Data ----------
def upsert_person(cxn: sqlite3.Connection, norm: dict, role: str = "PI", affiliation: Optional[str] = None) -> int:
    # Try exact first+last; if collision risk is a concern, add affiliation/orcid later.
    cur = cxn.cursor()
    cur.execute("""
        INSERT INTO people(first_name, last_name, affiliation, role)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(id) DO NOTHING
    """, (norm["first"], norm["last"], affiliation, role))
    # Get id (existing or new)
    cur.execute("""
        SELECT id FROM people
        WHERE first_name = ? AND last_name = ?
        ORDER BY id LIMIT 1
    """, (norm["first"], norm["last"]))
    row = cur.fetchone()
    return int(row[0])

def ensure_auto_project_for_faculty(cxn: sqlite3.Connection, person_id: int, faculty_full_name: str) -> int:
    title = f"Auto: {faculty_full_name} Recent Publications"
    cur = cxn.cursor()
    cur.execute("""
        SELECT pr.id FROM projects pr
        JOIN people_project_relation ppr ON ppr.project_id = pr.id
        WHERE pr.title = ? AND ppr.person_id = ?
        LIMIT 1
    """, (title, person_id))
    row = cur.fetchone()
    if row:
        return int(row[0])

    cur.execute("""
        INSERT INTO projects(title, abstract, stage, source)
        VALUES(?, ?, 'analysis', 'pubmed')
    """, (title, "Auto-created container for recent publications"))
    pid = cur.lastrowid
    cur.execute("""
        INSERT OR IGNORE INTO people_project_relation(person_id, project_id, role)
        VALUES(?, ?, 'PI')
    """, (person_id, pid))
    cxn.commit()
    return int(pid)

def upsert_pub_and_link(cxn: sqlite3.Connection, project_id: int, rec: dict) -> int:
    cur = cxn.cursor()
    authors_json = json.dumps(rec.get("authors", []), ensure_ascii=False)
    cur.execute("""
        INSERT INTO pubs(pmid, title, journal, year, authors_json)
        VALUES(?, ?, ?, ?, ?)
        ON CONFLICT(pmid) DO UPDATE SET
            title=excluded.title,
            journal=excluded.journal,
            year=COALESCE(excluded.year, pubs.year),
            authors_json=excluded.authors_json
    """, (rec["pmid"], rec.get("title"), rec.get("journal"), rec.get("year"), authors_json))

    # fetch pub id
    cur.execute("SELECT id FROM pubs WHERE pmid = ? LIMIT 1", (rec["pmid"],))
    pub_id = int(cur.fetchone()[0])

    # link to project
    cur.execute("""
        INSERT OR IGNORE INTO project_pub_relation(project_id, pub_id)
        VALUES(?, ?)
    """, (project_id, pub_id))

    return pub_id

# ---------- NIH Fetched Data ----------