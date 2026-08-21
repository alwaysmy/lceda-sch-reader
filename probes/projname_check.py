import io, json, sqlite3, sys, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
OLD = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2"

for label, p in (("NEW", NEW), ("OLD", OLD)):
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    print(f"==== {label}: projects 表")
    for row in conn.execute(
            "SELECT uuid, name, content, boards, pcb_count, branch_uuid, default_sheet, created_at, updated_at FROM projects").fetchall():
        print("  uuid:", row[0])
        print("  name:", row[1])
        print("  boards:", row[3])
        print("  pcb_count:", row[4])
        print("  default_sheet:", row[6])
        print("  created_at:", row[7], " updated_at:", row[8])
        try:
            c = json.loads(row[2])
            print("  content keys:", list(c.keys())[:20])
        except Exception as e:
            print("  content (raw, 200 chars):", str(row[2])[:200])
    conn.close()
