"""
Harvest recent PubMed publications by faculty list (CSV)
- Exact author matching via "Full Author Name"
- Optional affiliation scoping (e.g., Yale[Affiliation])
- Cap retmax results (default 10 most recent)
- Outputs consolidated JSON
- Optional: persist to SQLite (people, projects, pubs, and junctions)

Examples
1) JSON only
python pubmed.py \
  --csv ../data/raw_data/faculty.csv \
  --affiliation "Yale" \
  --num-papers 5 \
  -o ../data/sample_data/pubmed_faculty_recent.json

2) Persist to DB
python pubmed.py \
  --csv ../data/raw_data/faculty.csv \
  --affiliation "Yale" \
  --num-papers 5 \
  --db ../tracker.db \
  --persist
"""

import argparse
import csv
import datetime as dt
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests
import xml.dom.minidom as minidom
from dotenv import load_dotenv
from tqdm import tqdm

# self-defined helpers
from db_helper import (
    connect_db,
    upsert_person,
    ensure_auto_project_for_faculty,
    upsert_pub_and_link,
)

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Load env for NCBI credentials
load_dotenv("../config/.env")
NCBI_API_KEY = os.getenv("NCBI_API_KEY")
NCBI_EMAIL = os.getenv("NCBI_EMAIL")

# ---------- PubMed helpers ----------

def _params(base: Dict[str, Any]) -> Dict[str, Any]:
    if NCBI_API_KEY:
        base["api_key"] = NCBI_API_KEY
    if NCBI_EMAIL:
        base["email"] = NCBI_EMAIL
    return base


