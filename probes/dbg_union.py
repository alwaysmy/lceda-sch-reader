"""插桩 resolve：捕获跨网络非法 union 事件。"""
import io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
u = next(u for u, t, s, dt in db.sheets()
         if t.endswith("::controldac"))
sh = lr.parse_sheet(db, u)
pinc = lr._collect_pinmap_data(db, sh, u)
cp, ws_, pw, ep = pinc

# 复制 resolve 逻辑并插桩（关键段）
parent = {}
def norm_pt(p):
    return (round(p[0], 1), round(p[1], 1))
def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x
def union(a, b, tag=""):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[rb] = ra

wire_pts = {}
seglist = []
for wid, segs in ws_:
    pts = set()
    for x1, y1, x2, y2 in lr._norm_segs(segs):
        p1 = norm_pt((x1, y1)); p2 = norm_pt((x2, y2))
        pts.add(p1); pts.add(p2)
        if p1 != p2:
            seglist.append((p1, p2))
    if not pts:
        continue
    wire_pts[wid] = pts
    for p in pts:
        parent.setdefault(p, p)
    first = next(iter(pts))
    for p in pts:
        union(p, first)

endp_net = {}
endp_all = set()
for n in sh["nets"]:
    for px, py in n["points"]:
        npt = norm_pt((px, py))
        endp_all.add(npt)
        if n["net"] and npt not in endp_net:
            endp_net[npt] = n["net"]
for p in endp_all:
    parent.setdefault(p, p)

# 检查：每个 wire 内部是否有跨名端点（正常，同 wire 可多段多名？）
# 关键检查：不同 wire 之间是否共享端点坐标（T 型）导致跨网 union？
pt_to_wires = collections.defaultdict(set)
for wid, pts in wire_pts.items():
    for p in pts:
        pt_to_wires[p].add(wid)
shared = {p: w for p, w in pt_to_wires.items() if len(w) > 1}
print("多 wire 共享端点数:", len(shared))
bad = 0
for p, wids in list(shared.items())[:10]:
    nets = set()
    for wid in wids:
        # 该 wire 的名
        pass
    print("  点", p, "wires:", list(wids)[:4])
    bad += 1

# 合成点（port 补充）数量
synth = [p for p in endp_all if p not in pt_to_wires]
print("合成点(非wire端点)数:", len(synth), synth[:6])
