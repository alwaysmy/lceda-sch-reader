"""二分定位爆炸 union 源：分别禁用 jumper/short/on_segment 试跑。"""
import io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
u = next(u for u, t, s, dt in db.sheets() if t.endswith("::controldac_a"))
sh = lr.parse_sheet(db, u)
pinc = lr._collect_pinmap_data(db, sh, u)
cp, ws_, pw, ep = pinc

def run(disable):
    parent = {}
    def norm_pt(p):
        return (round(p[0], 1), round(p[1], 1))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    seglist = []
    for wid, segs in ws_:
        pts = set()
        for x1, y1, x2, y2 in lr._norm_segs(segs):
            p1 = norm_pt((x1, y1)); p2 = norm_pt((x2, y2))
            pts.add(p1); pts.add(p2)
            if p1 != p2 and not disable.get("seg", False):
                seglist.append((p1, p2))
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
    pin_hit = {}
    def pk(p):
        return p.get("key") or p.get("pin")
    for des, plist in cp.items():
        for p in plist:
            if p.get("no_connect"):
                continue
            pt = norm_pt((p["x"], p["y"]))
            if pt in endp_all:
                pin_hit.setdefault((des, pk(p)), []).append(pt)
                continue
            if disable.get("onseg", False):
                continue
            for p1, p2 in seglist:
                x1, y1 = p1; x2, y2 = p2
                cross = (x2-x1)*(p["y"]-y1) - (y2-y1)*(p["x"]-x1)
                if abs(cross) <= 0.75 and \
                        min(x1,x2)-0.01 <= p["x"] <= max(x1,x2)+0.01 and \
                        min(y1,y2)-0.01 <= p["y"] <= max(y1,y2)+0.01:
                    parent.setdefault(pt, pt)
                    union(pt, p1); union(pt, p2)
                    pin_hit.setdefault((des, pk(p)), []).append(pt)
                    break
    if not disable.get("jumper", False):
        dmap = db.device_map()
        jumpers = set()
        for c in sh["components"]:
            if c.get("dnp"):
                continue
            du = c.get("device_uuid") or c.get("symbol_uuid") or ""
            desc = dmap.get(du, ("", "", ""))[2] if du else ""
            if lr._is_zero_ohm(c.get("title"), desc):
                jumpers.add(c.get("designator"))
        for des in jumpers:
            pl = cp.get(des, [])
            if len(pl) == 2:
                k0 = (des, pl[0].get("key") or pl[0].get("pin"))
                k1 = (des, pl[1].get("key") or pl[1].get("pin"))
                if k0 in pin_hit and k1 in pin_hit:
                    union(pin_hit[k0][0], pin_hit[k1][0])
    if not disable.get("short", False):
        des2dnp = {c.get("designator"): bool(c.get("dnp"))
                   for c in sh["components"]}
        for key, plist in list(cp.items()):
            des = key if isinstance(key, str) else key[0]
            if des2dnp.get(des):
                continue
            if len(plist) == 2 and any(p.get("sym_type") == 22
                                       for p in plist):
                k0 = (des, plist[0].get("key") or plist[0].get("pin"))
                k1 = (des, plist[1].get("key") or plist[1].get("pin"))
                if k0 in pin_hit and k1 in pin_hit:
                    union(pin_hit[k0][0], pin_hit[k1][0])
    # 统计最大域
    dom_size = collections.Counter()
    for p in list(parent):
        dom_size[find(p)] += 1
    top = dom_size.most_common(3)
    return f"域数={len(dom_size)} 最大域={top[0][1]} 前3={[c for _,c in top]}"

print("全部启用:", run({}))
print("禁 on_segment:", run({"onseg": True}))
print("禁 short:", run({"short": True}))
print("禁 jumper:", run({"jumper": True}))
print("禁全部三种:", run({"onseg": True, "short": True, "jumper": True}))
