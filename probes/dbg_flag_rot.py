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
    for c in sh["components"]:
        # NetFlag/NetPort 实例（含 Name 属性的）
        nm = c["attrs"].get("Name") or ""
        if nm not in ("D3V3", "VOUT", "AGND", "VDDA", "VREF2.5V",
                      "H_DA_MOSI"):
            continue
        sym = lr.symbol_of(db, c)
        prims = db.symbol_records(sym) if sym else []
        tmpl_rot = tmpl_pos = None
        for a in (prims or []):
            if (isinstance(a, list) and a and a[0] == "ATTR"
                    and len(a) >= 12 and a[3] not in ("NAME", "NUMBER")
                    and a[7] is not None):
                tmpl_rot = a[9]
                tmpl_pos = (a[7], a[8])
                break
        print(f"{nm:10s} 实例rot={c.get('rot')} mirror={c.get('mirror')} "
              f"pos=({c['x']},{c['y']}) 模板NAME rot={tmpl_rot} "
              f"pos={tmpl_pos}")
    break
