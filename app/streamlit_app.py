# streamlit run streamlit_app.py
import os
import sqlite3
import pandas as pd
import streamlit as st

DB_PATH = "../tracker.db"
GRANTS_DB_PATH = "../grants_opportunity.db"

# ---------- Helpers ----------
def _db_exists() -> bool:
    return os.path.exists(DB_PATH)

def _db_mtime() -> float:
    """Hashable signal that invalidates caches when the DB file changes."""
    try:
        return os.path.getmtime(DB_PATH)
    except OSError:
        return 0.0

def _grants_db_exists() -> bool:
    return os.path.exists(GRANTS_DB_PATH)

def _grants_db_mtime() -> float:
    """Hashable signal that invalidates caches when the grants DB file changes."""
    try:
        return os.path.getmtime(GRANTS_DB_PATH)
    except OSError:
        return 0.0

# ---------- Data access ----------
@st.cache_resource
def get_conn(db_path: str):
    # For Streamlit + SQLite, allow use across threads.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _ensure_conn():
    if not _db_exists():
        return None
    return get_conn(DB_PATH)

@st.cache_data(show_spinner=False)
def list_faculty_cached(db_mtime: float):
    """Return faculty list; cache invalidates when DB file changes."""
    conn = _ensure_conn()
    if conn:
        q = """
            SELECT p.id,
                   COALESCE(p.first_name,'') || ' ' || COALESCE(p.last_name,'') AS name
            FROM people p
            WHERE p.role = 'PI'
            ORDER BY p.last_name, p.first_name
        """
        return pd.read_sql_query(q, conn)
    # demo fallback
    return pd.DataFrame(
        {"id":[1,2,3], "name":["Isibor Arhuidese","Alan Dardik","Julie Ann Freischlag"]}
    )

@st.cache_data(show_spinner=False)
def fetch_publications_cached(db_mtime: float, faculty_name: str, limit: int = 10):
    conn = _ensure_conn()
    if conn:
        q = """
            SELECT pb.pmid, pb.title, pb.journal, pb.year
            FROM pubs pb
            JOIN project_pub_relation r ON r.pub_id = pb.id
            JOIN projects pr ON pr.id = r.project_id
            LEFT JOIN people_project_relation ppr ON ppr.project_id = pr.id
            LEFT JOIN people pe ON pe.id = ppr.person_id
            WHERE pe.first_name || ' ' || pe.last_name = ?
            ORDER BY pb.year DESC, pb.id DESC
            LIMIT ?
        """
        return pd.read_sql_query(q, conn, params=[faculty_name, limit])
    # demo fallback
    data = [
        {"pmid":"38800123","title":"Endovascular AAA outcomes","journal":"J Vasc Surg","year":2024},
        {"pmid":"38799011","title":"PAD imaging advances","journal":"Circulation","year":2023},
    ]
    return pd.DataFrame(data)[:limit]

@st.cache_data(show_spinner=False)
def fetch_projects_cached(db_mtime: float, faculty_name: str):
    conn = _ensure_conn()
    if conn:
        q = """
            SELECT pr.id as project_id, pr.title, pr.stage, pr.start_date, pr.end_date
            FROM projects pr
            LEFT JOIN people_project_relation ppr ON ppr.project_id = pr.id
            LEFT JOIN people pe ON pe.id = ppr.person_id
            WHERE pe.first_name || ' ' || pe.last_name = ?
            ORDER BY pr.updated_at DESC
        """
        return pd.read_sql_query(q, conn, params=[faculty_name])
    # demo fallback
    return pd.DataFrame([
        {"project_id":101,"title":"AAA biomechanics pilot","stage":"analysis","start_date":"2024-01-01","end_date":None},
        {"project_id":102,"title":"PAD registry build","stage":"planning","start_date":"2024-09-01","end_date":None},
    ])

