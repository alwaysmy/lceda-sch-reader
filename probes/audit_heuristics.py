"""启发式审计探针：验证哪些启发式有结构化替代信息。

1. 0Ω 识别：实例/器件 attrs 是否有规范 Value 字段（vs description 正则）
2. 电源网判定：NetFlag(18) 挂接的网络名是否可作结构化信号
3. 渲染 T 形结点：线端落在另一线段内部（EDA 画结点、当前 seg_count>=3 漏）
"""
import io, sys, re, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

E = (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch"
     r"\涡流传感器-V1.0-2026.04.01.eprj2")
db = lr.LcedaDB(E)

# ── 1) 0Ω：Value attr vs description 正则 ──
dmap = db.device_map()
n_desc0 = n_val0 = n_val_missing = 0
samples = []
for u, t, s, dt in db.sheets():
    if dt != 1:
        continue
    sh = lr.parse_sheet(db, u)
    for c in sh["components"]:
        if not lr._is_zero_ohm(c.get("title") or "",
                               dmap.get(c.get("device_uuid") or "",
                                         ("", "", ""))[2]):
            continue
        du = c.get("device_uuid")
        da = db.device_attrs(du) if du else {}
        val = da.get("Value") or c["attrs"].get("Value")
        if val is not None:
            is0 = bool(re.search(r"^0\s*(Ω|欧|R|ohm)?$", str(val).strip(),
                                 re.I)) or str(val).strip() in ("0", "0R")
            if is0:
                n_val0 += 1
            elif n_val_missing < 5:
                samples.append((c.get("designator"), repr(val)))
        else:
            n_val_missing += 1
        n_desc0 += 1
print(f"0Ω(启发式命中)={n_desc0}, 其中 Value attr 确认 0: {n_val0}, "
      f"无 Value: {n_val_missing}, Value 非0 样例: {samples[:5]}")

# Value attr 的整体分布（电阻件）
vals = collections.Counter()
for u, t, s, dt in list(db.sheets())[:3]:
    if dt != 1:
        continue
    sh = lr.parse_sheet(db, u)
    for c in sh["components"]:
        du = c.get("device_uuid")
        da = db.device_attrs(du) if du else {}
        if "Value" in da:
            vals[da["Value"]] += 1
print("Value attr 分布(top10):", vals.most_common(10))

# ── 2) 电源网：NetFlag(18) 挂接网络名（结构化信号）──
power_flags = set()
for u, t, s, dt in list(db.sheets())[:5]:
    if dt != 1:
        continue
    sh = lr.parse_sheet(db, u)
    pinc = lr._collect_pinmap_data(db, sh, u)
    if not pinc:
        continue
    cp, ws, pw, ep = pinc
    for (des, cid), plist in cp.items():
        for p in plist:
            if p.get("sym_type") == 18 and p.get("key"):
                power_flags.add(str(p["key"]))
print(f"\nNetFlag(18) 命名的网络(前5页)共 {len(power_flags)} 个")
print("样例:", sorted(power_flags)[:20])
# 这些名字是否都被 is_power_net 覆盖
miss = [n for n in power_flags if not lr.is_power_net(n)]
print("is_power_net 未覆盖:", miss[:15], f"({len(miss)} 个)")

# ── 3) T 形结点：线端落在另一线段内部（渲染漏结点）──
n_t = 0
for u, t, s, dt in list(db.sheets())[:3]:
    if dt != 1:
        continue
    recs = db.sheet_records(u)
    segs = []
    for a in recs:
        if isinstance(a, list) and a and a[0] == "WIRE" and len(a) >= 3:
            for seg in lr._norm_segs(a[2]):
                segs.append(seg)
    eps = collections.Counter()
    for x1, y1, x2, y2 in segs:
        eps[(round(x1, 1), round(y1, 1))] += 1
        eps[(round(x2, 1), round(y2, 1))] += 1
    for x1, y1, x2, y2 in segs:
        # 端点落在水平/垂直段内部
        for ex, ey in ((x1, y1), (x2, y2)):
            k = (round(ex, 1), round(ey, 1))
            if eps.get(k):
                continue
            if x1 == x2 and min(y1, y2) < ey < max(y1, y2) \
                    and abs(ex - x1) < 0.05:
                n_t += 1
                break
            if y1 == y2 and min(x1, x2) < ex < max(x1, x2) \
                    and abs(ey - y1) < 0.05:
                n_t += 1
                break
        else:
            continue
        break
print(f"\n含 T 形结点的页(前3页采样): 检出 T 结点线段对 {n_t}")
