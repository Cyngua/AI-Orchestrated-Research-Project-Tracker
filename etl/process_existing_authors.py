#!/usr/bin/env python3
"""
Script to retroactively process authors from existing publications in the database.
This will extract all authors from the authors_json field and populate the people table.
"""

import sqlite3
import json
from db_helper import connect_db, process_authors_from_publication

def process_existing_publications():
    """Process all existing publications to extract authors."""
    
    db_path = "tracker.db"
    cxn = connect_db(db_path)
    cur = cxn.cursor()
    
    print("Processing existing publications to extract authors...")
    
    # Get all publications with authors_json data
    cur.execute("""
        SELECT id, pmid, title, authors_json 
        FROM pubs 
        WHERE authors_json IS NOT NULL AND authors_json != ''
        ORDER BY id
    """)
    
    publications = cur.fetchall()
    print(f"Found {len(publications)} publications to process.")
    
    processed_count = 0
    author_count = 0
    
    for pub_id, pmid, title, authors_json in publications:
        try:
            # Check if authors are already processed
            cur.execute("SELECT COUNT(*) FROM author_pub_relation WHERE pub_id = ?", (pub_id,))
            existing_relations = cur.fetchone()[0]
            
            if existing_relations > 0:
                print(f"  Skipping PMID {pmid} - authors already processed ({existing_relations} relations)")
                continue
            
            # Process authors for this publication
            author_ids = process_authors_from_publication(cxn, pub_id, authors_json)
            
            if author_ids:
                author_count += len(author_ids)
                processed_count += 1
                print(f"  Processed PMID {pmid}: {len(author_ids)} authors")
                print(f"    Title: {title[:60]}..." if len(title) > 60 else f"    Title: {title}")
            else:
                print(f"  No authors extracted from PMID {pmid}")
                
        except Exception as e:
            print(f"  Error processing PMID {pmid}: {e}")
            continue
    
    # Commit all changes
    cxn.commit()
    
    print(f"\n Processing complete!")
    print(f"   Publications processed: {processed_count}")
    print(f"   Total authors added: {author_count}")
    
    # Show summary statistics
    cur.execute("SELECT COUNT(*) FROM people")
    total_people = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM author_pub_relation")
    total_relations = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(DISTINCT person_id) FROM author_pub_relation")
    unique_authors = cur.fetchone()[0]
    
    print(f"\nDatabase summary:")
    print(f"   Total people: {total_people}")
    print(f"   Total author-publication relations: {total_relations}")
    print(f"   Unique authors with publications: {unique_authors}")
    
    cxn.close()

if __name__ == "__main__":
    process_existing_publications()
