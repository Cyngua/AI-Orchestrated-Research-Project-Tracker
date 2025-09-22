'''
Stub for NIH ETL
'''

import re, requests

REPORTER = "https://api.reporter.nih.gov/v2/projects/search"
ACTIVITY = {"R01","R21","R03","U01","U54","P50","K08","K23","T32","F32","R25","R61","R33"}

def to_core_project_num(grant_id: str) -> str | None:
    if not grant_id: return None
    s = grant_id.upper().replace(" ", "")
    s = s.split("-")[0]  # drop -01, -01A1, etc.
    # Find an activity code + IC + 6-digit serial, e.g. R01HL123456
    m = re.search(r'\b([A-Z]\d{2}|[A-Z]{1,2}\d{2})[A-Z]{2}\d{6}\b', s)
    if not m:
        # simpler heuristic: try common activities explicitly
        for a in sorted(ACTIVITY, key=len, reverse=True):
            idx = s.find(a)
            if idx != -1 and len(s) >= idx+len(a)+2+6:
                cand = s[idx:idx+len(a)+2+6]
                if cand[len(a):len(a)+2].isalpha() and s[idx+len(a)+2:idx+len(a)+8].isdigit():
                    return cand
        return None
    return m.group(0)

def fetch_reporter_by_core(core_nums: list[str], limit=50):
    payload = {
        "criteria": {"core_project_nums": core_nums},
        "include_fields": [
            "ProjectNum","CoreProjectNum","ProjectTitle","PrincipalInvestigators",
            "Organization","AwardAmount","FundingICs","AbstractText",
            "FiscalYear","ProjectStartDate","ProjectEndDate"
        ],
        "offset": 0, "limit": limit
    }
    r = requests.post(REPORTER, json=payload, timeout=60)
    r.raise_for_status()
    return r.json().get("results", [])

# Example: map PubMed grants → RePORTER rows
def lookup_from_pubmed_grants(pubmed_grants: list[dict]):
    # pubmed_grants like [{"agency":"NIH","grant_id":"R01HL123456-01A1"}, ...]
    cores = []
    for g in pubmed_grants:
        if g.get("agency","").upper() != "NIH": 
            continue
        core = to_core_project_num(g.get("grant_id",""))
        if core: cores.append(core)
    cores = sorted(set(cores))
    if not cores: return []
    return fetch_reporter_by_core(cores)


