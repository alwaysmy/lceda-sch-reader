import io, sys, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
conn = sqlite3.connect(
    r"file:C:\Users\dell\Documents\LCEDA-Pro\database\web.db?mode=ro", uri=True)
tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")]
print("web.db 表:", tables)
for t in tables:
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        if n:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info([{t}])")]
            print(f"  {t}: {n} 行, 列: {cols[:10]}")
    except Exception:
        pass
