import io, re, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
TOOL_DIR = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
sys.path.insert(0, TOOL_DIR)
import lceda_reader as lr

NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
db = lr.LcedaDB(NEW)

print("== P1: fallback 吸附距离分布 + 在线段覆盖率 ==")
dist = collections.Counter()
onseg_when_d2pos = 0
d2pos_total = 0
for uuid, title, sch, dt in db.sheets():
    if dt != 1:
        continue
    sh = lr.parse_sheet(db, uuid)
    comp_pins, wires, pt_wires, endp = lr._collect_pinmap_data(db, sh, uuid)
    merged = {}
    for (d_, cid), plist in comp_pins.items():
        merged.setdefault(d_, []).extend(plist)
    def np_(p):
        return (round(p[0], 1), round(p[1], 1))
    endp_all = set()
    for n in sh["nets"]:
        for px, py in n["points"]:
            endp_all.add(np_((px, py)))
    seglist = []
    for wid, segs in wires:
        for s_ in segs:
            seglist.append((np_((s_[0], s_[1])), np_((s_[2], s_[3]))))
    for d_, plist in merged.items():
        for p in plist:
            if p.get("no_connect"):
                continue
            px_, py_ = np_((p["x"], p["y"]))
            if (px_, py_) in endp_all:
                dist["d0_endpoint(命名或stub)"] += 1
                continue
            best = None
            for (wx, wy) in endp_all:
                d2 = (px_ - wx) ** 2 + (py_ - wy) ** 2
                if d2 <= 4 and (best is None or d2 < best[0]):
                    best = (d2, (wx, wy))
            if best is None:
                dist["no_endpoint_within2"] += 1
                continue
            d2 = best[0]
            if d2 == 0:
                dist["d0_but_not_in_endp_all(?!)"] += 1
            else:
                dist[f"d2={d2}"] += 1
                d2pos_total += 1
                for p1, p2 in seglist:
                    (x1, y1), (x2, y2) = p1, p2
                    cross = (x2 - x1) * (py_ - y1) - (y2 - y1) * (px_ - x1)
                    if abs(cross) < 0.75 and \
                            min(x1, x2) - 0.01 <= px_ <= max(x1, x2) + 0.01 and \
                            min(y1, y2) - 0.01 <= py_ <= max(y1, y2) + 0.01:
                        onseg_when_d2pos += 1
                        break
print("距离分布:", dict(dist))
print(f"d2>0 的吸附: {d2pos_total}, 其中在线段上: {onseg_when_d2pos}")

print("== P2: symbol_uuid vs device_uuid 映射与 BOM 影响 ==")
dmap = db.device_map()
sym2dev = collections.defaultdict(set)
dev2sym = collections.defaultdict(set)
diff_desc = 0
samples = []
for uuid, title, sch, dt in db.sheets():
    if dt != 1:
        continue
    sh = lr.parse_sheet(db, uuid)
    for c in sh["components"]:
        su, du = c.get("symbol_uuid"), c.get("device_uuid")
        if su and du:
            sym2dev[su].add(du)
            dev2sym[du].add(su)
multi = {s: v for s, v in sym2dev.items() if len(v) > 1}
print(f"带双 uuid 实例: {sum(len(v) for v in sym2dev.values())}, "
      f"symbol->多 device(会错并BOM): {len(multi)}", list(multi.items())[:3])
for su in list(sym2dev)[:3]:
    du = next(iter(sym2dev[su]))
    samples.append((su[:8], dmap.get(su, ("-", "-", "-"))[2][:30],
                    du[:8], dmap.get(du, ("-", "-", "-"))[2][:30]))
for s in samples:
    print("  sym:%s desc=%r | dev:%s desc=%r" % s)

print("== P2b: 连接器 desc 关键词来源 ==")
for d_ in ("RF1", "USBC1", "H1", "CN1", "H2"):
    for uuid, title, sch, dt in db.sheets():
        if dt != 1:
            continue
        sh = lr.parse_sheet(db, uuid)
        hit = False
        for c in sh["components"]:
            if c.get("designator") == d_:
                du = c.get("device_uuid")
                t, disp, desc = dmap.get(du, ("", "", "")) if du else ("", "", "")
                print(f"  {d_}: title={c.get('title')!r} device={disp!r} desc={desc[:60]!r}")
                hit = True
                break
        if hit:
            break

print("== P3: conn_nets 排除合成位号后的候选规模 ==")
def conn_nets2(dbx, desc_filter=True):
    res = {}
    dmapx = dbx.device_map()
    for uuid, title, sch, dt in dbx.sheets():
        if dt != 1:
            continue
        sh = lr.parse_sheet(dbx, uuid)
        pinc = lr._collect_pinmap_data(dbx, sh, uuid)
        if pinc is None:
            continue
        cp, ws, pw, ep = pinc
        dom = lr.resolve_nets_by_domain(dbx, sh, cp, ws, pw, ep)
        descs = {}
        for c in sh["components"]:
            if c.get("designator"):
                du = c.get("device_uuid")
                descs[c["designator"]] = dmapx.get(du, ("", "", ""))[2] if du else ""
        for (d_, pin), net in dom.items():
            if not d_ or d_.startswith(("PORT", "SHORT")):
                continue
            if pin.lower().startswith("pin"):
                continue
            is_conn = (d_[0] in ("H", "J", "P") or d_.startswith(("CN", "CON", "XS"))
                       or re.search(r"连接器|排针|排母|端子|座|header|connector|socket",
                                    descs.get(d_, ""), re.I))
            if is_conn and len(pin) <= 3:
                res.setdefault(d_, {}).setdefault(pin, set()).add(net or "")
    return res
na = conn_nets2(db)
print("新 conn 候选(NEW):", sorted(na))
pairs = []
dbs = [db, lr.LcedaDB(r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2")]
nb = conn_nets2(dbs[1])
cnt = 0
for da, pa in na.items():
    for dbb, pb in nb.items():
        if len(pa) != len(pb):
            continue
        cnt += 1
print(f"新候选对规模: {cnt} (原 70070)")