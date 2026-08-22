import io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db = lr.Epro2DB(V3)
page = None
for u, t, s, dt in db.sheets():
    if t == "quadPizeoDriver_RevA::ControlDAC_A":
        page = u
        break
sheet = lr.parse_sheet(db, page)
pinc = lr._collect_pinmap_data(db, sheet, page)
cp, ws, pw, ep = pinc
dom = lr.resolve_nets_by_domain(db, sheet, cp, ws, pw, ep)
named = sum(1 for v in dom.values() if v)
print(f"dom 引脚={len(dom)} 有网络名={named}")

# U41 各脚
for k, v in sorted(dom.items()):
    if k[0] == "U41":
        print("  U41", k[1], "->", v[:40])

# wire 记录段数分布（LINE.lineGroup 聚合是否成功）
segcnt = collections.Counter(len(s) for _, s in ws)
print("wire 段数分布:", dict(sorted(segcnt.items())[:8]))

# 检查 (1215,-730) 与 (1215,-750) 是否同一 wire
import itertools
for wid, segs in ws:
    pts = set()
    for x1, y1, x2, y2 in segs:
        pts.add((round(x1, 1), round(y1, 1)))
        pts.add((round(x2, 1), round(y2, 1)))
    if (1215.0, -730.0) in pts:
        has_named = (1215.0, -750.0) in pts
        print(f"wire {wid[:10]} 含 pin0 点, 同wire含命名点(1215,-750)? {has_named}, "
              f"段数={len(segs)}")
