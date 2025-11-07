"""
Generate synthetic project data for authors based on their publication keywords

1. Retrieves all PIs from the database
2. For each PI, extracts keywords from their publications (titles/topics)
3. Matches keywords with medical_keywords.json to find relevant categories
4. Generates 3-10 synthetic projects per author with realistic data
5. Replaces placeholder projects with new synthetic projects
"""

import argparse
import json
import random
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from db_helper import connect_db


def load_medical_keywords(keywords_path: str) -> Dict[str, Dict]:
    """Load medical keywords dictionary from JSON file."""
    with open(keywords_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_keywords_from_text(text: str) -> Set[str]:
    """Extract keywords from text by splitting and normalizing."""
    if not text:
        return set()
    
    # Normalize: lowercase, remove punctuation, split
    text_lower = text.lower()
    # Remove common punctuation but keep hyphens for compound terms
    text_clean = re.sub(r'[^\w\s-]', ' ', text_lower)
    # Split on whitespace
    words = text_clean.split()
    # Filter out very short words and common stop words
    stop_words = {'the', 'a', 'an', 'and', 'or', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which', 'who', 'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'now'}
    keywords = {w for w in words if len(w) > 2 and w not in stop_words}
    return keywords


def match_keywords_to_categories(author_keywords: Set[str], medical_keywords: Dict[str, Dict]) -> List[str]:
    """Match author keywords with medical keyword categories.
    
    Returns a list of category names that match the author's keywords.
    Uses both exact matches and substring matches for better coverage.
    """
    matched_categories = []
    author_keywords_lower = {kw.lower() for kw in author_keywords}
    
    for category, data in medical_keywords.items():
        category_keywords = {kw.lower() for kw in data.get('keywords', [])}
        
        # Check for exact matches
        if author_keywords_lower & category_keywords:
            matched_categories.append(category)
            continue
        
        # Check for substring matches (author keyword contains category keyword or vice versa)
        for author_kw in author_keywords_lower:
            for cat_kw in category_keywords:
                if author_kw in cat_kw or cat_kw in author_kw:
                    matched_categories.append(category)
                    break
            if category in matched_categories:
                break
    
    # Remove duplicates while preserving order
    seen = set()
    unique_categories = []
    for cat in matched_categories:
        if cat not in seen:
            seen.add(cat)
            unique_categories.append(cat)
    
    return unique_categories


def get_author_publications(cxn: sqlite3.Connection, person_id: int) -> List[Dict]:
    """Get all publications for a given author."""
    cur = cxn.cursor()
    cur.execute("""
        SELECT p.id, p.title, p.topic, p.journal, p.year
        FROM pubs p
        JOIN author_pub_relation apr ON apr.pub_id = p.id
        WHERE apr.person_id = ?
        ORDER BY p.year DESC NULLS LAST
    """, (person_id,))
    return [dict(zip(['id', 'title', 'topic', 'journal', 'year'], row)) for row in cur.fetchall()]


def extract_author_keywords(cxn: sqlite3.Connection, person_id: int) -> Set[str]:
    """Extract keywords from an author's publications."""
    publications = get_author_publications(cxn, person_id)
    all_keywords = set()
    
    for pub in publications:
        # Extract from title
        if pub.get('title'):
            all_keywords.update(extract_keywords_from_text(pub['title']))
        # Extract from topic
        if pub.get('topic'):
            all_keywords.update(extract_keywords_from_text(pub['topic']))
    
    return all_keywords


def generate_random_date_range() -> Tuple[datetime, Optional[datetime]]:
    """Generate a random date range within past 3 years to next 3 years.
    
    half of projects will be ongoing (no end_date).
    """
    today = datetime.now()
    past_3_years = today - timedelta(days=3*365)
    future_3_years = today + timedelta(days=3*365)
    
    # Random start date (past 3 years to future 3 years)
    start_range_days = (past_3_years - today).days
    end_range_days = (future_3_years - today).days
    start_days_offset = random.randint(start_range_days, end_range_days)
    start_date = today + timedelta(days=start_days_offset)

    if random.random() < 0.5:  # half of projects will be ongoing (no end date)
        end_date = None
    else:
        # End date between start_date and future_3_years
        max_duration_days = (future_3_years - start_date).days
        if max_duration_days > 0:
            duration_days = random.randint(30, max_duration_days)  # At least 30 days duration
            end_date = start_date + timedelta(days=duration_days)
        else:
            # Start date is in the future, make it ongoing
            end_date = None
    
    return start_date, end_date


def generate_project_title(keyword: str, project_number: int) -> str:
    """Generate project title in format: random_keyword_project_number."""
    return f"{keyword}_project_{project_number}"


def get_random_status() -> str:
    """Get a random status from allowed list."""
    statuses = ['idea', 'planning', 'data-collection', 'analysis', 'manuscript', 'submitted', 'funded', 'inactive']
    return random.choice(statuses)


def delete_placeholder_projects(cxn: sqlite3.Connection, person_id: int):
    """Delete placeholder projects for an author (those with 'Auto:' prefix).
    
    Note: Foreign key constraints with ON DELETE CASCADE will automatically
    remove related records in people_project_relation and project_pub_relation.
    """
    cur = cxn.cursor()
    # First, get the project IDs to delete
    cur.execute("""
        SELECT pr.id
        FROM projects pr
        JOIN people_project_relation ppr ON ppr.project_id = pr.id
        WHERE ppr.person_id = ? AND pr.title LIKE 'Auto:%'
    """, (person_id,))
    project_ids = [row[0] for row in cur.fetchall()]
    
    # Delete the projects (cascade will handle relations)
    if project_ids:
        placeholders = ','.join('?' * len(project_ids))
        cur.execute(f"""
            DELETE FROM projects
            WHERE id IN ({placeholders})
        """, project_ids)


def create_synthetic_projects(
    cxn: sqlite3.Connection,
    person_id: int,
    matched_categories: List[str],
    num_projects: int
) -> List[int]:
    """Create synthetic projects for an author."""
    if not matched_categories:
        # If no matched categories, use a default set
        matched_categories = ['clinical_research', 'epidemiology', 'healthcare_delivery']
    
    cur = cxn.cursor()
    project_ids = []
    current_time = datetime.now()
    
    for i in range(1, num_projects + 1):
        # Generate fields
        category = random.choice(matched_categories)
        title = generate_project_title(category, i)
        start_date, end_date = generate_random_date_range()
        status = get_random_status()
        
        # Insert project
        cur.execute("""
            INSERT INTO projects(title, stage, start_date, end_date, source, created_at, updated_at)
            VALUES(?, ?, ?, ?, 'synthetic', ?, ?)
        """, (title, status, start_date.date(), end_date.date() if end_date else None, current_time, current_time))
        
        project_id = cur.lastrowid
        
        # Link to person
        cur.execute("""
            INSERT OR IGNORE INTO people_project_relation(person_id, project_id, role)
            VALUES(?, ?, 'PI')
        """, (person_id, project_id))
        
        project_ids.append(project_id)
    
    return project_ids


def process_author(
    cxn: sqlite3.Connection,
    person_id: int,
    full_name: str,
    medical_keywords: Dict[str, Dict]
):
    """Process a single author: extract keywords, generate projects."""
    # Extract keywords from publications
    author_keywords = extract_author_keywords(cxn, person_id)
    
    # Match with medical keywords
    matched_categories = match_keywords_to_categories(author_keywords, medical_keywords)
    
    # Generate random number of projects (3-10)
    num_projects = random.randint(3, 10)
    
    # Delete placeholder projects
    delete_placeholder_projects(cxn, person_id)
    
    # Create synthetic projects
    project_ids = create_synthetic_projects(cxn, person_id, matched_categories, num_projects)
    
    print(f"  {full_name}: Generated {num_projects} projects (matched {len(matched_categories)} categories)")
    return len(project_ids)


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic project data for authors based on their publications."
    )
    parser.add_argument(
        "--db",
        default="tracker.db",
        help="Path to SQLite database (default: tracker.db)"
    )
    parser.add_argument(
        "--keywords",
        default="app/medical_keywords.json",
        help="Path to medical keywords JSON file (default: app/medical_keywords.json)"
    )
    args = parser.parse_args()
    
    # Load medical keywords
    keywords_path = Path(args.keywords)
    if not keywords_path.exists():
        raise FileNotFoundError(f"Medical keywords file not found: {keywords_path}")
    
    medical_keywords = load_medical_keywords(str(keywords_path))
    print(f"Loaded {len(medical_keywords)} medical keyword categories")
    
    # Connect to database
    db_path = Path(args.db)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    
    cxn = connect_db(str(db_path))
    
    # Get all PIs
    cur = cxn.cursor()
    cur.execute("""
        SELECT id, full_name, first_name, last_name
        FROM people
        WHERE role = 'PI'
        ORDER BY last_name, first_name
    """)
    authors = cur.fetchall()
    
    print(f"\nFound {len(authors)} PIs to process\n")
    
    total_projects = 0
    for person_id, full_name, first_name, last_name in authors:
        display_name = full_name or f"{first_name} {last_name}".strip()
        try:
            num_created = process_author(cxn, person_id, display_name, medical_keywords)
            total_projects += num_created
            cxn.commit()
        except Exception as e:
            cxn.rollback()
            print(f"  ERROR processing {display_name}: {e}")
    
    print(f"\nCompleted! Generated {total_projects} synthetic projects for {len(authors)} authors")
    cxn.close()


if __name__ == "__main__":
    main()

