"""找 dom 中同时含 GND 与 DAC0_SCLK_A 的引脚（桥接点）。"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
u = next(u for u, t, s, dt in db.sheets() if t.endswith("::controldac"))
sh = lr.parse_sheet(db, u)
pinc = lr._collect_pinmap_data(db, sh, u)
cp, ws_, pw, ep = pinc
dom = lr.resolve_nets_by_domain(db, sh, cp, ws_, pw, ep)

bridges = []
for (des, pin), v in dom.items():
    toks = set(t for t in v.split(",") if t)
    if "GND" in toks and "DAC0_SCLK_A" in toks:
        bridges.append((des, pin, sorted(toks)))
print("双名引脚数:", len(bridges))
for b in bridges[:8]:
    print("  ", b[0], b[1], "->", ",".join(b[2])[:80])
# 该引脚坐标
if bridges:
    des, pin = bridges[0][0], bridges[0][1]
    for k, plist in cp.items():
        if (k if isinstance(k, str) else k[0]) == des:
            for p in plist:
                if (p.get("key") or p.get("pin")) == pin:
                    print("  坐标:", (p["x"], p["y"]),
                          "sym_type:", p.get("sym_type"))