@st.cache_data(show_spinner=False)
def fetch_grant_fits_cached(db_mtime: float, faculty_name: str):
    conn = _ensure_conn()
    if conn:
        q = """
            SELECT gc.core_project_num, gc.mechanism, pgr.confidence, pgr.role, pgr.notes,
                   COALESCE(pgr.confidence,0) as score
            FROM project_grant_relation pgr
            JOIN grants_core gc ON gc.id = pgr.grant_id
            JOIN people_project_relation ppr ON pgr.project_id = ppr.project_id
            JOIN people pe ON pe.id = ppr.person_id
            WHERE pe.first_name || ' ' || pe.last_name = ?
            ORDER BY score DESC
            LIMIT 10
        """
        return pd.read_sql_query(q, conn, params=[faculty_name])
    # demo fallback
    return pd.DataFrame([
        {"core_project_num":"R01HL123456","mechanism":"R01","role":"inferred","confidence":0.82,"notes":"AAA keywords overlap","score":0.82},
        {"core_project_num":"R21HL987654","mechanism":"R21","role":"inferred","confidence":0.71,"notes":"embolization study","score":0.71},
    ])

@st.cache_data(show_spinner=False)
def fetch_grants_opportunities_cached(grants_db_mtime: float, status_filter: str = None, agency_filter: str = None, open_date_from: str = None, open_date_to: str = None, close_date_from: str = None, close_date_to: str = None, limit: int = 20, offset: int = 0):
    """Fetch grants.gov opportunities from the grants opportunity database."""
    if not _grants_db_exists():
        # Demo fallback data
        return pd.DataFrame([
            {
                "grantsgov_id": "356164",
                "opportunity_number": "RFA-OH-26-002", 
                "title": "Assessment and Evaluation of Emerging Health Conditions",
                "agency_name": "Centers for Disease Control and Prevention - ERA",
                "opp_status": "forecasted",
                "description": "This opportunity supports research on emerging health conditions...",
                "award_ceiling": "200000",
                "close_date": "2026-05-25"
            },
            {
                "grantsgov_id": "355417",
                "opportunity_number": "RFA-OH-25-002",
                "title": "Occupational Safety and Health Education and Research Centers",
                "agency_name": "Centers for Disease Control and Prevention - ERA", 
                "opp_status": "posted",
                "description": "NIOSH invites grant applications for Education and Research Centers...",
                "award_ceiling": "9000000",
                "close_date": "2026-05-25"
            }
        ])
    
    conn = get_conn(GRANTS_DB_PATH)
    
    # Build query with optional filters
    where_conditions = []
    params = []
    
    if status_filter:
        where_conditions.append("opp_status = ?")
        params.append(status_filter)
    
    if agency_filter:
        where_conditions.append("(agency_code LIKE ? OR agency_name LIKE ?)")
        params.extend([f"%{agency_filter}%", f"%{agency_filter}%"])
    
    if open_date_from:
        where_conditions.append("open_date >= ?")
        params.append(open_date_from)
    
    if open_date_to:
        where_conditions.append("open_date <= ?")
        params.append(open_date_to)
    
    if close_date_from:
        where_conditions.append("close_date >= ?")
        params.append(close_date_from)
    
    if close_date_to:
        where_conditions.append("close_date <= ?")
        params.append(close_date_to)
    
    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    
    query = f"""
        SELECT 
            grantsgov_id,
            opportunity_number,
            title,
            agency_name,
            opp_status,
            description,
            award_ceiling,
            award_floor,
            close_date,
            open_date,
            open_date,
            agency_contact_name,
            agency_contact_email,
            funding_desc_link
        FROM grants_opportunity 
        {where_clause}
        ORDER BY close_date DESC, open_date DESC, open_date DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    
    return pd.read_sql_query(query, conn, params=params)

@st.cache_data(show_spinner=False)
def get_grants_filtered_count_cached(grants_db_mtime: float, status_filter: str = None, agency_filter: str = None, open_date_from: str = None, open_date_to: str = None, close_date_from: str = None, close_date_to: str = None):
    """Get count of filtered grants opportunities."""
    if not _grants_db_exists():
        return 0
    
    conn = get_conn(GRANTS_DB_PATH)
    
    # Build query with optional filters (same logic as fetch_grants_opportunities_cached)
    where_conditions = []
    params = []
    
    if status_filter:
        where_conditions.append("opp_status = ?")
        params.append(status_filter)
    
    if agency_filter:
        where_conditions.append("(agency_code LIKE ? OR agency_name LIKE ?)")
        params.extend([f"%{agency_filter}%", f"%{agency_filter}%"])
    
    if open_date_from:
        where_conditions.append("open_date >= ?")
        params.append(open_date_from)
    
    if open_date_to:
        where_conditions.append("open_date <= ?")
        params.append(open_date_to)
    
    if close_date_from:
        where_conditions.append("close_date >= ?")
        params.append(close_date_from)
    
    if close_date_to:
        where_conditions.append("close_date <= ?")
        params.append(close_date_to)
    
    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    
    query = f"SELECT COUNT(*) as total FROM grants_opportunity {where_clause}"
    result = pd.read_sql_query(query, conn, params=params)
    return result.iloc[0]['total']

@st.cache_data(show_spinner=False)
def get_grants_stats_cached(grants_db_mtime: float):
    """Get summary statistics from grants opportunity database."""
    if not _grants_db_exists():
        return {"total": 0, "by_status": {}, "by_agency": {}}
    
    conn = get_conn(GRANTS_DB_PATH)
    
    # Total count
    total_df = pd.read_sql_query("SELECT COUNT(*) as total FROM grants_opportunity", conn)
    total = total_df.iloc[0]['total']
    
    # By status
    status_df = pd.read_sql_query("""
        SELECT opp_status, COUNT(*) as count 
        FROM grants_opportunity 
        GROUP BY opp_status 
        ORDER BY COUNT(*) DESC
    """, conn)
    by_status = dict(zip(status_df['opp_status'], status_df['count']))
    
    # By agency (top 10)
    agency_df = pd.read_sql_query("""
        SELECT agency_name, COUNT(*) as count 
        FROM grants_opportunity 
        WHERE agency_name IS NOT NULL
        GROUP BY agency_name 
        ORDER BY COUNT(*) DESC 
        LIMIT 10
    """, conn)
    by_agency = dict(zip(agency_df['agency_name'], agency_df['count']))
    
    return {"total": total, "by_status": by_status, "by_agency": by_agency}

# ---------- UI ----------
st.set_page_config(page_title="ARCC Tracker", layout="wide")

with st.sidebar:
    st.markdown("### Research Grants Tracker")
    db_ok = _db_exists()
    grants_db_ok = _grants_db_exists()
    
    if not db_ok:
        st.caption("Main DB: demo mode (no DB found)")
    else:
        st.caption("Main DB: connected")
        
    if not grants_db_ok:
        st.caption("Grants DB: not found")
    else:
        st.caption("Grants DB: connected")

    db_mtime = _db_mtime()
    grants_db_mtime = _grants_db_mtime()
    faculty_df = list_faculty_cached(db_mtime)

    names = faculty_df["name"].tolist()
    if names:
        selected_name = st.selectbox("Enter/Select Faculty Name to start", names, index=0)
    else:
        selected_name = None
        st.warning("No faculty found. Using demo data.")

    page = st.radio("Navigate", ["Main Page", "Grants Fitness", "AI Services"], index=0)

st.title("Research Grants Tracker")

# --------- Pages ---------
if page == "Main Page":
    st.subheader("Recent Publications (PubMed)")
    pubs = fetch_publications_cached(db_mtime, selected_name or names[0] if names else "Demo PI", limit=10)
    st.dataframe(pubs, width='stretch', hide_index=True)

    st.subheader("Ongoing Projects")
    projects = fetch_projects_cached(db_mtime, selected_name or names[0] if names else "Demo PI")
    st.dataframe(projects, width='stretch', hide_index=True)

    st.info("Click a row to drill down (detail view can link to collaborators and abstracts).")

elif page == "Grants Fitness":
    st.subheader("Grants.gov Opportunities")
    
    # Show database stats
    grants_stats = get_grants_stats_cached(grants_db_mtime)
    
    if grants_stats["total"] > 0:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Opportunities", grants_stats["total"])
        with col2:
            st.metric("Posted", grants_stats["by_status"].get("posted", 0))
        with col3:
            st.metric("Forecasted", grants_stats["by_status"].get("forecasted", 0))
        
        st.divider()
    
    # Filters
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.selectbox("Filter by Status", ["All", "posted", "forecasted", "closed", "archived"])
    with col2:
        agency_filter = st.text_input("Filter by Agency", placeholder="e.g., NIH, CDC")
    
    # Date filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        open_date_from = st.date_input("Open Date From", value=None, key="open_from", help="Show opportunities opened on or after this date")
    with col2:
        open_date_to = st.date_input("Open Date To", value=None, key="open_to", help="Show opportunities opened on or before this date")
    with col3:
        close_date_from = st.date_input("Close Date From", value=None, key="close_from", help="Show opportunities closing on or after this date")
    with col4:
        close_date_to = st.date_input("Close Date To", value=None, key="close_to", help="Show opportunities closing on or before this date")
    
    # Apply filters
    status_val = None if status_filter == "All" else status_filter
    agency_val = None if not agency_filter else agency_filter
    open_date_from_val = open_date_from.strftime('%Y-%m-%d') if open_date_from else None
    open_date_to_val = open_date_to.strftime('%Y-%m-%d') if open_date_to else None
    close_date_from_val = close_date_from.strftime('%Y-%m-%d') if close_date_from else None
    close_date_to_val = close_date_to.strftime('%Y-%m-%d') if close_date_to else None
    
    # Get total count with all filters applied
    total_count = get_grants_filtered_count_cached(grants_db_mtime, status_val, agency_val, open_date_from_val, open_date_to_val, close_date_from_val, close_date_to_val)
    
    # Fixed 15 results per page (Amazon-style)
    limit = 15
    
    # Reset pagination when filters change
    filter_key = f"{status_val}_{agency_val}_{open_date_from_val}_{open_date_to_val}_{close_date_from_val}_{close_date_to_val}"
    if 'last_filter_key' not in st.session_state or st.session_state.last_filter_key != filter_key:
        st.session_state.current_page = 1
        st.session_state.last_filter_key = filter_key
    
    # Initialize pagination variables
    page = 1
    offset = 0
    
    # Pagination with Amazon-style navigation
    if total_count > 0:
        total_pages = (total_count + limit - 1) // limit  # Ceiling division
        
        # Initialize session state for current page
        if 'current_page' not in st.session_state:
            st.session_state.current_page = 1
        
        # Ensure current page is within valid range
        if st.session_state.current_page > total_pages or st.session_state.current_page < 1:
            st.session_state.current_page = 1
        
        # Amazon-style pagination controls
        if total_pages > 1:
            col1, col2, col3, col4 = st.columns([1, 1, 3, 3])

            with col1:
                # Page number input
                page_input = st.number_input(
                    "Page", 
                    min_value=1, 
                    max_value=total_pages, 
                    value=st.session_state.current_page,
                    key="page_input",
                    label_visibility="collapsed"
                )
                if page_input != st.session_state.current_page:
                    st.session_state.current_page = page_input
                    st.rerun()
            
            with col2:
                st.write(f"**Page {st.session_state.current_page} of {total_pages}**")
                
        
        # Calculate offset and display info
        page = st.session_state.current_page
        offset = (page - 1) * limit
        start_result = offset + 1
        end_result = min(offset + limit, total_count)
        
        st.write(f"**Showing {start_result}-{end_result} of {total_count} results**")
    else:
        st.write("**No results found** with current filters")
    
    # Fetch and display opportunities
    opportunities = fetch_grants_opportunities_cached(grants_db_mtime, status_val, agency_val, open_date_from_val, open_date_to_val, close_date_from_val, close_date_to_val, limit, offset)
    
    if not opportunities.empty:
        # Display opportunities in a more readable format
        for idx, row in opportunities.iterrows():
            with st.expander(f"{row['opportunity_number']}: {row['title'][:80]}..."):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.write(f"**Agency:** {row['agency_name']}")
                    st.write(f"**Status:** {row['opp_status']}")
                    # Handle date values safely - convert to scalar if needed
                    try:
                        open_date_val = row['open_date']
                        if hasattr(open_date_val, 'iloc'):
                            open_date_val = open_date_val.iloc[0] if len(open_date_val) > 0 else None
                        open_date = open_date_val if pd.notna(open_date_val) and str(open_date_val).strip() != '' else "N/A"
                    except:
                        open_date = "N/A"
                    st.write(f"**Open Date:** {open_date}")
                    
                    try:
                        close_date_val = row['close_date']
                        if hasattr(close_date_val, 'iloc'):
                            close_date_val = close_date_val.iloc[0] if len(close_date_val) > 0 else None
                        close_date = close_date_val if pd.notna(close_date_val) and str(close_date_val).strip() != '' else "N/A"
                    except:
                        close_date = "N/A"
                    st.write(f"**Deadline:** {close_date}")
                    if pd.notna(row['award_ceiling']) and row['award_ceiling'] not in ['none', 'None', '']:
                        try:
                            ceiling = int(row['award_ceiling'])
                            st.write(f"**Award Ceiling:** ${ceiling:,}")
                        except (ValueError, TypeError):
                            st.write(f"**Award Ceiling:** {row['award_ceiling']}")
                    if pd.notna(row['award_floor']) and row['award_floor'] not in ['none', 'None', '']:
                        try:
                            floor = int(row['award_floor'])
                            st.write(f"**Award Floor:** ${floor:,}")
                        except (ValueError, TypeError):
                            st.write(f"**Award Floor:** {row['award_floor']}")
                
                with col2:
                    if pd.notna(row['agency_contact_name']):
                        st.write(f"**Contact:** {row['agency_contact_name']}")
                    if pd.notna(row['agency_contact_email']):
                        st.write(f"**Email:** {row['agency_contact_email']}")
                    if pd.notna(row['funding_desc_link']) and row['funding_desc_link'].strip() and not row['funding_desc_link'].startswith('http://localhost') and 'dashboard' not in row['funding_desc_link'].lower():
                        st.link_button("View Full Announcement", row['funding_desc_link'])
                
                # Description
                if pd.notna(row['description']) and row['description']:
                    st.write("**Description:**")
                    # Truncate long descriptions
                    desc = row['description']
                    if len(desc) > 500:
                        desc = desc[:500] + "..."
                    st.write(desc)
    else:
        st.info("No opportunities found. Try adjusting your filters or load some grants data first.")
        st.code("""
# To load grants data, run:
python etl/grantsgov.py \\
  --keyword "health research" \\
  --statuses "posted|forecasted" \\
  --rows 20 \\
  --details \\
  --load-db
        """)
    
    st.divider()
    st.subheader("Actions")
    col1, col2 = st.columns(2)
    with col1:
        if not opportunities.empty:
            csv = opportunities.to_csv(index=False).encode("utf-8")
            st.download_button("Export Opportunities to CSV", data=csv, file_name="grants_opportunities.csv", mime="text/csv")
    with col2:
        st.button("Refresh Data", help="Reload opportunities from database") # TODO: add a function to fetch new opportunities from grants.gov

elif page == "AI Services":
    st.subheader("AI Summaries & Q&A (MVP)")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Project Summary (cached)**")
        st.text_area("Summary", "Auto-generated 100-word summary will appear here.", height=180)
        st.write("Suggested mechanisms: R01, R21, K23")
    with col2:
        st.markdown("**Ask a question about your registry**")
        question = st.text_input("e.g., Projects about AAA with UT co-authors")
        if st.button("Ask"):
            st.success("MVP stub: wire to RAG/SQL. (Return an answer with citations to PMIDs and core_project_nums.)")

st.write("")
st.caption("Streamlit App Demo")
