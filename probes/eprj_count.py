import io, sys, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
cur = conn.cursor()
tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")]
for t in sorted(tables):
    try:
        n = cur.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        if n:
            print(f"{t}: {n}")
    except Exception:
        print(f"{t}: ERR")
