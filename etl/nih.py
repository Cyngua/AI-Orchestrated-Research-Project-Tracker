"""
nih ETL
- Queries via POST /v2/projects/search
- Normalizes into:
    grants_core: one per core_project_num
    grants_fy:   one per fiscal_year slice (linked by grant_id)
- Example Usage:
    python nih.py \
        --terms "abdominal aortic aneurysm" \
        --fiscal-years 2024 2025 \
        --limit 200 \
        -o sample_data/nih_aaa_2024_2025.json

    # Exact cores (e.g., normalized from PubMed GrantList)
    python nih.py \
        --core-project-nums K23DK128569 R01HL123456 \
        -o sample_data/nih_by_core.json
"""

import argparse, json, sys, time, datetime as dt
from typing import Dict, List, Any
import requests
from tqdm import tqdm

API_URL = "https://api.reporter.nih.gov/v2/projects/search"

# -------------- CLI ----------------
def parse_args():
    ap = argparse.ArgumentParser(description="Fetch funded NIH project data from RePORTER and export JSON.")
    ap.add_argument("--terms", nargs="+", help='Free-text (e.g., "abdominal aortic aneurysm"). Use quotes for phrases.')
    ap.add_argument("--activity-codes", nargs="+", help="R01 R21 K23 U01 ...")
    ap.add_argument("--ics", nargs="+", help="IC codes (e.g., HL NS DK)")
    ap.add_argument("--fiscal-years", nargs="+", type=int, help="Fiscal years (e.g., 2024 2025)")
    ap.add_argument("--core-project-nums", nargs="+", help="Exact cores (e.g., K23DK128569)")
    ap.add_argument("--limit", type=int, default=500, help="Page size (max 500)")
    ap.add_argument("--max-pages", type=int, default=50, help="Safety stop for pagination")
    ap.add_argument("--sleep", type=float, default=0.25, help="Seconds to sleep between pages")
    ap.add_argument("-o", "--out", required=True, help="Output JSON filepath")
    ap.add_argument("--debug", action="store_true", help="Print meta + first 1–3 raw rows before normalization")
    return ap.parse_args()

# -------------- Query ----------------
def build_payload(args, offset: int, limit: int) -> Dict[str, Any]:
    criteria: Dict[str, Any] = {}

    # Use text_search for free text
    if args.terms:
        criteria["text_search"] = {"search_text": " ".join(args.terms)}

    if args.activity_codes:
        criteria["activity_codes"] = args.activity_codes

    if args.ics:
        # RePORTER accepts 'ic' for IC filter (e.g., HL, DK, NS)
        criteria["ic"] = args.ics

    if args.fiscal_years:
        criteria["fiscal_years"] = args.fiscal_years

    if args.core_project_nums:
        criteria["core_project_nums"] = args.core_project_nums

    # include_fields = [
    #     "project_num",
    #     "core_project_num",
    #     "project_title",
    #     "abstract_text",
    #     "principal_investigators",
    #     "organization",
    #     "funding_ics",
    #     "award_amount",
    #     "fiscal_year",
    #     "project_start_date",
    #     "project_end_date",
    #     "activity_code",
    # ]
    include_fields = [
        "ProjectNum",
        "CoreProjectNum",
        "ProjectTitle",
        "AbstractText",
        "PrincipalInvestigators",
        "Organization",
        "Agency", # funding institude
        "AwardAmount",
        "FiscalYear",
        "ProjectStartDate",
        "ProjectEndDate",
        "ActivityCode",
    ]

    return {
        "criteria": criteria,
        "include_fields": include_fields,
        "offset": offset,
        "limit": min(max(1, limit), 500),
    }

