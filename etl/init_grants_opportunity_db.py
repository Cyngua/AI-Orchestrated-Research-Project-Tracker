import sqlite3, pathlib

SQL_PATH = pathlib.Path("grants_opportunity_schema.sql")
DB_PATH  = pathlib.Path("../grants_opportunity.db")

def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    sql = SQL_PATH.read_text(encoding="utf-8")
    with sqlite3.connect(DB_PATH) as cxn:
        cxn.execute("PRAGMA foreign_keys = ON;")  # optional but good practice
        cxn.executescript(sql)
    print(f"Created {DB_PATH} from {SQL_PATH}")

if __name__ == "__main__":
    main()
