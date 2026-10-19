"""V4 PCB DFM 批处理检查（基于 exact.py 的每层/每网络铜几何）。

检查项（第一版）：
  - track: 走线宽度（记录值，精确）
  - neck:  覆铜窄颈/断裂（矢量腐蚀；检测铺铜热焊盘辐条、窄连接）
  - clearance: 同层不同网络铜间距（Shapely 距离）
  - annular: 过孔/THT 焊盘环宽（记录值）

边界：铺铜取 POURED 缓存（cache 落后时告警，结果只是快照）；neck 是腐蚀
拓扑近似，不识别平滑渐变颈缩；不做阻焊/丝印/孔到铜/板边间距/DRC/热。
"""
import math
from collections import Counter

from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from .exact import cache_status, get_exact

MIL2MM = 0.0254


def _pp(geom):
    if geom is None or geom.is_empty:
        return None
    p = geom.representative_point()
    return [round(p.x, 1), round(p.y, 1)]


def _components(geom):
    if geom is None or geom.is_empty:
        return 0
    if geom.geom_type == "MultiPolygon":
        return len(geom.geoms)
    if geom.geom_type == "Polygon":
        return 1
    return len(getattr(geom, "geoms", []))


def _neck_width(geom, upper_mil, min_mil=0.2):
    """腐蚀拓扑法：返回使连通分量数变化的最小宽度（mil）；无则 None。"""
    base = _components(geom)
    if base == 0:
        return None

    def changed(w):
        er = geom.buffer(-w / 2.0, join_style="round", resolution=8)
        return _components(er) != base

    if not changed(upper_mil):
        return None
    lo, hi = min_mil, upper_mil
    for _ in range(11):
        mid = (lo + hi) / 2.0
        if changed(mid):
            hi = mid
        else:
            lo = mid
    return hi


def check(design, min_track=0.20, min_neck=0.20, min_clearance=0.15,
          min_annular=0.10, layers=None, max_items=200):
    """执行 DFM 检查，返回 dict。长度单位 mm（内部 mil）。"""
    ex = get_exact(design)
    ids = list(layers) if layers else design.copper_layers()
    out = {"track": [], "neck": [], "clearance": [], "annular": [],
           "layers": ids, "cache": cache_status(design)}

    # 走线宽度
    for t in design.tracks:
        if t["layer"] not in ids:
            continue
        w_mm = (t["w"] or 0) * MIL2MM
        if w_mm < min_track:
            out["track"].append({
                "layer": t["layer"], "net": t["net"], "width_mm": round(w_mm, 4),
                "at": [round((t["x1"] + t["x2"]) / 2, 1),
                       round((t["y1"] + t["y2"]) / 2, 1)]})

    # 覆铜窄颈（只查有 POUR 的网络，避免对纯走线重复/误报）
    pour_nets = {(p["net"], p["layer"]) for p in design.pours
                 if p["layer"] in ids and p["net"]}
    upper = 3.0 / MIL2MM
    for lid in ids:
        nets = ex.nets(lid)
        for net, geom in nets.items():
            if (net, lid) not in pour_nets:
                continue
            w = _neck_width(geom, upper)
            if w is not None and w * MIL2MM < min_neck:
                out["neck"].append({
                    "layer": lid, "net": net,
                    "neck_mm": round(w * MIL2MM, 4),
                    "at": _pp(geom)})

    # 同层不同网络间距
    # 铺铜缓存落后时，pour 与后改走线/焊盘可能“假重叠”；严格间距只用
    # 走线/焊盘/过孔（缓存无关），并在结果中标注。
    use_pours = not out["cache"]["cache_may_be_stale"]
    out["clearance_scope"] = ("含铺铜" if use_pours
                              else "仅走线/焊盘/过孔（铺铜缓存落后）")
    thr = min_clearance / MIL2MM
    for lid in ids:
        items = [(n, g) for n, g in ex.nets(lid, include_pours=use_pours).items()
                 if g is not None and not g.is_empty]
        if len(items) < 2:
            continue
        tree = STRtree([g for _n, g in items])
        seen = set()
        for i, (n1, g1) in enumerate(items):
            if not n1:
                continue
            for j in tree.query(g1.buffer(thr)):
                if j <= i:
                    continue
                n2, g2 = items[j]
                if not n2:
                    continue
                key = (min(n1, n2), max(n1, n2))
                if key in seen:
                    continue
                seen.add(key)
                d = g1.distance(g2)
                if d >= thr:
                    continue
                pa, pb = nearest_points(g1, g2)
                out["clearance"].append({
                    "layer": lid, "net_a": n1, "net_b": n2,
                    "gap_mm": round(d * MIL2MM, 4),
                    "at": [[round(pa.x, 1), round(pa.y, 1)],
                           [round(pb.x, 1), round(pb.y, 1)]]})

    # 过孔 / THT 环宽
    for v in design.vias:
        hole = float(v.get("hole") or 0)
        if hole <= 0:
            continue
        ring = (float(v["d"]) - hole) / 2.0 * MIL2MM
        if ring < min_annular:
            out["annular"].append({
                "kind": "via", "layer": "all", "net": v["net"],
                "ring_mm": round(ring, 4),
                "at": [round(v["x"], 1), round(v["y"], 1)]})
    for p in design.pads:
        raw = p.get("raw") or {}
        hole = raw.get("hole") or {}
        hw, hh = float(hole.get("width") or 0), float(hole.get("height") or 0)
        if hw <= 0 and hh <= 0:
            continue
        # 机械孔/NPTH/无网络安装孔：环宽 0 是预期，不算 DFM 违规
        if not raw.get("plated") or not p.get("net"):
            continue
        dp = raw.get("defaultPad") or {}
        if (hole.get("holeType") or "ROUND") != "ROUND":
            continue
        w = float(dp.get("width") or 0)
        h = float(dp.get("height") or 0)
        if w <= 0 or h <= 0:
            continue
        ring = (min(w, h) - max(hw, hh)) / 2.0 * MIL2MM
        if ring < min_annular:
            out["annular"].append({
                "kind": "pad", "layer": "top" if p.get("comp", {}).get("layerId") == 1 else "bottom",
                "net": p["net"], "des": p["des"], "pad": p["num"],
                "ring_mm": round(ring, 4), "at": [round(p["x"], 1), round(p["y"], 1)]})

    # 汇总（先记总数，再截断明细）
    totals = {k: len(out[k]) for k in
              ("track", "neck", "clearance", "annular")}
    for k in ("track", "neck", "clearance", "annular"):
        out[k] = sorted(out[k], key=lambda x: x.get("width_mm") or
                        x.get("neck_mm") or x.get("gap_mm") or
                        x.get("ring_mm") or 0)[:max_items]
    out["summary"] = {
        "track": totals["track"],
        "neck": totals["neck"],
        "clearance": totals["clearance"],
        "annular": totals["annular"],
        "violations": sum(totals.values()),
        "returned": {k: len(out[k]) for k in totals},
    }
    return out