def fetch_page(args, offset: int, limit: int) -> Dict[str, Any]:
    payload = build_payload(args, offset, limit)
    resp = requests.post(API_URL, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    if args.debug and offset == 0:
        results = data.get("results", [])
        sample = results[:3]
        print("\n=== DEBUG: raw response (first page) ===")
        print("criteria:", json.dumps(payload["criteria"], indent=2))
        print("meta:", json.dumps(data.get("meta", {}), indent=2))
        print("sample results:", json.dumps(sample, indent=2)[:4000], "...\n")

    return data

# -------------- Normalize ----------------
def infer_status(start_iso: str | None, end_iso: str | None) -> str:
    today = dt.date.today()
    try:
        if end_iso:
            end_d = dt.date.fromisoformat(end_iso[:10])
            return "completed" if end_d < today else "active"
    except Exception:
        pass
    return "unknown"

def normalize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Input rows are one-per-fiscal-year.
    Output:
      grants_core: list of core-level dicts with fields (lower_snake_case)
      grants_fy:   list of per-year dicts linked by grant_id (local numeric)
    """
    core_map: Dict[str, Dict[str, Any]] = {}  # core_project_num -> core dict
    fy_rows: List[Dict[str, Any]] = []

    for row in results:
        core = row.get("core_project_num")
        if not core:
            continue

        start = row.get("project_start_date")
        end = row.get("project_end_date")
        status = infer_status(start, end)
        mech = row.get("activity_code")
        org = (row.get("organization") or {}).get("org_name")
        pis = row.get("principal_investigators") or []
        pi_names = [pi.get("full_name") for pi in pis if isinstance(pi, dict) and pi.get("full_name")]
        ics = [fic.get("ic_code") for fic in (row.get("funding_ics") or []) if fic.get("ic_code")]

        # init or update core record
        if core not in core_map:
            core_map[core] = {
                "core_project_num": core,
                "agency": "NIH",
                "status": status,
                "mechanism": mech,
                "project_start": start,
                "project_end": end,
                "latest_title": row.get("project_title"),
                "latest_abstract": row.get("abstract_text"),
                "latest_org_name": org,
                "latest_pi_names": pi_names,
                "funding_ics": ics,
                "max_fiscal_year": row.get("fiscal_year"),
            }
        else:
            c = core_map[core]
            # span
            if start and (not c["project_start"] or start < c["project_start"]):
                c["project_start"] = start
            if end and (not c["project_end"] or end > c["project_end"]):
                c["project_end"] = end
            # latest FY snapshot
            fy = row.get("fiscal_year")
            if isinstance(fy, int) and (c["max_fiscal_year"] is None or fy >= c["max_fiscal_year"]):
                c["max_fiscal_year"] = fy
                c["latest_title"] = row.get("project_title")
                c["latest_abstract"] = row.get("abstract_text")
                c["latest_org_name"] = org
                c["latest_pi_names"] = pi_names
            if status == "active":
                c["status"] = "active"
            if not c["mechanism"] and mech:
                c["mechanism"] = mech
            c["funding_ics"] = sorted(list({*c["funding_ics"], *ics}))

        # per-year slice
        fy_rows.append({
            "core_project_num": core,                # useful before DB IDs exist
            "project_num": row.get("project_num"),
            "fiscal_year": row.get("fiscal_year"),
            "total_cost_fy": row.get("award_amount"),
            "org_name": org,
            "pi_names": pi_names,
            "title": row.get("project_title"),
            "abstract": row.get("abstract_text"),
            "funding_ics": ics,
        })

    # assign local IDs so grants_fy can reference core
    core_list = []
    id_map: Dict[str, int] = {}
    for idx, core_num in enumerate(sorted(core_map.keys()), start=1):
        rec = core_map[core_num]
        id_map[core_num] = idx
        core_list.append({
            "id": idx,
            "core_project_num": rec["core_project_num"],
            "agency": rec["agency"],
            "status": rec["status"],
            "mechanism": rec["mechanism"],
            "project_start": rec["project_start"],
            "project_end": rec["project_end"],
            "funding_ics": rec["funding_ics"],
            "latest_title": rec["latest_title"],
            "latest_abstract": rec["latest_abstract"],
            "latest_org_name": rec["latest_org_name"],
            "latest_pi_names": rec["latest_pi_names"],
        })

    fy_list = []
    for r in fy_rows:
        core_num = r["core_project_num"]
        if core_num not in id_map:
            continue
        fy_list.append({
            "grant_id": id_map[core_num],          # will map to grants_core.id later
            "project_num": r["project_num"],
            "fiscal_year": r["fiscal_year"],
            "total_cost_fy": r["total_cost_fy"],
            "org_name": r["org_name"],
            "pi_names": r["pi_names"],
            "title": r["title"],
            "abstract": r["abstract"],
            "funding_ics": r["funding_ics"],
        })

    return {"grants_core": core_list, "grants_fy": fy_list}

# -------------- Main ----------------
def main():
    args = parse_args()

    if not any([args.terms, args.activity_codes, args.ics, args.fiscal_years, args.core_project_nums]):
        print("ERROR: Provide at least one of --terms / --activity-codes / --ics / --fiscal-years / --core-project-nums", file=sys.stderr)
        sys.exit(2)

    all_results: List[dict] = []
    offset = 0
    print(f"Loading the first {args.max_pages} pages from the RePorter...")
    for _ in tqdm(range(args.max_pages)):
        # System doesn't support offset greater than 14999
        if offset > 14999:
            break
        data = fetch_page(args, offset, args.limit)
        results = data.get("results", [])
        if not results:
            break
        all_results.extend(results)
        offset += len(results)
        # stop if last page
        if len(results) < args.limit:
            break
        time.sleep(args.sleep)

    normalized = normalize(all_results)

    out = {
        "query": {
            "terms": args.terms,
            "activity_codes": args.activity_codes,
            "ics": args.ics,
            "fiscal_years": args.fiscal_years,
            "core_project_nums": args.core_project_nums,
            "retrieved": len(all_results),
            "timestamp": dt.datetime.utcnow().isoformat() + "Z",
        },
        "grants_core": normalized["grants_core"],
        "grants_fy": normalized["grants_fy"],
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Saved NIH RePORTER data to {args.out}")
    print(f"  cores: {len(out['grants_core'])}, fy_rows: {len(out['grants_fy'])}, raw_results: {len(all_results)}")

if __name__ == "__main__":
    main()
