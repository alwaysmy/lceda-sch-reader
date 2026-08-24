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
    # 找 x/y 在原点附近的 COMPONENT
    for a in recs:
        if not (isinstance(a, list) and a and a[0] == "COMPONENT"):
            continue
        x, y = a[3], a[4]
        if x is None or y is None:
            continue
        if abs(x) < 150 and abs(y) < 150:
            print(f"COMPONENT cid={a[1]} title={a[2]} x={x} y={y} "
                  f"rot={a[5]} mirror={a[6]}")
            cid = str(a[1])
            for b in recs:
                if (isinstance(b, list) and b and b[0] == "ATTR"
                        and len(b) >= 11 and str(b[2]) == cid):
                    print(f"   ATTR key={b[3]} val={b[4]!r} showK={b[5]} "
                          f"showV={b[6]} X={b[7]} Y={b[8]} rot={b[9]} "
                          f"style={b[10]} locked={b[11]}")
    break
