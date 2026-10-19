"""V4 PCB 精确几何：把记录展开成每层铜的 Shapely 多边形。

与 render.py 的“审阅模式”区别：
  - 覆铜用 POURED 实铜缓存（含挖孔/热焊盘），并按 owner fineness 半宽描边；
  - 焊盘支持 RECT(圆角百分比)/OVAL/ELLIPSE/POLYGON + padOffset/relativeAngle；
  - 过孔/THT 孔挖除；走线按宽度 buffer；每层/每网络做布尔并集；
  - 圆弧路径按弦高容差采样（POURED 的 ARC 段）。

仍不是官方铺铜引擎：若 POURED 缓存缺失/落后于后续编辑，只能用 POUR 边框
回退并标记 approximate；不做 DRC/间距/热/制造签核。
"""
import json
import math
import weakref

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

MIL = 1.0  # 内部统一 mil
_EXACT_CACHE = weakref.WeakKeyDictionary()


def get_exact(design, arc_tol=0.05):
    """同一 PCBDesign 复用几何（多层渲染/面积统计时避免重复展开）。"""
    per = _EXACT_CACHE.get(design)
    if per is None:
        per = {}
        _EXACT_CACHE[design] = per
    key = round(float(arc_tol), 6)
    if key not in per:
        per[key] = ExactLayer(design, arc_tol)
    return per[key]


# --------------------------------------------------------------------- 路径
def parse_path(path, scale=1.0, arc_tol=0.05):
    """V4 路径 -> [(x,y)]。支持 L 折线与 ARC(angle,endX,endY)。

    ARC 的圆心有两个解；用“弧中点离多边形质心更远”选择外凸方向，适配
    圆角外框与挖孔圆角。arc_tol 为弦高容差（mil）。
    """
    if not path:
        return []
    if isinstance(path[0], list):
        path = path[0]
    pts = []
    i = 0
    if len(path) >= 2 and isinstance(path[0], (int, float)):
        pts.append((float(path[0]) * scale, float(path[1]) * scale))
        i = 2
    # 先收集命令（ARC 端点参与质心估计）
    seq = []
    while i < len(path):
        tok = path[i]
        if isinstance(tok, str):
            cmd = tok.upper()
            i += 1
            if cmd == "L":
                seg = []
                while i + 1 < len(path) and isinstance(path[i], (int, float)) \
                        and isinstance(path[i + 1], (int, float)):
                    seg.append((float(path[i]) * scale,
                                float(path[i + 1]) * scale))
                    i += 2
                seq.append(("L", seg))
            elif cmd == "ARC":
                if i + 2 < len(path):
                    ang = float(path[i])
                    ex = float(path[i + 1]) * scale
                    ey = float(path[i + 2]) * scale
                    i += 3
                    seq.append(("ARC", (ang, ex, ey)))
                else:
                    i = len(path)
            else:
                # 未知命令：保守跳过一个数值
                if i < len(path) and isinstance(path[i], (int, float)):
                    i += 1
        else:
            # 裸坐标 -> 折线点
            if i + 1 < len(path) and isinstance(path[i + 1], (int, float)):
                seq.append(("L", [(float(path[i]) * scale,
                                   float(path[i + 1]) * scale)]))
                i += 2
            else:
                i += 1
    # 质心（弧端点近似）
    est = list(pts)
    for kind, val in seq:
        if kind == "L":
            est.extend(val)
        else:
            est.append((val[1], val[2]))
    if est:
        cx = sum(p[0] for p in est) / len(est)
        cy = sum(p[1] for p in est) / len(est)
    else:
        cx = cy = 0.0
    for kind, val in seq:
        if kind == "L":
            pts.extend(val)
        else:
            ang, ex, ey = val
            start = pts[-1] if pts else (ex, ey)
            pts.extend(_arc_points(start, (ex, ey), ang, (cx, cy), arc_tol))
    return pts


