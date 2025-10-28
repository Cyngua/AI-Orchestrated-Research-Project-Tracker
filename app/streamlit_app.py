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

    page = st.radio("Navigate", ["Main Page", "All Grants Opportunities", "PI Grant Matching", "AI Services"], index=0)

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

elif page == "All Grants Opportunities":
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

elif page == "PI Grant Matching":
    st.subheader("PI-Grant Matching System")
    
    if not selected_name:
        st.warning("Please select a faculty member from the sidebar to view matching grants.")
    else:
        st.write(f"**Matching grants for: {selected_name}**")
        
        # Matching weight controls
        st.subheader("Adjust Matching Weights")
        st.write("Customize how grants are scored based on your priorities:")
        
        # Preset weight configurations
        col_preset, col_custom = st.columns([1, 2])
        
        with col_preset:
            st.write("**Quick Presets:**")
            preset = st.selectbox(
                "Choose a configuration mode:",
                ["Custom", "Research Focus", "Timing Focus", "Experience Focus"],
                help="Select a preset weight configuration or choose Custom to adjust manually"
            )
            
            # Show current mode status
            if preset == "Custom":
                st.success("Custom mode - sliders enabled")
            else:
                st.info("Sliders disabled")
            
            # Mode descriptions
            mode_descriptions = {
                "Research Focus": "Prioritizes research topic alignment (70% semantic)",
                "Timing Focus": "Prioritizes project timing (60% time alignment)", 
                "Experience Focus": "Prioritizes grant history (50% eligibility)",
                "Custom": "Manual adjustment of all weights"
            }
            
            if preset in mode_descriptions:
                st.caption(f"💡 {mode_descriptions[preset]}")
            
            # Apply presets
            if preset == "Research Focus":
                semantic_weight, time_weight, eligibility_weight = 0.7, 0.2, 0.1
            elif preset == "Timing Focus":
                semantic_weight, time_weight, eligibility_weight = 0.3, 0.6, 0.1
            elif preset == "Experience Focus":
                semantic_weight, time_weight, eligibility_weight = 0.3, 0.2, 0.5
            else:  # Custom
                semantic_weight, time_weight, eligibility_weight = 0.5, 0.3, 0.2
        
        with col_custom:
            st.write("**Manual Adjustment:**")
            col1, col2, col3 = st.columns(3)
            
            # Determine if sliders should be disabled
            sliders_disabled = preset != "Custom"
        
        with col1:
            semantic_weight = st.slider(
                "Semantic Similarity", 
                min_value=0.0, 
                max_value=1.0, 
                value=semantic_weight, 
                step=0.1,
                disabled=sliders_disabled,
                help="How much to weight research topic/keyword alignment (0.0-1.0)" + (" (Disabled - use preset mode)" if sliders_disabled else "")
            )
        
        with col2:
            time_weight = st.slider(
                "Time Alignment", 
                min_value=0.0, 
                max_value=1.0, 
                value=time_weight, 
                step=0.1,
                disabled=sliders_disabled,
                help="How much to weight timing alignment with your active projects (0.0-1.0)" + (" (Disabled - use preset mode)" if sliders_disabled else "")
            )
        
        with col3:
            eligibility_weight = st.slider(
                "Eligibility", 
                min_value=0.0, 
                max_value=1.0, 
                value=eligibility_weight, 
                step=0.1,
                disabled=sliders_disabled,
                help="How much to weight your grant history and agency familiarity (0.0-1.0)" + (" (Disabled - use preset mode)" if sliders_disabled else "")
            )
        
        # Normalize weights to sum to 1.0
        total_weight = semantic_weight + time_weight + eligibility_weight
        if total_weight > 0:
            semantic_weight = semantic_weight / total_weight
            time_weight = time_weight / total_weight
            eligibility_weight = eligibility_weight / total_weight
        
        # Display normalized weights with visual representation
        st.divider()
        
        # Visual weight representation
        col_viz1, col_viz2, col_viz3 = st.columns(3)
        
        with col_viz1:
            st.metric("Semantic Similarity", f"{semantic_weight:.1%}", help="Research topic/keyword alignment")
            st.progress(semantic_weight)
        
        with col_viz2:
            st.metric("Time Alignment", f"{time_weight:.1%}", help="Timing with your active projects")
            st.progress(time_weight)
        
        with col_viz3:
            st.metric("Eligibility", f"{eligibility_weight:.1%}", help="Your grant history and agency familiarity")
            st.progress(eligibility_weight)
        
        # Weight summary
        st.info(f"**Current Configuration:** {preset} - Semantic: {semantic_weight:.2f}, Time: {time_weight:.2f}, Eligibility: {eligibility_weight:.2f}")
        
        # Import matching utilities
        try:
            from pi_matching_utils import (
                apply_binary_filters, 
                compute_pi_grant_match_score,
                get_pi_research_keywords
            )
            
            # Get all grants opportunities
            opportunities = fetch_grants_opportunities_cached(grants_db_mtime, None, None, None, None, None, None, 100, 0)
            
            if not opportunities.empty:
                # Apply matching to each opportunity
                matched_grants = []
                
                with st.spinner("Computing grant matches..."):
                    for idx, row in opportunities.iterrows():
                        grant_dict = row.to_dict()
                        
                        # Apply binary filters
                        if apply_binary_filters(selected_name, DB_PATH, grant_dict):
                            # Prepare custom weights
                            custom_weights = {
                                'semantic': semantic_weight,
                                'time': time_weight,
                                'eligibility': eligibility_weight
                            }
                            
                            # Compute detailed match score with custom weights
                            match_data = compute_pi_grant_match_score(selected_name, DB_PATH, grant_dict, custom_weights)
                            
                            # Add match data to grant info
                            grant_dict.update(match_data)
                            matched_grants.append(grant_dict)
                
                # Sort by overall score
                matched_grants.sort(key=lambda x: x['overall_score'], reverse=True)
                
                st.write(f"**Found {len(matched_grants)} matching grants**")
                
                # Display top matches with weight-aware scoring
                st.write(f"**Top {min(10, len(matched_grants))} matching grants (sorted by overall score):**")
                
                for i, grant in enumerate(matched_grants[:10], 1):
                    
                    with st.expander(f"#{i} Score: {grant['overall_score']:.3f} - {grant['opportunity_number']}: {grant['title'][:60]}..."):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**Agency:** {grant['agency_name']}")
                            st.write(f"**Status:** {grant['opp_status']}")
                            
                            # Handle date values safely
                            try:
                                open_date_val = grant['open_date']
                                if hasattr(open_date_val, 'iloc'):
                                    open_date_val = open_date_val.iloc[0] if len(open_date_val) > 0 else None
                                open_date = open_date_val if pd.notna(open_date_val) and str(open_date_val).strip() != '' else "N/A"
                            except:
                                open_date = "N/A"
                            st.write(f"**Open Date:** {open_date}")
                            
                            try:
                                close_date_val = grant['close_date']
                                if hasattr(close_date_val, 'iloc'):
                                    close_date_val = close_date_val.iloc[0] if len(close_date_val) > 0 else None
                                close_date = close_date_val if pd.notna(close_date_val) and str(close_date_val).strip() != '' else "N/A"
                            except:
                                close_date = "N/A"
                            st.write(f"**Deadline:** {close_date}")
                        
                        with col2:
                            # Match score breakdown with visual indicators
                            st.write("**Match Scores:**")
                            
                            # Overall score with color coding
                            overall_color = "green" if grant['overall_score'] > 0.7 else "orange" if grant['overall_score'] > 0.4 else "red"
                            st.markdown(f"* **Overall:** <span style='color: {overall_color}'>{grant['overall_score']:.3f}</span>", unsafe_allow_html=True)
                            st.write(f"* **Semantic:** {grant['semantic_score']:.3f}")
                            st.write(f"* **Time:** {grant['time_score']:.3f}")     
                            st.write(f"* **Eligibility:** {grant['eligibility_score']:.3f}")
                            
                            # PI keywords
                            if grant.get('pi_keywords'):
                                st.write(f"**PI Keywords:** {', '.join(grant['pi_keywords'][:5])}")
                        
                        # Description
                        if pd.notna(grant.get('description')) and grant['description']:
                            st.write("**Description:**")
                            desc = grant['description']
                            if len(desc) > 300:
                                desc = desc[:300] + "..."
                            st.write(desc)
                
                # Summary statistics
                if matched_grants:
                    st.divider()
                    st.subheader("Matching Summary")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Total Matches", len(matched_grants))
                    with col2:
                        avg_score = sum(g['overall_score'] for g in matched_grants) / len(matched_grants)
                        st.metric("Average Score", f"{avg_score:.3f}")
                    with col3:
                        high_score = len([g for g in matched_grants if g['overall_score'] > 0.7])
                        st.metric("High Matches (>0.7)", high_score)
                    with col4:
                        agencies = set(g['agency_name'] for g in matched_grants if g.get('agency_name'))
                        st.metric("Unique Agencies", len(agencies))
            else:
                st.info("No grants opportunities found. Please load some grants data first.")
        
        except ImportError as e:
            st.error(f"Error importing matching utilities: {e}")
            st.info("Please ensure pi_matching_utils.py is in the app directory.")

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
