'''
helper functions to feed fetched data into the sqlite database
'''
import sqlite3
import json
import re
from typing import List, Dict, Any, Optional

def connect_db(db_path: str) -> sqlite3.Connection:
    cxn = sqlite3.connect(db_path)
    cxn.execute("PRAGMA foreign_keys = ON;")
    return cxn

# ---------- Name utilities ----------
def normalize_author_name(author_data: Dict[str, str]) -> Dict[str, str]:
    """Normalize author data from PubMed JSON format."""
    fore = author_data.get("fore", "").strip()
    last = author_data.get("last", "").strip()
    initials = author_data.get("initials", "").strip()
    
    # Construct full name
    full_name_parts = []
    if fore:
        full_name_parts.append(fore)
    if last:
        full_name_parts.append(last)
    full_name = " ".join(full_name_parts)
    
    # Extract middle name from forename if it contains multiple parts
    middle_name = ""
    if fore and " " in fore:
        fore_parts = fore.split()
        fore = fore_parts[0]
        middle_name = " ".join(fore_parts[1:])
    
    return {
        "first": fore,
        "middle": middle_name,
        "last": last,
        "full": full_name,
        "initials": initials
    }

# ---------- PubMed Fetched Data ----------
def upsert_person(cxn: sqlite3.Connection, norm: dict, role: str = "PI", affiliation: Optional[str] = None) -> int:
    """Upsert a person into the people table with enhanced data handling."""
    cur = cxn.cursor()
    
    # Check if person already exists by first_name + last_name
    cur.execute("""
        SELECT id FROM people
        WHERE first_name = ? AND last_name = ?
        ORDER BY id LIMIT 1
    """, (norm["first"], norm["last"]))
    existing_row = cur.fetchone()
    
    if existing_row:
        person_id = int(existing_row[0])
        # Update affiliation if provided and more detailed
        if affiliation and affiliation.strip():
            cur.execute("""
                UPDATE people 
                SET affiliation = ?, full_name = COALESCE(NULLIF(full_name, ''), ?)
                WHERE id = ?
            """, (affiliation, norm.get("full", ""), person_id))
        return person_id
    else:
        # Insert new person
        cur.execute("""
            INSERT INTO people(first_name, last_name, middle_name, full_name, affiliation, role)
            VALUES(?, ?, ?, ?, ?, ?)
        """, (
            norm["first"], 
            norm["last"], 
            norm.get("middle", ""), 
            norm.get("full", ""), 
            affiliation, 
            role
        ))
        return cur.lastrowid

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
        VALUES(?, ?, 'inactive', 'pubmed')
    """, (title, "Auto-created container for recent publications"))
    pid = cur.lastrowid
    cur.execute("""
        INSERT OR IGNORE INTO people_project_relation(person_id, project_id, role)
        VALUES(?, ?, 'PI')
    """, (person_id, pid))
    cxn.commit()
    return int(pid)

def process_authors_from_publication(cxn: sqlite3.Connection, pub_id: int, authors_json: str) -> List[int]:
    """Process authors from publication JSON and create author-publication relationships."""
    cur = cxn.cursor()
    author_ids = []
    
    try:
        authors = json.loads(authors_json) if isinstance(authors_json, str) else authors_json
    except (json.JSONDecodeError, TypeError):
        return author_ids
    
    for position, author_data in enumerate(authors, 1):
        if not isinstance(author_data, dict):
            continue
            
        # Normalize author data
        norm = normalize_author_name(author_data)
        affiliation = author_data.get("affiliation", "").strip()
        
        # Skip if no meaningful name data
        if not norm["first"] and not norm["last"]:
            continue
            
        # Upsert author to people table
        person_id = upsert_person(cxn, norm, role="Author", affiliation=affiliation)
        author_ids.append(person_id)
        
        # Create author-publication relationship
        cur.execute("""
            INSERT OR IGNORE INTO author_pub_relation(person_id, pub_id, author_position)
            VALUES(?, ?, ?)
        """, (person_id, pub_id, position))
    
    return author_ids

def upsert_pub_and_link(cxn: sqlite3.Connection, rec: dict, project_id: Optional[int] = None) -> int:
    """Upsert a publication and optionally link it to a project.
    
    Args:
        cxn: Database connection
        rec: Publication record dictionary
        project_id: Optional project ID to link the publication to. If None, publication
                   is stored but not linked to any project.
    
    Returns:
        Publication ID
    """
    cur = cxn.cursor()
    authors_json = json.dumps(rec.get("authors", []), ensure_ascii=False)
    grants_json = json.dumps(rec.get("grants", []), ensure_ascii=False)
    abstract = rec.get("abstract", "")
    
    # Try to insert with abstract column, fall back to without if column doesn't exist
    try:
        cur.execute("""
            INSERT INTO pubs(pmid, title, journal, year, authors_json, grants_json, abstract)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pmid) DO UPDATE SET
                title=excluded.title,
                journal=excluded.journal,
                year=COALESCE(excluded.year, pubs.year),
                authors_json=excluded.authors_json,
                grants_json=excluded.grants_json,
                abstract=excluded.abstract
        """, (rec["pmid"], rec.get("title"), rec.get("journal"), rec.get("year"), authors_json, grants_json, abstract))
    except sqlite3.OperationalError:
        # Fall back to version without abstract column
        cur.execute("""
            INSERT INTO pubs(pmid, title, journal, year, authors_json, grants_json)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(pmid) DO UPDATE SET
                title=excluded.title,
                journal=excluded.journal,
                year=COALESCE(excluded.year, pubs.year),
                authors_json=excluded.authors_json,
                grants_json=excluded.grants_json
        """, (rec["pmid"], rec.get("title"), rec.get("journal"), rec.get("year"), authors_json, grants_json))

    # fetch pub id
    cur.execute("SELECT id FROM pubs WHERE pmid = ? LIMIT 1", (rec["pmid"],))
    pub_id = int(cur.fetchone()[0])

    # link to project (only if project_id is provided)
    if project_id is not None:
        cur.execute("""
            INSERT OR IGNORE INTO project_pub_relation(project_id, pub_id)
            VALUES(?, ?)
        """, (project_id, pub_id))

    # Process all authors from this publication
    process_authors_from_publication(cxn, pub_id, authors_json)
    
    return pub_id

# ---------- NIH Fetched Data ----------