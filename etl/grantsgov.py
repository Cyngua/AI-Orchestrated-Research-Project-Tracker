"""
Grants.gov etl

Examples:
# 1) Basic vascular keywords, Health category, HHS, posted/forecasted
python grantsgov.py \
  --keyword "vascular OR aneurysm OR carotid OR peripheral arterial disease" \
  --statuses "posted|forecasted" \
  --rows 50 \
  --pages 2 \
  -o ../data/sample_data/grantsgov_health_vascular.json

# 2) Bias to NIH cardiovascular ALN (CFDA 93.837)
python grantsgov.py \
  --keyword "abdominal aortic aneurysm OR peripheral arterial disease" \
  --aln 93.837 \
  --rows 10 \
  -o ../data/sample_data/grantsgov_aaa_pad_nih.json

# 3) Fetch detailed information for each opportunity
python grantsgov.py \
  --keyword "vascular OR aneurysm OR carotid OR peripheral arterial disease" \
  --statuses "posted|forecasted" \
  --rows 50 \
  --pages 2 \
  --details \
  -o ../data/sample_data/grantsgov_health_vascular_details.json

# 4) Load into database
python etl/grantsgov.py \
    --keyword "health OR medicine OR medical OR clinical OR research OR biomedical OR healthcare OR treatment OR therapy OR diagnosis OR prevention OR disease OR patient OR clinical trial OR study" \
    --statuses "posted|forecasted|closed|archived" \
    --rows 50 \
    --pages 10 \
    --details \
    --load-db
"""

import argparse, json, datetime as dt, sqlite3
from typing import Any, Dict, List, Optional
import requests
from tqdm import tqdm
from pathlib import Path

SEARCH_URL = "https://api.grants.gov/v1/api/search2"

def parse_date_us(s: Optional[str]) -> Optional[str]:
    """Convert 'MM/DD/YYYY' -> 'YYYY-MM-DD' (or return None)."""
    if not s:
        return None
    try:
        m, d, y = s.split("/")
        return f"{y}-{int(m):02d}-{int(d):02d}"
    except Exception:
        return None

def normalize_hit(h: Dict[str, Any]) -> Dict[str, Any]:
    """Pick fields useful for scoring & display."""
    return {
        "grantsgov_id": h.get("id"),
        "opportunity_number": h.get("number"),
        "title": h.get("title"),
        "agency_code": h.get("agencyCode"),
        "agency_name": h.get("agencyName"),
        "opp_status": h.get("oppStatus"),
        "doc_type": h.get("docType"),
        "open_date": parse_date_us(h.get("openDate")),
        "close_date": parse_date_us(h.get("closeDate")),
        "aln_list": h.get("alnist", []),   # Assistance Listings (CFDA)
        "opportunity_category": h.get("opportunityCategory"),
        "post_date": parse_date_us(h.get("postDate")),
        "archive_date": parse_date_us(h.get("archiveDate")),
    }

