import io, os, re, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
TOOL_DIR = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
sys.path.insert(0, TOOL_DIR)
import lceda_reader as lr

NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
OLD = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2"

def pages(db):
    for uuid, title, sch, dt in db.sheets():
        if dt == 1:
            yield uuid, title

print("=" * 30, "A1: 0Ω 判定", "=" * 30)
dbN = lr.LcedaDB(NEW)
re_bridge = re.compile(r"0000|0R|0Ω|0RΩ", re.I)
re_union_sub = "0000"
cands = []
for db_tag, dbx in (("NEW", dbN),):
    for uuid, title in pages(dbx):
        sh = lr.parse_sheet(dbx, uuid)
        for c in sh["components"]:
            t = c.get("title") or ""
            if t and (re_bridge.search(t) or re_union_sub in t):
                du = c.get("device_uuid")
                desc = ""
                if du:
                    dmap = dbx.device_map()
                    desc = dmap.get(du, ("", "", ""))[2]
                cands.append((t, c.get("designator"), desc[:50]))
print(f"命中 bridge/union 正则的 title 共 {len(cands)}:")
for t, d, desc in sorted(set(cands))[:20]:
    print(f"  title={t!r} des={d} desc={desc}")
# 潜在误报：形如 X0R 的阻值（10R/20R...）
fp = [c for c in cands if re.search(r"(?:^|[^0-9.])[1-9]\d*0R", c[0], re.I)]
print("其中 'X0R'(如10R) 误报:", len(fp), fp[:5])
# 真实 0Ω 器件（desc 含 0000 或 0Ω）但 title 不含关键字的漏报
miss = []
dmap = dbN.device_map()
for uuid, title in pages(dbN):
    sh = lr.parse_sheet(dbN, uuid)
    for c in sh["components"]:
        du = c.get("device_uuid")
        desc = dmap.get(du, ("", "", ""))[2] if du else ""
        t = c.get("title") or ""
        if desc and re.search(r"(?:^|[^0-9.])0\s*(?:Ω|R|ohm)", desc, re.I) and \
                not (re_bridge.search(t)):
            miss.append((t, c.get("designator"), desc[:40]))
print("desc 是 0Ω 但 title 不匹配（union 会漏）:", len(miss), miss[:8])

print("=" * 30, "A3: 非90°旋转", "=" * 30)
rot_hist = collections.Counter()
odd = []
for uuid, title in pages(dbN):
    for a in dbN.sheet_records(uuid):
        if isinstance(a, list) and a and a[0] == "COMPONENT":
            rot = a[5] if len(a) > 5 else 0
            rot_hist[rot] += 1
            if rot % 90 != 0:
                odd.append((title, a[1], rot))
print("rot 分布:", dict(rot_hist))
print("非90°倍数:", len(odd), odd[:5])

print("=" * 30, "A4a: NET属性挂实例的 symbol_type 分布", "=" * 30)
symtype_dist = collections.Counter()
for uuid, title in pages(dbN):
    sh = lr.parse_sheet(dbN, uuid)
    comp_cids = {c["cid"]: c for c in sh["components"]}
    for a in dbN.sheet_records(uuid):
        if isinstance(a, list) and len(a) >= 5 and a[0] == "ATTR" and \
                a[3] in ("NET", "Global Net Name"):
            cid = a[2]
            if cid in comp_cids:
                sym = lr.symbol_of(dbN, comp_cids[cid])
                sp = dbN.symbol_pins(sym) if sym else None
                st = sp.get("symbol_type") if sp else None
                symtype_dist[st] += 1
print("挂实例的 NET/GNN 属性按 symbol_type:", dict(symtype_dist))

print("=" * 30, "A4b: 18/19 符号引脚名", "=" * 30)
seen_sym = set()
pn = collections.Counter()
for uuid, title in pages(dbN):
    sh = lr.parse_sheet(dbN, uuid)
    for c in sh["components"]:
        sym = lr.symbol_of(dbN, c)
        if not sym or sym in seen_sym:
            continue
        sp = dbN.symbol_pins(sym)
        seen_sym.add(sym)
        if sp and sp.get("symbol_type") in (18, 19):
            for p in sp["pins"]:
                pn[p["name"]] += 1
