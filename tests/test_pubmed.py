"""
Smoke test for PubMed to SQLite ETL:
1) Create SQLite schema (init.sql)
2) Run harvester to fetch recent pubs per faculty and persist to DB
3) Run sanity queries and print human-readable stats/samples

Sample Usage:
python test_pubmed.py \
  --csv ../data/raw_data/faculty.csv \
  --harvester ../etl/pubmed.py \
  --db ../tracker.db \
  --schema ../etl/schema.sql \
  --affiliation "Yale" \
  --num-papers 10 \
  --out ../data/sample_data/pubmed_faculty_recent.json
"""

import argparse
import os
import sys
import sqlite3
import subprocess
from pathlib import Path
from textwrap import indent

def sh(cmd: list[str]) -> int:
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.call(cmd)

def ensure_dir(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)

def init_db(db_path: Path, schema_path: Path):
    if not schema_path.exists():
        raise SystemExit(f"[ERROR] schema file not found: {schema_path}")
    ensure_dir(db_path)
    sql = schema_path.read_text(encoding="utf-8")
    con = sqlite3.connect(str(db_path))
    con.executescript("PRAGMA foreign_keys = ON;")
    con.executescript(sql)
    con.commit()
    con.close()
    print(f"[OK] Initialized DB schema to {db_path}")

def run_harvester(harvester: Path, csv_path: Path, db_path: Path, out_json: Path,
                  affiliation: str, per_faculty: int):
    if not harvester.exists():
        raise SystemExit(f"[ERROR] harvester not found: {harvester}")
    if not csv_path.exists():
        raise SystemExit(f"[ERROR] faculty CSV not found: {csv_path}")
    ensure_dir(out_json)
    cmd = [
        sys.executable, str(harvester),
        "--csv", str(csv_path),
        "--affiliation", affiliation,
        "--num-papers", str(per_faculty),
        "--db", str(db_path),
        "--persist",
        "-o", str(out_json),
    ]
    rc = sh(cmd)
    if rc != 0:
        raise SystemExit(f"[ERROR] harvester exited with code {rc}")
    print(f"[OK] Harvester completed. Saved JSON to {out_json}")

def sample_table(con: sqlite3.Connection, title: str, q: str, params=(), limit: int = 5):
    q_final = q.strip()
    if "limit" not in q_final.lower():
        q_final += f"\nLIMIT {limit}"
    cur = con.execute(q_final, params)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description] if cur.description else []
    print(f"\n== {title} ==")
    if not rows:
        print("(no rows)")
        return
    # pretty print simple table
    widths = [max(len(c), *(len(str(r[i])) for r in rows)) for i, c in enumerate(cols)]
    line = " | ".join(c.ljust(widths[i]) for i, c in enumerate(cols))
    print(line)
    print("-" * len(line))
    for r in rows:
        print(" | ".join(str(r[i]).ljust(widths[i]) for i in range(len(cols))))

def sanity_checks(db_path: Path):
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    # counts
    def count(table): 
        return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    people = count("people")
    projects = count("projects")
    pubs = count("pubs")
    links_pp = count("project_pub_relation")
    links_ppl = count("people_project_relation")

    print("\n================ SANITY CHECKS ================")
    print(f"people:                 {people}")
    print(f"projects:               {projects}")
    print(f"pubs:                   {pubs}")
    print(f"project_pub_relation:   {links_pp}")
    print(f"people_project_relation:{links_ppl}")

    # samples
    sample_table(con, "People (first 5)",
        "SELECT id, first_name, last_name, COALESCE(affiliation,'') AS affiliation, COALESCE(role,'') AS role FROM people ORDER BY id")
    sample_table(con, "Auto Projects (pubmed)",
        "SELECT id, title, stage, source, created_at FROM projects WHERE source='pubmed' ORDER BY id DESC")
    sample_table(con, "Recent Publications",
        "SELECT id, pmid, substr(title,1,60) AS title, journal, year FROM pubs ORDER BY id DESC")
    sample_table(con, "Project Pub links",
        """SELECT ppr.project_id, pr.title AS project_title, pb.pmid
           FROM project_pub_relation ppr
           JOIN projects pr ON pr.id = ppr.project_id
           JOIN pubs pb ON pb.id = ppr.pub_id
           ORDER BY ppr.rowid DESC""")

    # quick join: pubs per person
    sample_table(con, "Pubs per Person (joined)",
        """SELECT pe.first_name||' '||pe.last_name AS person,
                  COUNT(pb.id) AS n_pubs
           FROM people pe
           LEFT JOIN people_project_relation x ON x.person_id = pe.id
           LEFT JOIN project_pub_relation y ON y.project_id = x.project_id
           LEFT JOIN pubs pb ON pb.id = y.pub_id
           GROUP BY pe.id
           ORDER BY n_pubs DESC""")

    con.close()
    print("\n[OK] Sanity checks complete.")

def parse_args():
    ap = argparse.ArgumentParser(description="Smoke test for PubMed ETL into SQLite.")
    ap.add_argument("--csv", required=True, help="Faculty CSV (must include 'full_name').")
    ap.add_argument("--db", required=True, help="SQLite DB path, e.g., db/tracker.db")
    ap.add_argument("--schema", required=True, help="Schema SQL path, e.g., db/init.sql")
    ap.add_argument("--harvester", required=True, help="Path to harvest_pubmed_by_faculty.py")
    ap.add_argument("--out", required=True, help="Output JSON path, e.g., data/pubmed_recent.json")
    ap.add_argument("--affiliation", default="Yale", help="Affiliation hint")
    ap.add_argument("--num-papers", type=int, default=5, help="Most recent N pubs per faculty")
    return ap.parse_args()

def main():
    args = parse_args()
    db_path = Path(args.db)
    schema_path = Path(args.schema)
    harvester = Path(args.harvester)
    csv_path = Path(args.csv)
    out_json = Path(args.out)

    print("=== Step 1: Initialize DB ===")
    init_db(db_path, schema_path)

    print("\n=== Step 2: Run Harvester ===")
    run_harvester(harvester, csv_path, db_path, out_json, args.affiliation, args.num_papers)

    print("\n=== Step 3: Sanity Queries ===")
    sanity_checks(db_path)

if __name__ == "__main__":
    main()
