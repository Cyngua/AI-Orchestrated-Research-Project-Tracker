# streamlit run streamlit_app.py
import os
import sqlite3
import pandas as pd
import streamlit as st

DB_PATH = "../tracker.db"

# ---------- Data access ----------
@st.cache_data(show_spinner=False)
def get_conn():
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@st.cache_data(show_spinner=False)
def list_faculty(conn):
    if conn:
        q = """
        SELECT p.id, COALESCE(p.first_name,'') || ' ' || COALESCE(p.last_name,'') AS name
        FROM people p
        ORDER BY p.last_name, p.first_name
        """
        return pd.read_sql(q, conn)
    # demo fallback
    return pd.DataFrame({"id":[1,2,3], "name":["Isibor Arhuidese","Alan Dardik","Julie Ann Freischlag"]})

@st.cache_data(show_spinner=False)
def fetch_publications(conn, faculty_name, limit=10):
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
        return pd.read_sql(q, conn, params=[faculty_name, limit])
    # demo fallback
    data = [
        {"pmid":"38800123","title":"Endovascular AAA outcomes","journal":"J Vasc Surg","year":2024},
        {"pmid":"38799011","title":"PAD imaging advances","journal":"Circulation","year":2023},
    ]
    return pd.DataFrame(data)[:limit]

@st.cache_data(show_spinner=False)
def fetch_projects(conn, faculty_name):
    if conn:
        q = """
        SELECT pr.id as project_id, pr.title, pr.stage, pr.start_date, pr.end_date
        FROM projects pr
        LEFT JOIN people_project_relation ppr ON ppr.project_id = pr.id
        LEFT JOIN people pe ON pe.id = ppr.person_id
        WHERE pe.first_name || ' ' || pe.last_name = ?
        ORDER BY pr.updated_at DESC
        """
        return pd.read_sql(q, conn, params=[faculty_name])
    # demo fallback
    return pd.DataFrame([
        {"project_id":101,"title":"AAA biomechanics pilot","stage":"analysis","start_date":"2024-01-01","end_date":None},
        {"project_id":102,"title":"PAD registry build","stage":"planning","start_date":"2024-09-01","end_date":None},
    ])

@st.cache_data(show_spinner=False)
def fetch_grant_fits(conn, faculty_name):
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
        return pd.read_sql(q, conn, params=[faculty_name])
    # demo fallback
    return pd.DataFrame([
        {"core_project_num":"R01HL123456","mechanism":"R01","role":"inferred","confidence":0.82,"notes":"AAA keywords overlap","score":0.82},
        {"core_project_num":"R21HL987654","mechanism":"R21","role":"inferred","confidence":0.71,"notes":"embolization study","score":0.71},
    ])

# ---------- UI ----------
st.set_page_config(page_title="ARCC Tracker", layout="wide")

with st.sidebar:
    # st.markdown("### Research Grants Tracker")
    # conn = get_conn() # TODO: feed data
    conn = None # for demo purpose
    faculty_df = list_faculty(conn)
    names = faculty_df["name"].tolist()
    selected_name = st.selectbox("Enter/Select Faculty Name to start", names, index=0 if names else None)
    page = st.radio("Navigate", ["Main Page", "Grants Fitness", "AI Services"], index=0)
    # st.caption("DB: " + (DB_PATH if os.path.exists(DB_PATH) else "demo mode (no DB found)"))

st.title("Research Grants Tracker")

# --------- Pages ---------
if page == "Main Page":
    st.subheader("Recent Publications (PubMed)")
    pubs = fetch_publications(conn, selected_name, limit=10)
    st.dataframe(pubs, use_container_width=True, hide_index=True)

    st.subheader("Ongoing Projects")
    projects = fetch_projects(conn, selected_name)
    st.dataframe(projects, use_container_width=True, hide_index=True)

    st.info("Click a row to drill down (detail view can link to collaborators and abstracts).")

elif page == "Grants Fitness":
    st.subheader("Recommended NIH Opportunities / Grant Matches")
    fits = fetch_grant_fits(conn, selected_name)
    st.dataframe(fits, use_container_width=True, hide_index=True)
    st.caption("Scores are placeholders; wire to your fit-score service.")

    st.divider()
    st.subheader("Actions")
    col1, col2 = st.columns(2)
    with col1:
        st.button("Mark selected as Primary Support", help="Promote an inferred match to manual.")
    with col2:
        st.button("Export top matches to CSV")

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

    # st.caption("Once your vector index is ready, plug in a RAG function here.")

# ---------- Footer ----------
st.write("")
st.caption("Streamlit App Demo")
