"""
Integration test for enhanced author processing functionality:
Tests the complete ETL pipeline with synthetic data to verify:
1) Author extraction from publication JSON
2) People table population with detailed author data
3) Author-publication relationship creation
4) Enhanced affiliation data handling

This test uses synthetic data to avoid external API dependencies.
"""

import json
import sqlite3
import tempfile
import os
from pathlib import Path

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from etl.db_helper import (
    connect_db,
    upsert_person,
    ensure_auto_project_for_faculty,
    upsert_pub_and_link,
    normalize_author_name
)

def create_test_db():
    """Create a temporary test database with schema."""
    # Create temporary database file
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()
    
    # Initialize with schema
    schema_path = Path(__file__).parent.parent / "etl" / "schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
    cxn = sqlite3.connect(temp_db.name)
    cxn.execute("PRAGMA foreign_keys = ON;")
    
    # Read and execute schema
    with open(schema_path, 'r') as f:
        schema_sql = f.read()
    cxn.executescript(schema_sql)
    
    # Add author-publication relationship table
    cxn.execute("""
        CREATE TABLE IF NOT EXISTS author_pub_relation (
          person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
          pub_id    INTEGER NOT NULL REFERENCES pubs(id) ON DELETE CASCADE,
          author_position INTEGER,
          PRIMARY KEY (person_id, pub_id)
        );
    """)
    cxn.execute("CREATE INDEX IF NOT EXISTS idx_author_pub_person ON author_pub_relation(person_id);")
    cxn.execute("CREATE INDEX IF NOT EXISTS idx_author_pub_pub ON author_pub_relation(pub_id);")
    
    cxn.commit()
    cxn.close()
    
    return temp_db.name

def test_author_processing():
    """Test the enhanced author processing functionality with synthetic data."""
    
    print(" Testing enhanced author processing functionality...")
    
    # Create test database
    db_path = create_test_db()
    cxn = connect_db(db_path)
    
    try:
        # Test data - simulate what would come from PubMed API
        test_faculty = {
            "first": "Isibor",
            "last": "Arhuidese", 
            "middle": "",
            "full": "Isibor Arhuidese"
        }
        
        test_publication = {
            "pmid": "TEST456",
            "title": "Enhanced ETL Test Publication",
            "journal": "Test Journal",
            "year": 2024,
            "authors": [
                {"last": "Arhuidese", "fore": "Isibor", "initials": "I", "affiliation": "Yale School of Medicine"},
                {"last": "Smith", "fore": "John", "initials": "J", "affiliation": "Harvard Medical School"},
                {"last": "Johnson", "fore": "Jane", "initials": "J", "affiliation": "Stanford University"}
            ]
        }
        
        # Step 1: Upsert faculty member
        print("1 Upserting faculty member...")
        person_id = upsert_person(cxn, test_faculty, role="PI", affiliation="Yale")
        print(f"   Faculty ID: {person_id}")
        
        # Step 2: Create auto project
        print("2. Creating auto project...")
        project_id = ensure_auto_project_for_faculty(cxn, person_id, test_faculty["full"])
        print(f"   Project ID: {project_id}")
        
        # Step 3: Upsert publication and process authors
        print("3. Processing publication and authors...")
        pub_id = upsert_pub_and_link(cxn, project_id, test_publication)
        print(f"   Publication ID: {pub_id}")
        
        # Step 4: Verify results
        print("4.Verifying results...")
        
        # Check people table
        cur = cxn.cursor()
        cur.execute("""
            SELECT id, first_name, last_name, full_name, affiliation, role
            FROM people 
            WHERE last_name IN ('Arhuidese', 'Smith', 'Johnson')
            ORDER BY last_name
        """)
        people = cur.fetchall()
        print("   People in database:")
        for person in people:
            print(f"       {person[1]} {person[2]} (ID: {person[0]}) - Role: {person[5]}")
            print(f"       Full name: {person[3]}")
            print(f"       Affiliation: {person[4][:60]}..." if person[4] and len(person[4]) > 60 else f"       Affiliation: {person[4]}")
        
        # Check author-publication relationships
        cur.execute("""
            SELECT apr.author_position, p.first_name, p.last_name, p.affiliation
            FROM author_pub_relation apr
            JOIN people p ON apr.person_id = p.id
            WHERE apr.pub_id = ?
            ORDER BY apr.author_position
        """, (pub_id,))
        relations = cur.fetchall()
        print("   Author-publication relationships:")
        for rel in relations:
            print(f"     Position {rel[0]}: {rel[1]} {rel[2]} - {rel[3][:40]}..." if rel[3] and len(rel[3]) > 40 else f"     Position {rel[0]}: {rel[1]} {rel[2]} - {rel[3]}")
        
        # Check project-publication relationship
        cur.execute("""
            SELECT COUNT(*) FROM project_pub_relation 
            WHERE project_id = ? AND pub_id = ?
        """, (project_id, pub_id))
        project_pub_count = cur.fetchone()[0]
        print(f"   Project-publication relationship exists: {project_pub_count > 0}")
        
        # Verify counts
        cur.execute("SELECT COUNT(*) FROM people")
        total_people = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM author_pub_relation")
        total_relations = cur.fetchone()[0]
        
        print(f"\n Final counts:")
        print(f"   Total people: {total_people}")
        print(f"   Total author-publication relations: {total_relations}")
        
        # Assertions for test validation
        assert total_people == 3, f"Expected 3 people, got {total_people}"
        assert total_relations == 3, f"Expected 3 author-publication relations, got {total_relations}"
        assert project_pub_count == 1, f"Expected 1 project-publication relation, got {project_pub_count}"
        
        print("\n All tests passed! Enhanced author processing is working correctly.")
        
    except Exception as e:
        print(f" Test failed with error: {e}")
        raise
    finally:
        cxn.close()
        # Clean up temporary database
        os.unlink(db_path)

def test_name_normalization():
    """Test the name normalization functionality."""
    print("\n Testing name normalization...")
    
    test_cases = [
        {
            "input": {"last": "Arhuidese", "fore": "Isibor J", "initials": "IJ", "affiliation": "Yale"},
            "expected": {"first": "Isibor", "middle": "J", "last": "Arhuidese", "full": "Isibor J Arhuidese"}
        },
        {
            "input": {"last": "Smith", "fore": "John", "initials": "J", "affiliation": "Harvard"},
            "expected": {"first": "John", "middle": "", "last": "Smith", "full": "John Smith"}
        },
        {
            "input": {"last": "Johnson", "fore": "Jane Marie", "initials": "JM", "affiliation": "Stanford"},
            "expected": {"first": "Jane", "middle": "Marie", "last": "Johnson", "full": "Jane Marie Johnson"}
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        result = normalize_author_name(test_case["input"])
        expected = test_case["expected"]
        
        print(f"   Test case {i}: {test_case['input']['fore']} {test_case['input']['last']}")
        
        for key in ["first", "middle", "last", "full"]:
            assert result[key] == expected[key], f"Expected {key}='{expected[key]}', got '{result[key]}'"
        
        print(f"     {result['full']} parsed correctly")
    
    print(" Name normalization tests passed!")

def main():
    """Run all integration tests."""
    print(" Starting enhanced author processing integration tests...\n")
    
    try:
        test_name_normalization()
        test_author_processing()
        print("\n All integration tests completed successfully!")
        
    except Exception as e:
        print(f"\n Integration tests failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