def _arc_points(start, end, ang_deg, centroid, tol):
    sx, sy = start
    ex, ey = end
    chord = math.hypot(ex - sx, ey - sy)
    if chord < 1e-9:
        return [end]
    theta = math.radians(abs(ang_deg))
    if theta < 1e-6 or theta >= 2 * math.pi - 1e-6:
        return [end]
    half = chord / 2.0
    s = math.sin(theta / 2.0)
    if s <= 1e-12:
        return [end]
    r = half / s
    mx, my = (sx + ex) / 2.0, (sy + ey) / 2.0
    h2 = r * r - half * half
    h = math.sqrt(max(0.0, h2))
    ux, uy = (ex - sx) / chord, (ey - sy) / chord
    nx, ny = -uy, ux
    cands = []
    for sign in (1, -1):
        cx, cy = mx + sign * nx * h, my + sign * ny * h
        a0 = math.atan2(sy - cy, sx - cx)
        a1 = math.atan2(ey - cy, ex - cx)
        # 两个方向
        for direction in (1, -1):
            sweep = direction * theta
            # 对齐端点（允许 2π 差）
            delta = (a1 - a0) if direction == 1 else (a0 - a1)
            delta %= 2 * math.pi
            if abs(delta - theta) > 1e-3:
                continue
            mid = a0 + sweep / 2.0
            px = cx + r * math.cos(mid)
            py = cy + r * math.sin(mid)
            dist = math.hypot(px - centroid[0], py - centroid[1])
            cands.append((dist, cx, cy, a0, sweep, r))
    if not cands:
        return [end]
    _d, cx, cy, a0, sweep, r = max(cands, key=lambda x: x[0])
    n = max(2, min(128, int(math.ceil(abs(sweep) / max(1e-3,
                                                       2 * math.acos(
                                                           max(-1.0, 1 - tol / max(r, 1e-9))))))))
    return [(cx + r * math.cos(a0 + sweep * k / n),
             cy + r * math.sin(a0 + sweep * k / n)) for k in range(1, n + 1)]


# --------------------------------------------------------------------- 形状
def _poly_or_none(pts):
    if len(pts) < 3:
        return None
    try:
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return poly if not poly.is_empty else None
    except Exception:
        return None


def _pad_shape(p, dp, hole=False):
    """封装局部坐标下的焊盘/孔形状。"""
    typ = (dp or {}).get("padType")
    if typ == "POLYGON":
        pts = parse_path((dp or {}).get("path"), 1.0)
        return _poly_or_none(pts)
    w = float((dp or {}).get("width") or 0)
    h = float((dp or {}).get("height") or 0)
    if w <= 0 or h <= 0:
        return None
    if typ == "RECT":
        r = float((dp or {}).get("radius") or 0) / 100.0
        rr = min(w, h) * r
        g = box(-w / 2, -h / 2, w / 2, h / 2)
        if rr > 0:
            g = g.buffer(-rr, join_style="round").buffer(
                rr, join_style="round")
        return g
    if typ in ("OVAL", "SLOT"):
        if w >= h:
            core = LineString([(-(w - h) / 2, 0), ((w - h) / 2, 0)])
            return core.buffer(h / 2, cap_style="round")
        core = LineString([(0, -(h - w) / 2), (0, (h - w) / 2)])
        return core.buffer(w / 2, cap_style="round")
    if typ == "ELLIPSE":
        return affinity.scale(Point(0, 0).buffer(1, 64), w / 2, h / 2)
    # 未知/圆形兜底
    return Point(0, 0).buffer(max(w, h) / 2)


