'''
Stub for PubMed ETL: fetch detailed metadata for published biomedical papers
python pubmed.py --topic "abdominal aortic aneurysm" --year 2024 --retmax 50 --out ../data/sample_data/aaa_2024.json
python pubmed.py --topic "peripheral arterial disease" --year 2023 --out ../data/sample_data/pad_2023.json
python pubmed.py --topic "carotid artery stenosis" --year 2024 --out ../data/sample_data/cas_2024.json
'''

import os
import time, requests
import json
import argparse
import xml.dom.minidom as minidom
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

NCBI_API_KEY = os.getenv("NCBI_API_KEY")
NCBI_EMAIL = os.getenv("NCBI_EMAIL")

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

def esearch_pmids(topic: str, year: int, retmax: int = 50):
    """Return a list of PMIDs for topic/year using ESearch (JSON)."""
    params = {
        "db": "pubmed",
        "term": f"{topic} AND {year}[pdat]",
        "datetype": "pdat",
        "retmode": "json",
        "retmax": retmax,
    }
    if NCBI_API_KEY: params["api_key"] = NCBI_API_KEY
    if NCBI_EMAIL:   params["email"] = NCBI_EMAIL
    r = requests.get(f"{EUTILS}/esearch.fcgi", params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("esearchresult", {}).get("idlist", [])

def _text(nodes):
    return nodes[0].firstChild.nodeValue.strip() if nodes and nodes[0].firstChild else ""

def _year_from_pubdate(pubdate):
    y = pubdate[:4] if pubdate else None
    return int(y) if y and y.isdigit() else None

def _authors(article_node):
    out = []
    for a in article_node.getElementsByTagName("Author"):
        last = _text(a.getElementsByTagName("LastName"))
        fore = _text(a.getElementsByTagName("ForeName"))
        init = _text(a.getElementsByTagName("Initials"))
        affn = a.getElementsByTagName("Affiliation")
        aff = _text(affn) if affn else ""
        if last or fore:
            out.append({"last": last, "fore": fore, "initials": init, "affiliation": aff})
    return out

def _abstract(article_node):
    abs_nodes = article_node.getElementsByTagName("Abstract")
    if not abs_nodes:
        return ""
    parts = []
    for t in abs_nodes[0].getElementsByTagName("AbstractText"):
        label = t.getAttribute("Label")
        txt = "".join(n.data for n in t.childNodes if n.nodeType == n.TEXT_NODE).strip()
        parts.append(f"{label}: {txt}" if label else txt)
    return "\n".join([p for p in parts if p])

def _keywords(medline_node):
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

def _grants(medline_node):
    """Parse GrantList with agency, acronym, grant_id, country"""
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
            out.append({
                "agency": agency or "",
                "acronym": acronym or "",
                "grant_id": grant_id or "",
                "country": country or ""
            })
    return out

def efetch_details(pmids, sleep_between=0.34):
    """Return list of dicts with pmid, title, journal, year, authors_json, plus abstract & keywords."""
    results = []
    if not pmids:
        return results

    for i in range(0, len(pmids), 200):
        batch = pmids[i:i+200]
        params = {"db": "pubmed", "retmode": "xml", "id": ",".join(batch)}
        if NCBI_API_KEY: params["api_key"] = NCBI_API_KEY
        if NCBI_EMAIL:   params["email"] = NCBI_EMAIL

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

            year = None
            if jnode:
                ji = jnode[0].getElementsByTagName("JournalIssue")
                if ji:
                    pd = ji[0].getElementsByTagName("PubDate")
                    if pd:
                        # PubDate may have Year or MedlineDate; both handled by slicing first 4 chars
                        y_candidate = _text(pd[0].getElementsByTagName("Year")) or _text(pd[0].getElementsByTagName("MedlineDate"))
                        year = _year_from_pubdate(y_candidate)

            authors = _authors(art)
            abstr = _abstract(art)
            kw = _keywords(medline)
            grants = _grants(medline)

            results.append({
                "pmid": pmid,
                "title": title,
                "journal": jtitle,
                "year": year,
                "authors_json": json.dumps(authors, ensure_ascii=False),
                "abstract": abstr,
                "keywords": kw,
                "grants": grants
            })
        time.sleep(sleep_between)
    return results

def save_json(records, out_path):
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

def main():
    ap = argparse.ArgumentParser(description="Harvest PubMed metadata to JSON.")
    ap.add_argument("--topic", required=True, help='e.g., "abdominal aortic aneurysm"')
    ap.add_argument("--year", type=int, required=True, help="Publication year filter")
    ap.add_argument("--retmax", type=int, default=50, help="Max PMIDs to fetch")
    ap.add_argument("--out", required=True, help="Output JSON filepath")
    args = ap.parse_args()

    pmids = esearch_pmids(args.topic, args.year, args.retmax)
    details = efetch_details(pmids)
    save_json(details, args.out)
    print(f"Saved {len(details)} records to {args.out}")

if __name__ == "__main__":
    main()
