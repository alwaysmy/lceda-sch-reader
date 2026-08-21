import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

E1 = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
db = lr.EproDB(E1)

# 找 quadPizeoDriver_RevA::ControlDAC_A
for uuid, title, sch, dt in db.sheets():
    if title == "quadPizeoDriver_RevA::ControlDAC_A":
        page = uuid
        break
sheet = lr.parse_sheet(db, page)
pinc = lr._collect_pinmap_data(db, sheet, page)
cp, ws, pw, ep = pinc

# 手动走匹配逻辑看候选
sig = lr._cbb_sig(db)
inst_pins = set()
for k, plist in cp.items():
    for p in plist:
        if p.get("sym_type") == 17:
            inst_pins.add(p.get("pin"))
print("CBB 实例引脚集:", len(inst_pins))
cands = {u: v for u, v in sig.items() if v[0] == frozenset(inst_pins)}
print("端口集匹配候选:", [(u[:8], v[2]) for u, v in cands.items()])
groups = {}
for u, (ports, fp, title) in cands.items():
    groups.setdefault(fp, []).append(title)
print("内容指纹分组数:", len(groups),
      [[t for _, t in m] for m in [g for g in groups.values()]])

# 完整 resolve 看展开结果
dom = lr.resolve_nets_by_domain(db, sheet, cp, ws, pw, ep)
exp = [(k, v) for k, v in dom.items() if "." in k[0]]
print(f"\n展开条目数: {len(exp)}")
for k, v in exp[:8]:
    print("  ", k, "->", v[:60])