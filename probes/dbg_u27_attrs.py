import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

db = lr.LcedaDB(r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch"
                r"\涡流传感器-V1.0-2026.04.01.eprj2")
for u, t, s, dt in db.sheets():
    if dt != 1 or t != "高速DA":
        continue
    recs = db.sheet_records(u)
    fs = {}
    for a in recs:
        if isinstance(a, list) and a and a[0] == "FONTSTYLE" and len(a) > 1:
            fs[a[1]] = a
    for a in recs:
        if (isinstance(a, list) and a and a[0] == "ATTR" and len(a) >= 11
                and str(a[2]) == "e107"  # U27 cid? 先打印再确认
                and a[3] in ("Name", "Value", "Designator", "Description")):
            print(f"U27? {a[3]}={a[4]!r} X={a[7]} Y={a[8]} rot={a[9]} "
                  f"style={a[10]} -> FONTSTYLE={fs.get(a[10])}")
    # 找到真正的 U27 cid
    for a in recs:
        if (isinstance(a, list) and a and a[0] == "ATTR" and len(a) >= 5
                and a[3] == "Designator" and a[4] == "U27"):
            cid = str(a[2])
            print(f"\nU27 cid={cid}")
            for b in recs:
                if (isinstance(b, list) and b and b[0] == "ATTR"
                        and len(b) >= 11 and str(b[2]) == cid):
                    print(f"  {b[3]}={b[4]!r:22s} showK={b[5]} showV={b[6]} "
                          f"X={b[7]} Y={b[8]} rot={b[9]} style={b[10]} -> "
                          f"{fs.get(b[10])}")
            break
    break
