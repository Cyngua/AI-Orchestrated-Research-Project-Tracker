'''
Harvest recent PubMed publications by faculty list (CSV)
- Exact author matching via "Full Author Name"
- Optional affiliation scoping (e.g., Yale[Affiliation])
- Cap retmax results (default 10 most recent)
- Outputs a consolidated JSON

Sample Usage
python pubmed.py \
  --csv ../data/raw_data/faculty.csv \
  --affiliation-hint "Yale" \
  --retmax 10 \
  -o ../data/sample_data/pubmed_faculty_recent.json
'''

import argparse, csv, json, os, time, re, datetime as dt
from typing import List, Dict, Any, Optional
import requests
from dotenv import load_dotenv
import xml.dom.minidom as minidom
from tqdm import tqdm

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

load_dotenv()
NCBI_API_KEY = os.getenv("NCBI_API_KEY")
NCBI_EMAIL = os.getenv("NCBI_EMAIL")

# ---------- Helpers ----------

def _params(base: Dict[str, Any]) -> Dict[str, Any]:
    if NCBI_API_KEY: base["api_key"] = NCBI_API_KEY
    if NCBI_EMAIL: base["email"] = NCBI_EMAIL
    return base

def esearch_pmids(query: str, retmax: int = 10) -> List[str]:
    """ESearch with pub date sort; returns PMIDs (most recent first)."""
    params = _params({
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": retmax,
        "sort": "pub_date"
    })
    r = requests.get(f"{EUTILS}/esearch.fcgi", params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("esearchresult", {}).get("idlist", [])

def _text(node_list):
    return node_list[0].firstChild.nodeValue.strip() if node_list and node_list[0].firstChild else ""

def _authors(article_node) -> List[Dict[str, Any]]:
    out = []
    for a in article_node.getElementsByTagName("Author"):
        last = _text(a.getElementsByTagName("LastName"))
        fore = _text(a.getElementsByTagName("ForeName"))
        init = _text(a.getElementsByTagName("Initials"))
        affn = a.getElementsByTagName("Affiliation")
        aff  = _text(affn) if affn else ""
        # Corresponding author often has <AffiliationInfo><Affiliation>... ElectronicAddress ...</>
        # PubMed doesn't flag corresponding author uniformly; we'll infer by presence of <Author><Identifier ...> rarely present.
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
        if val: kws.append(val)
    for mh in medline_node.getElementsByTagName("MeshHeading"):
        desc = mh.getElementsByTagName("DescriptorName")
        if desc:
            val = _text(desc)
            if val: kws.append(val)
    # de-dup preserve order
    seen, out = set(), []
    for k in kws:
        if k not in seen:
            seen.add(k); out.append(k)
    return out

def _grants(medline_node) -> List[Dict[str, str]]:
    out = []
    gl = medline_node.getElementsByTagName("GrantList")
    if not gl:
        return out
    for g in gl[0].getElementsByTagName("Grant"):
        grant_id = _text(g.getElementsByTagName("GrantID"))
        agency   = _text(g.getElementsByTagName("Agency"))
        acronym  = _text(g.getElementsByTagName("Acronym"))
        country  = _text(g.getElementsByTagName("Country"))
        if grant_id or agency or acronym:
            out.append({
                "agency": agency or "",
                "acronym": acronym or "",
                "grant_id": grant_id or "",
                "country": country or ""
            })
    return out

def efetch_details(pmids: List[str]) -> List[Dict[str, Any]]:
    """EFetch XML: structured dicts (title, journal, year, authors_json, abstract, keywords, grants)."""
    results = []
    if not pmids:
        return results
    for i in range(0, len(pmids), 200):
        batch = pmids[i:i+200]
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
                jtitle = _text(jnode[0].getElementsByTagName("Title")) or \
                         _text(jnode[0].getElementsByTagName("ISOAbbreviation"))

            # year
            year = None
            if jnode:
                ji = jnode[0].getElementsByTagName("JournalIssue")
                if ji:
                    pd = ji[0].getElementsByTagName("PubDate")
                    if pd:
                        y_candidate = _text(pd[0].getElementsByTagName("Year")) or _text(pd[0].getElementsByTagName("MedlineDate"))
                        y4 = y_candidate[:4] if y_candidate else None
                        year = int(y4) if y4 and y4.isdigit() else None

            authors = _authors(art)
            abstr = _abstract(art)
            kw = _keywords(medline)
            grants = _grants(medline)

            results.append({
                "pmid": pmid,
                "title": title,
                "journal": jtitle,
                "year": year,
                "authors": authors,
                "abstract": abstr,
                "keywords": kw,
                "grants": grants
            })
        time.sleep(0.34)
    return results

# ---------- Matching logic ----------

def normalize_name(full_name: str) -> Dict[str, str]:
    s = re.sub(r"\s+", " ", full_name.strip())
    parts = s.split(" ")
    first = parts[0]
    last = parts[-1]
    middle = " ".join(parts[1:-1]) if len(parts) > 2 else ""
    initials = "".join(x[0] for x in (first, *middle.split(), last) if x)
    return {"first": first, "middle": middle, "last": last, "initials": initials, "full": s}

def author_position_and_conf(authors: List[Dict[str, Any]], faculty_norm: Dict[str, str], affiliation_hint: Optional[str]) -> Dict[str, Any]:
    """Find if/where the faculty appears among authors; compute match confidence and affiliation match."""
    full = faculty_norm["full"].lower()
    last = faculty_norm["last"].lower()
    first = faculty_norm["first"].lower()
    initials = faculty_norm["initials"].lower()

    pos = None
    aff_match = False
    conf = "low"

    # Scan authors list
    for idx, a in enumerate(authors):
        a_last = (a.get("last") or "").lower()
        a_fore = (a.get("fore") or "").lower()
        a_init = (a.get("initials") or "").lower()
        a_full  = f"{a_fore} {a_last}".strip()

        name_hit = (a_last == last and (a_fore.startswith(first) or first in a_fore)) or (a_last == last and a_init.startswith(first[:1]))
        # Additional robust check for compound names
        name_hit = name_hit or (full == f"{a_fore} {a_last}".strip())

        if name_hit:
            pos = "first" if idx == 0 else ("last" if idx == len(authors) - 1 else "other")
            # affiliation hint
            if affiliation_hint:
                aff = (a.get("affiliation") or "").lower()
                if aff and affiliation_hint.lower() in aff:
                    aff_match = True
            # confidence
            if a_last == last and a_fore.startswith(first):
                conf = "high"
            elif a_last == last and a_init.startswith(first[:1]):
                conf = "medium"
            else:
                conf = "low"
            break

    return {"author_position": pos, "author_match_confidence": conf, "affiliation_match": aff_match}

# ---------- Query builder ----------

def build_author_query(full_name: str, affiliation: Optional[str], years_back: int, retmax: int) -> str:
    """
    Favor Full Author Name, optionally AND affiliation.
    Constrain by recent years using reldate if years_back > 0.
    """
    q_name = f"{full_name}[Full Author Name]"
    if affiliation:
        q_name += f" AND {affiliation}[Affiliation]"
    if years_back and years_back > 0:
        days = years_back * 365
        # TODO: IF we want a year cutoff, add: AND ({dt.date.today().year - years_back}:{dt.date.today().year}[dp])
    return q_name

# ---------- CLI + main ----------

def parse_args():
    ap = argparse.ArgumentParser(description="Harvest recent PubMed publications per faculty list.")
    ap.add_argument("--csv", required=True, help="Path to faculty CSV (must include at least 'full_name' column).")
    ap.add_argument("--affiliation-hint", default="", help="Optional affiliation filter (e.g., 'Yale').")
    ap.add_argument("--years-back", type=int, default=0, help="Limit search to last N years (0 = no hard limit; we still sort by pub date).")
    ap.add_argument("--retmax", type=int, default=10, help="Max number of most recent papers per faculty.")
    ap.add_argument("-o", "--out", required=True, help="Output JSON file.")
    ap.add_argument("--sleep", type=float, default=0.34, help="Seconds to sleep between authors (NCBI policy-friendly).")
    return ap.parse_args()

def main():
    args = parse_args()

    # Read faculty
    faculty_rows = []
    with open(args.csv, newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            if not row.get("full_name"):
                continue
            faculty_rows.append(row)

    out_blocks = []
    for row in tqdm(faculty_rows):
        full_name = row["full_name"].strip()
        affiliation = row.get("affiliation", "").strip() or args.affiliation_hint.strip() or ""
        norm = normalize_name(full_name)
        query = build_author_query(full_name, affiliation if affiliation else None, args.years_back, args.retmax
                                   )
        # Search
        try:
            pmids = esearch_pmids(query, retmax=args.retmax)
        except requests.HTTPError as e:
            print(f"[WARN] ESearch failed for {full_name}: {e}")
            pmids = []

        # Fetch details
        records = efetch_details(pmids)
        # post-process: add matching diagnostics
        for rec in records:
            diag = author_position_and_conf(rec.get("authors", []), norm, affiliation if affiliation else None)
            rec.update(diag)
            # stringify authors for final JSON cleanliness
            rec["authors_json"] = json.dumps(rec.pop("authors", []), ensure_ascii=False)

        out_blocks.append({
            "faculty_full_name": full_name,
            "affiliation_hint": affiliation or None,
            "query": query,
            "count": len(records),
            "records": records
        })

        time.sleep(args.sleep)

    # Save JSON
    payload = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "ncbi_email_present": bool(NCBI_EMAIL),
        "ncbi_api_key_present": bool(NCBI_API_KEY),
        "return_max": args.retmax,
        "years_back": args.years_back,
        "affiliation_hint": args.affiliation_hint or None,
        "faculty_count": len(out_blocks),
        "data": out_blocks
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Saved PubMed data to: {args.out}")
    print(f"Faculty processed: {len(out_blocks)}")

if __name__ == "__main__":
    main()