def pad_geometry(p, comp, layer, arc_tol=0.05):
    """焊盘在该层的铜（已含/已挖孔）；不匹配返回 None。"""
    p = p.get("raw", p)
    hole = p.get("hole") or {}
    hw = float(hole.get("width") or 0)
    hh = float(hole.get("height") or 0)
    tht = hw > 0 or hh > 0
    if not tht:
        if comp.get("layerId") == 1 and layer != 1:
            return None
        if comp.get("layerId") == 2 and layer != 2:
            return None
    dp = p.get("defaultPad") or {}
    typ = dp.get("padType")
    if typ == "POLYGON":
        local = _pad_shape(p, dp)
        if local is None:
            return None
    else:
        local = _pad_shape(p, dp)
        if local is None:
            return None
        ang = (p.get("padAngle") or 0) + (p.get("relativeAngle") or 0)
        if ang:
            local = affinity.rotate(local, ang, origin=(0, 0))
        local = affinity.translate(local,
                                   p.get("centerX") or 0,
                                   p.get("centerY") or 0)
        ox, oy = p.get("padOffsetX") or 0, p.get("padOffsetY") or 0
        if ox or oy:
            local = affinity.translate(local, ox, oy)
    # 组件变换：底面先镜像 Y，再旋转，再平移（热报告实测顺序）
    if comp.get("layerId") == 2:
        local = affinity.scale(local, xfact=1, yfact=-1, origin=(0, 0))
    ang = comp.get("angle") or 0
    if ang:
        local = affinity.rotate(local, ang, origin=(0, 0))
    local = affinity.translate(local, comp.get("x") or 0,
                               comp.get("y") or 0)
    # 孔
    if tht:
        hd = {"padType": "SLOT" if hole.get("holeType") == "SLOT" else "ROUND",
              "width": hw, "height": hh}
        if hd["padType"] == "ROUND":
            hg = Point(0, 0).buffer(max(hw, hh) / 2, 64)
        else:
            hg = _pad_shape(p, hd)
        if hg is not None:
            if ang:
                hg = affinity.rotate(hg, ang, origin=(0, 0))
            hg = affinity.translate(hg, p.get("centerX") or 0,
                                   p.get("centerY") or 0)
            ox, oy = p.get("padOffsetX") or 0, p.get("padOffsetY") or 0
            if ox or oy:
                hg = affinity.translate(hg, ox, oy)
            if comp.get("layerId") == 2:
                hg = affinity.scale(hg, xfact=1, yfact=-1, origin=(0, 0))
            cang = comp.get("angle") or 0
            if cang:
                hg = affinity.rotate(hg, cang, origin=(0, 0))
            hg = affinity.translate(hg, comp.get("x") or 0, comp.get("y") or 0)
            local = local.difference(hg)
    return local if not local.is_empty else None