def fetch_opportunity_details(opportunity_id: str) -> Dict[str, Any]:
    """Fetch detailed information for a specific opportunity."""
    detail_url = "https://api.grants.gov/v1/api/fetchOpportunity"
    payload = {"opportunityId": opportunity_id}
    
    try:
        response = requests.post(detail_url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get("errorcode") != 0:
            return {}
            
        return data.get("data", {})
    except Exception as e:
        print(f"Error fetching details for opportunity {opportunity_id}: {e}")
        return {}

def normalize_detailed_hit(details: Dict[str, Any]) -> Dict[str, Any]:
    """Extract useful fields from detailed opportunity data."""
    synopsis = details.get("synopsis", {})
    
    return {
        "grantsgov_id": details.get("id"),
        "opportunity_number": details.get("opportunityNumber"),
        "title": details.get("opportunityTitle"),
        "agency_code": details.get("owningAgencyCode"),
        "agency_name": synopsis.get("agencyDetails", {}).get("agencyName"),
        "opp_status": details.get("ost", "").lower(),
        "doc_type": details.get("docType"),
        "open_date": parse_date_us(synopsis.get("postingDate")),
        "close_date": parse_date_us(synopsis.get("responseDate")),
        "post_date": parse_date_us(synopsis.get("postingDate")),
        "archive_date": parse_date_us(synopsis.get("archiveDate")),
        
        # Detailed fields
        "description": synopsis.get("synopsisDesc", ""),
        "award_ceiling": synopsis.get("awardCeiling"),
        "award_floor": synopsis.get("awardFloor"),
        "cost_sharing": synopsis.get("costSharing", False),
        "applicant_eligibility": synopsis.get("applicantEligibilityDesc", ""),
        "agency_contact_name": synopsis.get("agencyContactName", ""),
        "agency_contact_phone": synopsis.get("agencyContactPhone", ""),
        "agency_contact_email": synopsis.get("agencyContactEmail", ""),
        "funding_desc_link": synopsis.get("fundingDescLinkUrl", ""),
        
        # Categories and types
        "opportunity_category": details.get("opportunityCategory", {}).get("description", ""),
        "funding_instruments": [item.get("description", "") for item in synopsis.get("fundingInstruments", [])],
        "funding_activity_categories": [item.get("description", "") for item in synopsis.get("fundingActivityCategories", [])],
        "applicant_types": [item.get("description", "") for item in synopsis.get("applicantTypes", [])],
        
        # CFDA numbers
        "cfda_numbers": [item.get("cfdaNumber", "") for item in details.get("cfdas", [])],
        "cfda_program_titles": [item.get("programTitle", "") for item in details.get("cfdas", [])],
        
        # Additional metadata
        "revision": details.get("revision"),
        "listed": details.get("listed"),
        "publisher_uid": details.get("publisherUid"),
        "modified_comments": details.get("modifiedComments", ""),
    }

def search_once(payload: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(SEARCH_URL, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json().get("data", {})
    return {
        "hitCount": data.get("hitCount", 0),
        "searchParams": data.get("searchParams", {}),
        "hits": data.get("oppHits", []) or []
    }

def run_search(keyword: str,
               rows: int,
               pages: int,
               start: int,
               statuses: str,
               aln: Optional[str],
               fetch_details: bool = False) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    total_seen = 0
    start_record = start

    for p in tqdm(range(pages)):
        # Build payload with only keyword and status filters
        payload = {
            "rows": rows,
            "startRecordNum": start_record,
            "keyword": keyword,
            "oppStatuses": statuses
        }
        
        # Only add ALN if specified
        if aln:
            payload["aln"] = aln

        page = search_once(payload)
        hits = page["hits"]
        if not hits:
            break

        for h in tqdm(hits):
            if fetch_details:
                # Fetch detailed information for each opportunity
                opp_id = h.get("id")
                if opp_id:
                    details = fetch_opportunity_details(opp_id)
                    if details:
                        results.append(normalize_detailed_hit(details))
                    else:
                        # Fallback to basic info if details fetch fails
                        results.append(normalize_hit(h))
                else:
                    results.append(normalize_hit(h))
            else:
                results.append(normalize_hit(h))
        total_seen += len(hits)
        start_record += rows

        # stop if we've pulled everything reported by the API
        if total_seen >= page.get("hitCount", total_seen):
            break

    return {
        "query": {
            "keyword": keyword,
            "statuses": statuses,
            "aln": aln,
            "rows": rows,
            "pages": pages,
            "start": start
        },
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "count": len(results),
        "results": results
    }

def load_to_database(results: List[Dict[str, Any]], query_info: Dict[str, Any], db_path: str = "grants_opportunity.db"):
    """Load search results directly into the database."""
    
    if not Path(db_path).exists():
        print(f" Database not found: {db_path}")
        print("Run 'python etl/init_grants_opportunity_db.py' first to create the database")
        return False
    
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    
    try:
        cursor = conn.cursor()
        
        # Insert search query record
        cursor.execute("""
            INSERT INTO grants_search_queries 
            (keyword, statuses, agencies, category, aln, rows_per_page, pages_requested, 
             start_record, total_results, output_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            query_info.get('keyword', ''),
            query_info.get('statuses', ''),
            query_info.get('agencies', ''),
            query_info.get('category', ''),
            query_info.get('aln'),
            query_info.get('rows', 0),
            query_info.get('pages', 0),
            query_info.get('start', 0),
            len(results),
            None  # No output file when loading to database
        ))
        
        # Filter out opportunities without grantsgov_id
        valid_results = [opp for opp in results if opp.get('grantsgov_id') is not None]
        filtered_count = len(results) - len(valid_results)
        
        if filtered_count > 0:
            print(f" Filtered out {filtered_count} opportunities without grantsgov_id")
        
        if not valid_results:
            print(" No valid opportunities to load (all had null grantsgov_id)")
            return True
        
        # Process each opportunity
        print(f" Loading {len(valid_results)} opportunities into database...")
        
        for opp in valid_results:
            cursor.execute("""
                INSERT OR REPLACE INTO grants_opportunity 
                (grantsgov_id, opportunity_number, title, agency_code, agency_name,
                 opp_status, doc_type, open_date, close_date, post_date, archive_date,
                 opportunity_category, description, award_ceiling, award_floor, cost_sharing,
                 applicant_eligibility, agency_contact_name, agency_contact_phone, 
                 agency_contact_email, funding_desc_link, revision, listed, publisher_uid,
                 modified_comments)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                opp.get('grantsgov_id'),
                opp.get('opportunity_number'),
                opp.get('title'),
                opp.get('agency_code'),
                opp.get('agency_name'),
                opp.get('opp_status'),
                opp.get('doc_type'),
                opp.get('open_date'),
                opp.get('close_date'),
                opp.get('post_date'),
                opp.get('archive_date'),
                opp.get('opportunity_category'),
                opp.get('description'),
                opp.get('award_ceiling'),
                opp.get('award_floor'),
                opp.get('cost_sharing'),
                opp.get('applicant_eligibility'),
                opp.get('agency_contact_name'),
                opp.get('agency_contact_phone'),
                opp.get('agency_contact_email'),
                opp.get('funding_desc_link'),
                opp.get('revision'),
                opp.get('listed'),
                opp.get('publisher_uid'),
                opp.get('modified_comments')
            ))
        
        conn.commit()
        print(f" Successfully loaded {len(valid_results)} opportunities into database")
        return True
        
    except Exception as e:
        print(f" Error loading data: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def parse_args():
    ap = argparse.ArgumentParser(description="Fetch Grants.gov opportunities via search2 and save JSON.")
    ap.add_argument("--keyword", required=True, help='e.g. "vascular OR aneurysm OR carotid"')
    ap.add_argument("--statuses", default="posted|forecasted", help='e.g. "posted|forecasted|closed"')
    ap.add_argument("--aln", default=None, help="Assistance Listing (CFDA), e.g., 93.837")
    ap.add_argument("--rows", type=int, default=50, help="Rows per page (API supports ~50).")
    ap.add_argument("--pages", type=int, default=1, help="How many pages to fetch.")
    ap.add_argument("--start", type=int, default=0, help="Start record number (pagination offset).")
    ap.add_argument("--details", action="store_true", help="Fetch detailed information for each opportunity (slower)")
    ap.add_argument("--load-db", action="store_true", help="Load results directly into database instead of saving JSON")
    ap.add_argument("--db", default="grants_opportunity.db", help="Database file path (used with --load-db)")
    ap.add_argument("-o", "--out", help="Output JSON filepath (required if not using --load-db)")
    return ap.parse_args()

def main():
    args = parse_args()
    
    # Validate arguments
    if not args.load_db and not args.out:
        print(" Error: Either --load-db or --out must be specified")
        return
    
    payload = run_search(
        keyword=args.keyword,
        rows=args.rows,
        pages=args.pages,
        start=args.start,
        statuses=args.statuses,
        aln=args.aln,
        fetch_details=args.details
    )
    
    if args.load_db:
        # Load directly into database
        success = load_to_database(payload['results'], payload['query'], args.db)
        if success:
            print(f" Successfully loaded {payload['count']} opportunities into database")
        else:
            print(" Failed to load data into database")
    else:
        # Save to JSON file
        os_path = args.out
        # ensure parent dirs exist
        import os
        os.makedirs(os.path.dirname(os_path) or ".", exist_ok=True)
        with open(os_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f" Saved {payload['count']} opportunities to {args.out}")

if __name__ == "__main__":
    main()