def esearch_pmids(query: str, retmax: int = 10) -> List[str]:
    """ESearch with publication-date sort; returns PMIDs (most recent first)."""
    params = _params(
        {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": retmax,
            "sort": "pub+date",
        }
    )
    r = requests.get(f"{EUTILS}/esearch.fcgi", params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("esearchresult", {}).get("idlist", [])


def _text(node_list):
    return (
        node_list[0].firstChild.nodeValue.strip()
        if node_list and node_list[0].firstChild
        else ""
    )


def _authors(article_node) -> List[Dict[str, Any]]:
    out = []
    for a in article_node.getElementsByTagName("Author"):
        last = _text(a.getElementsByTagName("LastName"))
        fore = _text(a.getElementsByTagName("ForeName"))
        init = _text(a.getElementsByTagName("Initials"))
        affn = a.getElementsByTagName("Affiliation")
        aff = _text(affn) if affn else ""
        out.append({"last": last, "fore": fore, "initials": init, "affiliation": aff})
    return out


def _abstract(article_node) -> str:
    abs_nodes = article_node.getElementsByTagName("Abstract")
    if not abs_nodes:
        return ""
    parts = []
    for t in abs_nodes[0].getElementsByTagName("AbstractText"):
        label = t.getAttribute("Label")
        txt = "".join(n.data for n in t.childNodes if n.nodeType == n.TEXT_NODE).strip()
        parts.append(f"{label}: {txt}" if label else txt)
    return "\n".join([p for p in parts if p])


def _keywords(medline_node) -> List[str]:
    kws = []
    for kw in medline_node.getElementsByTagName("Keyword"):
        val = "".join(n.data for n in kw.childNodes if n.nodeType == n.TEXT_NODE).strip()
        if val:
            kws.append(val)
    for mh in medline_node.getElementsByTagName("MeshHeading"):
        desc = mh.getElementsByTagName("DescriptorName")
        if desc:
            val = _text(desc)
            if val:
                kws.append(val)
    # de-dup preserve order
    seen, out = set(), []
    for k in kws:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _grants(medline_node) -> List[Dict[str, str]]:
    out = []
    gl = medline_node.getElementsByTagName("GrantList")
    if not gl:
        return out
    for g in gl[0].getElementsByTagName("Grant"):
        grant_id = _text(g.getElementsByTagName("GrantID"))
        agency = _text(g.getElementsByTagName("Agency"))
        acronym = _text(g.getElementsByTagName("Acronym"))
        country = _text(g.getElementsByTagName("Country"))
        if grant_id or agency or acronym:
            out.append(
                {
                    "agency": agency or "",
                    "acronym": acronym or "",
                    "grant_id": grant_id or "",
                    "country": country or "",
                }
            )
    return out


def efetch_details(pmids: List[str]) -> List[Dict[str, Any]]:
    """EFetch XML → structured dicts."""
    results = []
    if not pmids:
        return results
    for i in range(0, len(pmids), 200):
        batch = pmids[i : i + 200]
        params = _params({"db": "pubmed", "retmode": "xml", "id": ",".join(batch)})
        r = requests.get(f"{EUTILS}/efetch.fcgi", params=params, timeout=60)
        r.raise_for_status()
        doc = minidom.parseString(r.text)
        for pma in doc.getElementsByTagName("PubmedArticle"):
            medline = pma.getElementsByTagName("MedlineCitation")[0]
            art = medline.getElementsByTagName("Article")[0]

            pmid = _text(medline.getElementsByTagName("PMID"))
            title = _text(art.getElementsByTagName("ArticleTitle"))

            jtitle = ""
            jnode = art.getElementsByTagName("Journal")
            if jnode:
                jtitle = _text(jnode[0].getElementsByTagName("Title")) or _text(
                    jnode[0].getElementsByTagName("ISOAbbreviation")
                )

            # year
            year = None
            if jnode:
                ji = jnode[0].getElementsByTagName("JournalIssue")
                if ji:
                    pd = ji[0].getElementsByTagName("PubDate")
                    if pd:
                        y_candidate = _text(pd[0].getElementsByTagName("Year")) or _text(
                            pd[0].getElementsByTagName("MedlineDate")
                        )
                        y4 = y_candidate[:4] if y_candidate else None
                        year = int(y4) if y4 and y4.isdigit() else None

            authors = _authors(art)
            abstr = _abstract(art)
            kw = _keywords(medline)
            grants = _grants(medline)

            results.append(
                {
                    "pmid": pmid,
                    "title": title,
                    "journal": jtitle,
                    "year": year,
                    "authors": authors,  # list (will be stringified for JSON/persist)
                    "abstract": abstr,
                    "keywords": kw,
                    "grants": grants,
                }
            )
        time.sleep(0.34)
    return results


# ---------- Name utils ----------

def normalize_name(full_name: str) -> Dict[str, str]:
    s = re.sub(r"\s+", " ", full_name.strip())
    parts = s.split(" ")
    first = parts[0]
    last = parts[-1]
    middle = " ".join(parts[1:-1]) if len(parts) > 2 else ""
    return {"first": first, "middle": middle, "last": last, "full": s}


def build_author_query(full_name: str, affiliation: Optional[str]) -> str:
    q_name = f"{full_name}[Full Author Name]"
    if affiliation:
        q_name += f" AND {affiliation}[Affiliation]"
    return q_name


# ---------- CLI ----------

def parse_args():
    ap = argparse.ArgumentParser(
        description="Harvest recent PubMed publications per faculty list."
    )
    ap.add_argument(
        "--csv",
        required=True,
        help="Faculty CSV (must include 'full_name'; optional 'affiliation').",
    )
    ap.add_argument(
        "--affiliation",
        default="",
        help="Default affiliation filter if CSV lacks it (e.g., 'Yale').",
    )
    ap.add_argument(
        "--num-papers", type=int, default=10, help="Max recent papers per faculty."
    )
    ap.add_argument("-o", "--out", help="Output JSON filepath.")
    ap.add_argument("--db", default="", help="SQLite DB path (e.g., db/tracker.db).")
    ap.add_argument(
        "--persist",
        action="store_true",
        help="Write into SQLite (people/projects/pubs + relations).",
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=0.34,
        help="Seconds to sleep between authors (NCBI-friendly).",
    )
    return ap.parse_args()


# ---------- Main ----------

def main():
    args = parse_args()

    # Read faculty
    faculty_rows = []
    with open(args.csv, newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            if row.get("full_name"):
                faculty_rows.append(row)

    cxn = None
    if args.persist:
        if not args.db:
            raise SystemExit("ERROR: --persist requires --db path to SQLite database.")
        cxn = connect_db(args.db)

    out_blocks = []

    for row in tqdm(faculty_rows, desc="Faculty"):
        full_name = row["full_name"].strip()
        affiliation = (row.get("affiliation") or args.affiliation or "").strip() or None
        norm = normalize_name(full_name)
        query = build_author_query(full_name, affiliation)

        try:
            pmids = esearch_pmids(query, retmax=args.num_papers)
        except requests.HTTPError as e:
            print(f"[WARN] ESearch failed for {full_name}: {e}")
            pmids = []
        records = efetch_details(pmids)

        # prepare JSON (stringify authors)
        for rec in records:
            rec["authors_json"] = json.dumps(rec.get("authors", []), ensure_ascii=False)

        # persist (optional)
        if args.persist and cxn:
            try:
                person_id = upsert_person(cxn, norm, role="PI", affiliation=affiliation)
                # Skip creating "Auto:" placeholder projects - just store publications
                # Publications will be linked to authors via author_pub_relation
                for rec in records:
                    upsert_pub_and_link(cxn, rec, project_id=None)
                cxn.commit()
            except Exception as e:
                cxn.rollback()
                print(f"[ERROR] persist failed for {full_name}: {e}")

        out_blocks.append(
            {
                "faculty_full_name": full_name,
                "affiliation": affiliation,
                "query": query,
                "count": len(records),
                "records": records,
            }
        )

        time.sleep(args.sleep)

    payload = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "ncbi_email_present": bool(NCBI_EMAIL),
        "ncbi_api_key_present": bool(NCBI_API_KEY),
        "num_papers": args.num_papers,
        "affiliation": args.affiliation or None,
        "faculty_count": len(out_blocks),
        "data": out_blocks,
    }

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print(f"Saved PubMed harvest to {args.out}")
    if args.persist:
        print(f"Persisted to SQLite: {args.db}")


if __name__ == "__main__":
    main()