# --------------------------------------------------------------------- 层
class ExactLayer:
    def __init__(self, design, arc_tol=0.05):
        self.d = design
        self.arc_tol = arc_tol
        self._poured = {}
        self._net_cache = {}
        self.warnings = []
        for h, b in design_records(design):
            if h.get("type") == "POURED":
                try:
                    key = json.loads(h.get("id") or "null")[1]
                except Exception:
                    continue
                self._poured[key] = b

    def _pour_geom(self, pour):
        """POUR -> (geom, exact)。POURED 缓存优先。"""
        pc = self._poured.get(pour.get("id"))
        if pc and pc.get("pourFill"):
            pos = []
            neg = []
            for entry in pc["pourFill"]:
                pts = parse_path(entry.get("path"), 10.0, self.arc_tol)
                g = _poly_or_none(pts)
                if g is None:
                    continue
                (pos if entry.get("fill") else neg).append(g)
            if pos:
                g = unary_union(pos)
                if neg:
                    g = g.difference(unary_union(neg))
                fin = float(((pour.get("pourType") or {}).get("fineness")) or 0)
                if fin > 0:
                    # 官方引擎按 fineness 半宽给外环/孔洞描边（圆角外扩）
                    g = g.buffer(fin / 2.0, join_style="round",
                                 resolution=16)
                return g, True
        pts = parse_path(pour.get("path"), 1.0, self.arc_tol)
        g = _poly_or_none(pts)
        if g is None:
            return None, False
        self.warnings.append("POUR 无实铜缓存，边框回退: %s"
                             % (pour.get("name") or pour.get("id")))
        return g, False

    def nets(self, layer):
        """{net: geom}；该层所有铜的并集/按网络（按层缓存）。"""
        if layer in self._net_cache:
            return self._net_cache[layer]
        d = self.d
        by_net = {}

        def add(net, geom):
            if geom is None or geom.is_empty:
                return
            by_net.setdefault(net, []).append(geom)

        for t in d.tracks:
            if t["layer"] != layer:
                continue
            if t["x1"] == t["x2"] and t["y1"] == t["y2"]:
                continue
            add(t["net"], LineString([(t["x1"], t["y1"]),
                                      (t["x2"], t["y2"])]).buffer(
                max(t["w"], 1) / 2.0, cap_style="round"))
        for v in d.vias:
            g = Point(v["x"], v["y"]).buffer(max(v["d"], 1) / 2.0, 64)
            hole = float(v.get("hole") or 0)
            if hole > 0:
                g = g.difference(Point(v["x"], v["y"]).buffer(hole / 2, 64))
            add(v["net"], g)
        for p in d.pads:
            comp = p.get("comp") or next(
                (c for c in d.components.values() if c.get("des") == p["des"]),
                None)
            if comp is None:
                continue
            raw = p.get("raw") or {}
            if raw.get("specialPad"):
                self.warnings.append("specialPad 未支持（按 defaultPad）: %s.%s"
                                     % (p.get("des"), p.get("num")))
            typ = ((raw.get("defaultPad") or {}).get("padType"))
            if typ not in (None, "RECT", "OVAL", "ELLIPSE", "POLYGON", "ROUND"):
                self.warnings.append("未知焊盘形状 %s: %s.%s"
                                     % (typ, p.get("des"), p.get("num")))
            g = pad_geometry(p, comp, layer, self.arc_tol)
            add(p["net"], g)
        for pour in d.pours:
            if pour["layer"] != layer:
                continue
            g, _exact = self._pour_geom(pour)
            add(pour["net"], g)
        for f in d.fills:
            if f["layer"] != layer:
                continue
            path = f["path"]
            if not path:
                continue
            if path and isinstance(path[0], str) and path[0] == "R" \
                    and len(path) >= 5:
                g = box(min(path[1], path[3]), min(path[2], path[4]),
                        max(path[1], path[3]), max(path[2], path[4]))
            else:
                if path and isinstance(path[0], str) and path[0] not in ("L",):
                    self.warnings.append("未知 FILL 路径 %r，已跳过"
                                         % (path[0],))
                    continue
                g = _poly_or_none(parse_path(path, 1.0, self.arc_tol))
            add(f["net"], g)
        out = {n: unary_union(v) for n, v in by_net.items()}
        self._net_cache[layer] = out
        return out

    def layer_geom(self, layer):
        return unary_union(list(self.nets(layer).values()))


def design_records(design):
    """取 PCB 文档原始记录（ExactLayer 用）。"""
    return list(design.records)


def layer_areas(design, arc_tol=0.05):
    """{layer: area_mm2}。"""
    ex = get_exact(design, arc_tol)
    out = {}
    for lid in design.copper_layers():
        g = ex.layer_geom(lid)
        out[lid] = g.area * (0.0254 ** 2)
    return out


def cache_status(design):
    """POURED 缓存新鲜度代理指标：缓存最大 ticket vs 最新铜编辑 ticket。

    只是“可能落后”的提示——LCEDA 的铺铜引擎才能重算；缓存旧于任何铜编辑
    时，几何精确到缓存快照，不等于当前设计。
    """
    copper_types = {"LINE", "VIA", "PAD_NET", "POUR", "FILL", "COMPONENT"}
    max_edit = 0
    for h, b in design_records(design):
        if h.get("type") in copper_types:
            max_edit = max(max_edit, h.get("ticket") or 0)
    cache_tickets = []
    for h, b in design_records(design):
        if h.get("type") == "POURED" and b.get("pourFill"):
            cache_tickets.append(h.get("ticket") or 0)
    return {
        "max_copper_ticket": max_edit,
        "max_cache_ticket": max(cache_tickets) if cache_tickets else 0,
        "cached_pours": len(cache_tickets),
        "cache_may_be_stale": bool(cache_tickets) and max(cache_tickets) < max_edit,
    }
