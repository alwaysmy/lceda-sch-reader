import io, sqlite3, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"

conn = sqlite3.connect(f"file:{NEW}?mode=ro", uri=True)
cur = conn.cursor()

print("== documents 表：同名页全部记录 ==")
rows = list(cur.execute(
    "SELECT uuid, display_title, schematic_uuid, docType, length(dataStr) FROM documents ORDER BY display_title"))
from collections import defaultdict
by_title = defaultdict(list)
for u, t, s, dt, L in rows:
    by_title[t].append((u, s, dt, L))
for t, recs in sorted(by_title.items()):
    if len(recs) > 1:
        print(f"\n[{t}] {len(recs)} 条:")
        for u, s, dt, L in recs:
            print(f"  uuid={u[:12]} sch={s} docType={dt} len={L}")

print("\n== schematics 表 ==")
for r in cur.execute("SELECT uuid, name, display_name FROM schematics"):
    print(f"  uuid={r[0][:12]} name={r[1]} display={r[2]}")

print("\n== 同名页 dataStr 是否相同（schematic1 vs schematic1_2 的 激励输出和AD采集）==")
for t in ["激励输出和AD采集", "DA输出", "P1"]:
    recs = list(cur.execute(
        "SELECT schematic_uuid, length(dataStr) FROM documents WHERE display_title=?", (t,)))
    print(f"  {t}: {recs}")

conn.close()