print("18/19 符号引脚名分布:", dict(pn))

print("=" * 30, "A4c: link-check 假候选(PORT/SHORT)", "=" * 30)
dbO = lr.LcedaDB(OLD)
pairs = lr._conn_pairs(dbN, dbO)
weird = [p for p in pairs if p[0].startswith(("PORT", "SHORT")) or
         p[1].startswith(("PORT", "SHORT"))]
print(f"候选对总数={len(pairs)}, 含 PORT/SHORT 合成位号={len(weird)}")
for p in weird[:6]:
    print("  ", p)

print("=" * 30, "A5: 实例带 Symbol 属性?", "=" * 30)
cnt_sym_attr = 0
for uuid, title in pages(dbN):
    sh = lr.parse_sheet(dbN, uuid)
    cids = {c["cid"] for c in sh["components"]}
    for a in dbN.sheet_records(uuid):
        if isinstance(a, list) and len(a) >= 5 and a[0] == "ATTR" and \
                a[3] == "Symbol" and a[2] in cids:
            cnt_sym_attr += 1
print("实例级 Symbol 属性数:", cnt_sym_attr)

print("=" * 30, "A6: 页标题块 cid=='e1'", "=" * 30)
bad_e1 = []
for uuid, title in pages(dbN):
    recs = dbN.sheet_records(uuid)
    has_e1 = any(isinstance(a, list) and a and a[0] == "COMPONENT" and a[1] == "e1"
                 for a in recs)
    at_cids = {a[2] for a in recs if isinstance(a, list) and len(a) >= 5
               and a[0] == "ATTR" and isinstance(a[3], str) and a[3].startswith("@")}
    if not has_e1 or (at_cids and "e1" not in at_cids):
        bad_e1.append((title, has_e1, sorted(at_cids)[:4]))
print(f"页数中 e1 异常: {len(bad_e1)}", bad_e1[:5])

print("=" * 30, "A7a: NO_CONNECT 取值 / A7b: 网络名含逗号", "=" * 30)
nc_vals = collections.Counter()
comma_nets = set()
for uuid, title in pages(dbN):
    for a in dbN.sheet_records(uuid):
        if isinstance(a, list) and len(a) >= 5 and a[0] == "ATTR":
            if a[3] == "NO_CONNECT":
                nc_vals[str(a[4])] += 1
            if a[3] in ("NET", "Global Net Name") and "," in str(a[4]):
                comma_nets.add(a[4])
print("NO_CONNECT 值分布:", dict(nc_vals))
print("含逗号网络名:", comma_nets or "无")

print("=" * 30, "B1: 电源网名分类对比", "=" * 30)
all_nets = set()
for uuid, title in pages(dbN):
    sh = lr.parse_sheet(dbN, uuid)
    for n in sh["nets"]:
        if n["net"]:
            all_nets.add(n["net"])

def is_power_new(name):
    u = name.upper()
    if "GND" in u:
        return True
    if u in ("VCC", "VDD", "VSS", "VBUS", "VBAT", "VPP", "VREF") or \
            u.startswith(("VCC", "VDD", "VSS", "AVDD", "AVSS", "VDDA",
                          "VSSA", "VCCA", "VCCD")):
        return True
    if re.match(r"^[+-]?\d+(\.\d+)?V$", u):
        return True
    if re.match(r"^[+-]?D?\d+V\d+$", u):
        return True
    return False

cur_hit = {n for n in all_nets if lr.POWER_NET_RE.match(n)}
new_hit = {n for n in all_nets if is_power_new(n)}
print("现正则命中:", sorted(cur_hit))
print("新分类多识别(将开始跳过):", sorted(new_hit - cur_hit))
print("新分类丢失(回归!):", sorted(cur_hit - new_hit))

