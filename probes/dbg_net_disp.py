import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

db = lr.LcedaDB(r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch"
                r"\涡流传感器-V1.0-2026.04.01.eprj2")
for u, t, s, dt in db.sheets():
    if dt != 1 or t != "高速DA":
        continue
    n_net = n_placed = 0
    for a in db.sheet_records(u):
        if not (isinstance(a, list) and a and a[0] == "ATTR"
                and len(a) >= 11 and a[3] in ("NET", "Global Net Name")):
            continue
        n_net += 1
        placed = a[7] is not None and a[8] is not None
        if placed:
            n_placed += 1
            print("已放置:", a[4], "@", a[7], a[8], "style=", a[10])
    print(f"NET 属性共 {n_net}, 带显示位的 {n_placed}")
    # 字体族样例：TEXT/FONTSTYLE 里出现的字体名
    fams = {}
    for a in db.sheet_records(u):
        if isinstance(a, list) and a and a[0] == "FONTSTYLE":
            fams[a[1]] = a[4]
    print("页 FONTSTYLE 字体名:", {k: v for k, v in fams.items() if v})
    break
