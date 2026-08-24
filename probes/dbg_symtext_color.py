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
    sh = lr.parse_sheet(db, u)
    # 1) DAC 符号内 TEXT/ATTR 的样式与颜色
    for c in sh["components"]:
        if c.get("designator") != "U27":
            continue
        sym = lr.symbol_of(db, c)
        row = db.cur.execute(
            "SELECT dataStr FROM components WHERE uuid=?", (sym,)).fetchone()
        text = db.decompress(row[0])
        fs = {}
        for ln in text.splitlines():
            try:
                a = json.loads(ln)
            except Exception:
                continue
            if not isinstance(a, list):
                continue
            if a[0] == "FONTSTYLE":
                fs[a[1]] = a
            elif a[0] == "TEXT" and len(a) >= 7:
                print(f"符TEXT {a[5]!r:20s} style={a[6]} -> "
                      f"color={fs.get(a[6], ['?','?'])[2] if a[6] in fs else '?'}")
            elif a[0] == "ATTR" and len(a) >= 12 and a[3] not in (
                    "NAME", "NUMBER") and a[7] is not None:
                print(f"符ATTR {a[3]!r}={a[4]!r:16s} style={a[10]} -> "
                      f"color={fs.get(a[10], [None, None, None])[2]}")
    # 2) AGND/VDDA NET 标签的 rot
    for a in recs:
        if (isinstance(a, list) and a and a[0] == "ATTR" and len(a) >= 11
                and a[3] in ("NET",) and a[4] in ("AGND", "VDDA")
                and a[7] is not None):
            print(f"NET {a[4]} @({a[7]},{a[8]}) rot={a[9]} style={a[10]}")
    break