print("=" * 30, "B2: 连接器前缀覆盖", "=" * 30)
conn_truth = set()
des_all = {}
for uuid, title in pages(dbN):
    sh = lr.parse_sheet(dbN, uuid)
    for c in sh["components"]:
        if c.get("designator"):
            du = c.get("device_uuid")
            desc = dmap.get(du, ("", "", ""))[2] if du else ""
            des_all.setdefault(c["designator"], desc)
for d, desc in des_all.items():
    if re.search(r"连接器|排针|排母|端子|座|header|connector|socket", desc, re.I):
        conn_truth.add(d)
pref_ok = {d for d in des_all
           if d[0] in ("H", "J", "P") or d.startswith("CN")}
print("desc 判定为连接器:", sorted(conn_truth))
print("其中前缀未覆盖(漏):", sorted(conn_truth - pref_ok))
print("前缀命中但 desc 非连接器(误收样例):",
      sorted(pref_ok - conn_truth)[:15])

print("=" * 30, "坐标容差/SNAP 插桩", "=" * 30)
tot = collections.Counter()
fb_samples = []
tol_deltas = collections.Counter()
for uuid, title in pages(dbN):
    sh = lr.parse_sheet(dbN, uuid)
    comp_pins, wires, pt_wires, endp = lr._collect_pinmap_data(dbN, sh, uuid)
    merged = {}
    for (des, cid), plist in comp_pins.items():
        merged.setdefault(des, []).extend(plist)
    def np_(p):
        return (round(p[0], 1), round(p[1], 1))
    endp_net = {}
    for n in sh["nets"]:
        if n["net"]:
            for px, py in n["points"]:
                endp_net.setdefault(np_((px, py)), n["net"])
    wpts = set()
    seglist = []
    for wid, segs in wires:
        for s_ in segs:
            p1, p2 = np_((s_[0], s_[1])), np_((s_[2], s_[3]))
            wpts.add(p1)
            wpts.add(p2)
            seglist.append((p1, p2))
    for des, plist in merged.items():
        for p in plist:
            if p.get("no_connect"):
                tot["nc_skip"] += 1
                continue
            px_, py_ = np_((p["x"], p["y"]))
            exact = (px_, py_) in endp_net
            tol_hit = None
            if not exact:
                for (ex, ey) in endp_net:
                    dx, dy = abs(px_ - ex), abs(py_ - ey)
                    if dx <= 2 and dy <= 2:
                        tol_hit = (dx, dy, ex, ey)
                        break
            if exact:
                tot["exact_named"] += 1
            elif tol_hit:
                tot["tol_named"] += 1
                tol_deltas[(tol_hit[0], tol_hit[1])] += 1
            else:
                best = None
                for (wx, wy) in wpts:
                    d2 = (px_ - wx) ** 2 + (py_ - wy) ** 2
                    if d2 <= 4 and (best is None or d2 < best[0]):
                        best = (d2, (wx, wy))
                if best:
                    tot["fallback_snap"] += 1
                    on_seg = False
                    for p1, p2 in seglist:
                        (x1, y1), (x2, y2) = p1, p2
                        cross = (x2 - x1) * (py_ - y1) - (y2 - y1) * (px_ - x1)
                        if abs(cross) < 0.75 and \
                                min(x1, x2) - 0.01 <= px_ <= max(x1, x2) + 0.01 and \
                                min(y1, y2) - 0.01 <= py_ <= max(y1, y2) + 0.01:
                            on_seg = True
                            break
                    fb_samples.append((title, des, p.get("key") or p["pin"],
                                       best[1], endp_net.get(best[1]), on_seg))
                else:
                    tot["no_hit"] += 1
print("引脚命中统计:", dict(tot))
print("容差命中偏移分布(dx,dy):", dict(tol_deltas))
print(f"fallback 吸附样本({len(fb_samples)}):")
for s in fb_samples[:15]:
    print("   page=%s %s.%s -> %s net=%r 在线段上=%s" % s)