import io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
u = next(u for u, t, s, dt in db.sheets()
         if t.endswith("::controldac_a"))
sh = lr.parse_sheet(db, u)
pinc = lr._collect_pinmap_data(db, sh, u)
cp, ws_, pw, ep = pinc
sizes = sorted(((len(lr._norm_segs(seg)), wid) for wid, seg in ws_),
               reverse=True)[:6]
print("wire 段数 top:", sizes)
wid = sizes[0][1]
segs = lr._norm_segs(dict(ws_)[wid])
pts = set()
for x1, y1, x2, y2 in segs:
    pts.add((round(x1,1), round(y1,1)))
    pts.add((round(x2,1), round(y2,1)))
print(f"最大 wire {wid[:10]}: 段 {len(segs)}, 端点 {len(pts)}")
xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
print("  范围 x:", min(xs), max(xs), " y:", min(ys), max(ys))
# 该 wire 的 NET 名集合
nets = set()
for n in sh["nets"]:
    if any((round(px,1), round(py,1)) in pts for px, py in n["points"]):
        if n["net"]:
            nets.add(n["net"])
print("  涉及网络名数:", len(nets), sorted(nets)[:8])
