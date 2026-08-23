"""探针：镜像×旋转复合顺序实证。
对每页找 mirror=1 且 rot 非 0 的实例，取其引脚，分别按两种顺序计算
绝对坐标，看哪种顺序命中有名导线端点。
规范(原理图文档格式.pdf §3.3.2)：1.绕原点逆时针旋转 2.绕Y轴水平镜像 3.平移
即 T·M·R（先旋转后镜像）；现行 pinmap 代码为 T·R·M（先镜像后旋转）。"""
import io, sys, math, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

E = r"D:\WorkDesigns\2_WorkProjects\E_distance\1\1".replace(
    r"\1\1", r"\1_sch\涡流传感器-V1.0-2026.04.01.eprj2")
db = lr.LcedaDB(E)

def pin_abs(px, py, cx, cy, rot, mirror, order):
    if order == "RM":   # 先镜像后旋转（现行代码）
        rx, ry = (px, py)
        if mirror:
            rx = -rx
        n = int(rot % 360) // 90
        for _ in range(n):
            rx, ry = -ry, rx
    else:               # MR：先旋转后镜像（规范）
        r = math.radians(rot or 0)
        c, s = math.cos(r), math.sin(r)
        rx, ry = px * c - py * s, px * s + py * c
        if mirror:
            rx = -rx
    return cx + rx, cy + ry

stats = collections.Counter()
examples = []
for u, title, sch, dt in db.sheets():
    if dt != 1:
        continue
    sh = lr.parse_sheet(db, u)
    if not sh:
        continue
    # 导线端点集合
    recs = db.sheet_records(u)
    net_of, endp = {}, set()
    for a in recs:
        if not isinstance(a, list):
            continue
        if a[0] == "ATTR" and len(a) >= 5 and a[3] in ("NET", "Global Net Name"):
            net_of[a[2]] = a[4]
        elif a[0] == "WIRE" and len(a) >= 3:
            for seg in lr._norm_segs(a[2]):
                endp.add((round(seg[0], 1), round(seg[1], 1)))
                endp.add((round(seg[2], 1), round(seg[3], 1)))
    for c in sh["components"]:
        if not (c.get("mirror") and (c.get("rot") or 0) % 360):
            continue
        sym = lr.symbol_of(db, c)
        sp = db.symbol_pins(sym) if sym else None
        if not sp or not sp["pins"]:
            continue
        parts = sp["parts"]
        part = lr._match_part(c.get("title"), parts) if parts else None
        for pp in sp["pins"]:
            if pp.get("part") != part:
                continue
            hit_rm = pin_abs(pp["x"], pp["y"], c["x"], c["y"],
                             c["rot"], True, "RM") in endp
            hit_mr = pin_abs(pp["x"], pp["y"], c["x"], c["y"],
                             c["rot"], True, "MR") in endp
            stats[f"{c['designator']} RM={hit_rm} MR={hit_mr}"] += 1
            if len(examples) < 12:
                examples.append((title[:14], c["designator"], pp["name"],
                                 f'rot={c["rot"]}',
                                 f"RM={hit_rm}", f"MR={hit_mr}"))
print("统计:", dict(stats))
for e in examples:
    print(" ", e)
