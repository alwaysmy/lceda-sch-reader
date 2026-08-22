import io, sys, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
tables = sorted(r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"))
for t in tables:
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        if n:
            print(f"  {t}: {n}")
    except Exception:
        pass
print("\n== documents docType 分布 ==")
try:
    for row in conn.execute("SELECT docType, COUNT(*) FROM documents GROUP BY docType"):
        print("  ", row)
except Exception:
    print("  无 documents 表")
print("\n== projects.name ==")
try:
    print(" ", conn.execute("SELECT name FROM projects").fetchone())
except Exception:
    pass
