"""
Query and explore grants opportunity data.
"""

import sqlite3
import argparse
from pathlib import Path
from typing import List, Dict, Any

def query_opportunities(db_path: str, 
                       status: str = None,
                       agency: str = None,
                       keyword: str = None,
                       limit: int = 10) -> List[Dict[str, Any]]:
    """Query opportunities with optional filters."""
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    cursor = conn.cursor()
    
    try:
        # Build query with optional filters
        where_conditions = []
        params = []
        
        if status:
            where_conditions.append("opp_status = ?")
            params.append(status)
        
        if agency:
            where_conditions.append("(agency_code LIKE ? OR agency_name LIKE ?)")
            params.extend([f"%{agency}%", f"%{agency}%"])
        
        if keyword:
            where_conditions.append("title LIKE ?")
            params.append(f"%{keyword}%")
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        query = f"""
            SELECT 
                grantsgov_id,
                opportunity_number,
                title,
                agency_code,
                agency_name,
                opp_status,
                doc_type,
                open_date,
                close_date,
                post_date
            FROM grants_opportunity 
            {where_clause}
            ORDER BY open_date DESC, post_date DESC
            LIMIT ?
        """
        params.append(limit)
        
        cursor.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]
        
        return results
        
    finally:
        conn.close()

def get_summary_stats(db_path: str) -> Dict[str, Any]:
    """Get summary statistics from the database."""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        stats = {}
        
        # Total opportunities
        cursor.execute("SELECT COUNT(*) FROM grants_opportunity")
        stats['total_opportunities'] = cursor.fetchone()[0]
        
        # By status
        cursor.execute("""
            SELECT opp_status, COUNT(*) 
            FROM grants_opportunity 
            GROUP BY opp_status 
            ORDER BY COUNT(*) DESC
        """)
        stats['by_status'] = dict(cursor.fetchall())
        
        # By agency
        cursor.execute("""
            SELECT agency_code, COUNT(*) 
            FROM grants_opportunity 
            WHERE agency_code IS NOT NULL
            GROUP BY agency_code 
            ORDER BY COUNT(*) DESC 
            LIMIT 10
        """)
        stats['by_agency'] = dict(cursor.fetchall())
        
        # Recent opportunities
        cursor.execute("""
            SELECT COUNT(*) 
            FROM grants_opportunity 
            WHERE post_date >= date('now', '-30 days')
        """)
        stats['recent_30_days'] = cursor.fetchone()[0]
        
        return stats
        
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="Query grants opportunity data")
    parser.add_argument("--db", default="grants_opportunity.db", 
                       help="Path to the grants opportunity database file")
    parser.add_argument("--status", help="Filter by opportunity status")
    parser.add_argument("--agency", help="Filter by agency (partial match)")
    parser.add_argument("--keyword", help="Filter by keyword in title")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of results")
    parser.add_argument("--stats", action="store_true", help="Show summary statistics")
    
    args = parser.parse_args()
    
    if not Path(args.db).exists():
        print(f" Database not found: {args.db}")
        return
    
    if args.stats:
        print(" Summary Statistics:")
        print("=" * 50)
        stats = get_summary_stats(args.db)
        
        print(f"Total opportunities: {stats['total_opportunities']}")
        print(f"Recent (30 days): {stats['recent_30_days']}")
        
        print("\nBy Status:")
        for status, count in stats['by_status'].items():
            print(f"  {status}: {count}")
        
        print("\nTop Agencies:")
        for agency, count in stats['by_agency'].items():
            print(f"  {agency}: {count}")
        
        return
    
    # Query opportunities
    results = query_opportunities(
        args.db, 
        status=args.status,
        agency=args.agency,
        keyword=args.keyword,
        limit=args.limit
    )
    
    if not results:
        print("No opportunities found matching criteria.")
        return
    
    print(f"Found {len(results)} opportunities:")
    print("=" * 80)
    
    for i, opp in enumerate(results, 1):
        print(f"{i}. {opp['title']}")
        print(f"   ID: {opp['grantsgov_id']} | Number: {opp['opportunity_number']}")
        print(f"   Agency: {opp['agency_name'] or opp['agency_code']}")
        print(f"   Status: {opp['opp_status']} | Type: {opp['doc_type']}")
        print(f"   Open: {opp['open_date']} | Close: {opp['close_date']}")
        print()

if __name__ == "__main__":
    main()
