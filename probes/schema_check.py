import io, sqlite3, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
OLD = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2"

for label, p in (("NEW", NEW), ("OLD", OLD)):
    print("======", label, p)
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({name})").fetchall()]
        n = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"  {name} ({n} rows): {', '.join(cols)}")
    conn.close()
