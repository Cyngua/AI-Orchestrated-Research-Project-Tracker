"""
Create projects from existing publications.

This script:
1. Finds publications that don't have associated projects
2. Creates projects from these publications with:
   - Title from publication title
   - Abstract from publication abstract (if available)
   - Stage set to "submitted" or "funded" (since they're published)
   - Source = "pubmed"
3. Links publications to projects via project_pub_relation
4. Links authors to projects via people_project_relation
"""

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from db_helper import connect_db


def get_publications_without_projects(cxn: sqlite3.Connection) -> List[Dict]:
    """Get publications that don't have associated projects."""
    cur = cxn.cursor()
    
    # Get publications without projects
    # Note: pubs table doesn't have abstract column, so we'll use title and topic
    query = """
        SELECT p.id, p.pmid, p.title, p.topic, p.journal, p.year, p.authors_json
        FROM pubs p
        LEFT JOIN project_pub_relation ppr ON p.id = ppr.pub_id
        WHERE ppr.pub_id IS NULL
        ORDER BY p.year DESC NULLS LAST, p.id DESC
    """
    
    cur.execute(query)
    rows = cur.fetchall()
    
    return [
        {
            'id': row[0],
            'pmid': row[1],
            'title': row[2],
            'topic': row[3],
            'journal': row[4],
            'year': row[5],
            'authors_json': row[6]
        }
        for row in rows
    ]


def get_publication_authors(cxn: sqlite3.Connection, pub_id: int) -> List[int]:
    """Get author person_ids for a publication."""
    cur = cxn.cursor()
    cur.execute("""
        SELECT DISTINCT person_id
        FROM author_pub_relation
        WHERE pub_id = ?
        ORDER BY person_id
    """, (pub_id,))
    return [row[0] for row in cur.fetchall()]


def create_project_from_publication(
    cxn: sqlite3.Connection,
    pub: Dict,
    stage: str = "submitted"
) -> Optional[int]:
    """Create a project from a publication and link them.
    
    Args:
        cxn: Database connection
        pub: Publication dictionary with id, title, abstract, etc.
        stage: Project stage (default: "submitted" for published papers)
    
    Returns:
        Project ID if created, None otherwise
    """
    cur = cxn.cursor()
    
    # Use publication title as project title
    project_title = pub.get('title', f"Project from PMID {pub.get('pmid', 'unknown')}")
    if not project_title or project_title.strip() == '':
        project_title = f"Project from PMID {pub.get('pmid', 'unknown')}"
    
    # Generate abstract from available data
    # Since pubs table doesn't have abstract, create one from title and topic
    abstract_parts = []
    if pub.get('title'):
        abstract_parts.append(f"This project resulted in the publication: {pub['title']}")
    if pub.get('topic'):
        abstract_parts.append(f"Research focus: {pub['topic']}")
    if pub.get('journal'):
        abstract_parts.append(f"Published in: {pub['journal']}")
    if pub.get('year'):
        abstract_parts.append(f"Publication year: {pub['year']}")
    
    project_abstract = ". ".join(abstract_parts) if abstract_parts else None
    
    # Set dates based on publication year
    start_date = None
    end_date = None
    if pub.get('year'):
        try:
            year = int(pub['year'])
            # Assume project started 1-2 years before publication
            start_date = f"{year - 1}-01-01"
            # Project ended when published
            end_date = f"{year}-12-31"
        except (ValueError, TypeError):
            pass
    
    current_time = datetime.now()
    
    # Create project
    try:
        cur.execute("""
            INSERT INTO projects(title, abstract, stage, start_date, end_date, source, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, 'pubmed', ?, ?)
        """, (
            project_title,
            project_abstract,
            stage,
            start_date,
            end_date,
            current_time,
            current_time
        ))
        project_id = cur.lastrowid
    except Exception as e:
        print(f"  ERROR creating project for PMID {pub.get('pmid')}: {e}")
        return None
    
    # Link publication to project
    try:
        cur.execute("""
            INSERT OR IGNORE INTO project_pub_relation(project_id, pub_id)
            VALUES(?, ?)
        """, (project_id, pub['id']))
    except Exception as e:
        print(f"  ERROR linking pub to project for PMID {pub.get('pmid')}: {e}")
        # Rollback project creation
        cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return None
    
    # Link authors to project
    author_ids = get_publication_authors(cxn, pub['id'])
    if not author_ids:
        # If no authors found, try to parse authors_json
        authors_json = pub.get('authors_json')
        if authors_json:
            try:
                authors = json.loads(authors_json) if isinstance(authors_json, str) else authors_json
                # Try to find authors by name
                for author in authors[:1]:  # Just link first author as PI
                    if isinstance(author, dict):
                        last_name = author.get('last', '')
                        first_name = author.get('fore', '')
                        if last_name and first_name:
                            cur.execute("""
                                SELECT id FROM people
                                WHERE first_name = ? AND last_name = ?
                                LIMIT 1
                            """, (first_name, last_name))
                            result = cur.fetchone()
                            if result:
                                author_ids.append(result[0])
            except:
                pass
    
    # Link all authors to project
    for author_id in author_ids:
        # Determine role: first author is PI, others are Co-I
        role = "PI" if author_id == author_ids[0] else "Co-I"
        try:
            cur.execute("""
                INSERT OR IGNORE INTO people_project_relation(person_id, project_id, role)
                VALUES(?, ?, ?)
            """, (author_id, project_id, role))
        except Exception as e:
            print(f"  WARNING: Could not link author {author_id} to project: {e}")
    
    return project_id


def main():
    parser = argparse.ArgumentParser(
        description="Create finished projects from existing publications."
    )
    parser.add_argument(
        "--db",
        default="tracker.db",
        help="Path to SQLite database (default: tracker.db)"
    )
    parser.add_argument(
        "--stage",
        default="submitted",
        choices=["submitted", "funded", "inactive"],
        help="Stage to assign to projects created from publications (default: submitted)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without actually creating projects"
    )
    args = parser.parse_args()
    
    # Connect to database
    db_path = Path(args.db)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    
    cxn = connect_db(str(db_path))
    
    # Get publications without projects
    publications = get_publications_without_projects(cxn)
    
    print(f"Found {len(publications)} publications without associated projects\n")
    
    if args.dry_run:
        print("DRY RUN - Would create projects for:")
        for pub in publications[:10]:  # Show first 10
            print(f"  - PMID {pub.get('pmid')}: {pub.get('title', 'N/A')[:60]}...")
        if len(publications) > 10:
            print(f"  ... and {len(publications) - 10} more")
        return
    
    # Create projects
    created_count = 0
    error_count = 0
    
    for pub in publications:
        try:
            project_id = create_project_from_publication(cxn, pub, stage=args.stage)
            if project_id:
                created_count += 1
                if created_count % 10 == 0:
                    print(f"  Created {created_count} projects...")
            else:
                error_count += 1
        except Exception as e:
            error_count += 1
            print(f"  ERROR processing PMID {pub.get('pmid')}: {e}")
            continue
    
    # Commit all changes
    cxn.commit()
    
    print(f"\nCompleted!")
    print(f"  Created {created_count} projects from publications")
    print(f"  Errors: {error_count}")
    print(f"  Stage: {args.stage}")
    
    cxn.close()


if __name__ == "__main__":
    main()

