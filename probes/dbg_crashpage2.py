import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
u = next(u for u, t, s, dt in db.sheets() if t.endswith("::controldac"))
sh = lr.parse_sheet(db, u)
print("components:", len(sh["components"]), "nets:", len(sh["nets"]),
      "命名:", sum(1 for n in sh["nets"] if n["net"]))
pinc = lr._collect_pinmap_data(db, sh, u)
cp, ws_, pw, ep = pinc
print("comp_pins 键数:", len(cp), "wires:", len(ws_),
      "endp:", len(ep), "pt_wires:", len(pw))
# 崩溃点 (625,1085)：是否在 endp_all / parent
import itertools
target = (625.0, 1085.0)
in_endp = target in ep
print("崩溃点 in endp:", in_endp)
# 找引用该点的引脚
for k, plist in list(cp.items())[:200]:
    for p in plist:
        if abs(p["x"]-625) < 1 and abs(p["y"]-1085) < 1:
            print("  引脚:", k[0], p.get("key"), (p["x"], p["y"]))
# 该页 COMPONENT/WIRE 样例
recs = db.sheet_records(u)
kinds = collections.Counter(r[0] for r in recs)
print("记录分布:", dict(kinds))
wires = [r for r in recs if r[0] == "WIRE"]
if wires:
    print("WIRE 样例:", json.dumps(wires[0][:3])[:150],
          "段数:", len(wires[0][2]))
comps = [r for r in recs if r[0] == "COMPONENT"]
if comps:
    print("COMPONENT 样例:", json.dumps(comps[0])[:180])
