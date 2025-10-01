import sqlite3, pathlib

SQL_PATH = pathlib.Path("schema.sql")
DB_PATH  = pathlib.Path("../tracker.db") # create db in parent directory

def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    sql = SQL_PATH.read_text(encoding="utf-8")
    with sqlite3.connect(DB_PATH) as cxn:
        cxn.executescript(sql)
    print(f"Created {DB_PATH} from {SQL_PATH}")

if __name__ == "__main__":
    main()
