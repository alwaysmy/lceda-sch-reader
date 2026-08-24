import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

db = lr.LcedaDB(r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch"
                r"\涡流传感器-V1.0-2026.04.01.eprj2")
for u, t, s, dt in db.sheets():
    if dt != 1 or t != "高速DA":
        continue
    recs = db.sheet_records(u)
    # e621 的全部原始 ATTR 记录（含重复 key）
    print("== e621 原始 ATTR ==")
    for a in recs:
        if (isinstance(a, list) and a and a[0] == "ATTR"
                and str(a[2]) == "e621"):
            print(f"  {a[3]}={a[4]!r} X={a[7]} Y={a[8]} style={a[10]}")
    sh = lr.parse_sheet(db, u)
    for c in sh["components"]:
        if c.get("designator") == "U27":
            print("== parse_sheet 后 attrs ==")
            for k, v in c["attrs"].items():
                print(f"  {k}={v!r}")
            print("title=", c["title"])
    break
