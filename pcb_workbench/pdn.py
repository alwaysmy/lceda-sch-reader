"""2.5D FDM PDN 电学求解 + 电压/电流密度热力图（基于 exact.py 实铜几何）。

  - 每层铜栅格化成电阻网络（4 邻域），电导 G = σ·t（S）；
  - 过孔按镀铜桶电阻连接相邻层（R = ρL/A，默认 25 µm 镀层）；
  - 源焊盘设为 Dirichlet 电压，汇焊盘注入总电流；
  - 解稀疏线性系统 A·V=b，得到电压场、边电流、电流密度、功率。

热模型已移到 `thermal.py`（3D 分层板 + 器件封装紧凑网络）；本文件不再
输出温度，避免把铜损温升误当成器件/整板温度。
"""
import json
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import sparse
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import spsolve

from .exact import get_exact, pad_geometry

MIL2MM = 0.0254
SIGMA_CU = 5.8e7          # S/m
RHO_CU = 1.0 / SIGMA_CU
K_CU = 385.0              # W/(m·K)
BG = (8, 8, 12)


# ------------------------------------------------------------------ 栅格
def _raster(geom, bbox, h_mm):
    xmin, ymin, xmax, ymax = bbox
    W = max(1, int(math.ceil((xmax - xmin) / h_mm)))
    H = max(1, int(math.ceil((ymax - ymin) / h_mm)))
    img = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(img)

    def xy(x, y):
        return ((x - xmin) / h_mm, (ymax - y) / h_mm)

    if geom is None or geom.is_empty:
        return np.zeros((H, W), bool)
    geoms = geom.geoms if hasattr(geom, "geoms") else [geom]
    for g in geoms:
        if g.geom_type != "Polygon":
            continue
        dr.polygon([xy(x, y) for x, y in g.exterior.coords], fill=1)
        for ring in g.interiors:
            dr.polygon([xy(x, y) for x, y in ring.coords], fill=0)
    return np.array(img, bool)


def _color(v):
    """0..1 -> 蓝-青-绿-黄-红。"""
    v = max(0.0, min(1.0, v))
    stops = [(0.0, (40, 40, 180)), (0.25, (0, 190, 220)),
             (0.5, (0, 200, 80)), (0.75, (255, 210, 0)),
             (1.0, (230, 40, 30))]
    for i in range(len(stops) - 1):
        a, ca = stops[i]
        b, cb = stops[i + 1]
        if a <= v <= b:
            t = (v - a) / (b - a)
            return tuple(int(ca[k] + (cb[k] - ca[k]) * t) for k in range(3))
    return stops[-1][1]


def _font(size):
    for p in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _pclip(vals, q=99.5):
    vals = vals[np.isfinite(vals)]
    if not len(vals):
        return None
    return float(np.percentile(vals, q))


def _heatmap(values, mask, out, title, unit, src=None, sink=None,
             vmin=None, vmax=None, bg_mask=None):
    """values: HxW float（仅 mask 内有效）。"""
    vals = values[mask]
    if vals.size == 0:
        return None
    if vmin is None:
        vmin = float(np.nanmin(vals))
    if vmax is None:
        vmax = float(np.nanmax(vals))
    if vmax <= vmin:
        vmax = vmin + 1e-12
    H, W = mask.shape
    img = Image.new("RGB", (W, H), BG)
    px = img.load()
    if bg_mask is not None:
        for y, x in np.argwhere(bg_mask):
            px[x, y] = (28, 28, 36)
    for y in range(H):
        for x in range(W):
            if not mask[y, x]:
                continue
            v = (values[y, x] - vmin) / (vmax - vmin)
            px[x, y] = _color(v)
    dr = ImageDraw.Draw(img)
    f = _font(14)
    for name, pos, col in (("SRC", src, (255, 255, 255)),
                           ("SINK", sink, (255, 255, 255))):
        if pos:
            x, y = pos
            dr.ellipse([x - 5, y - 5, x + 5, y + 5], outline=col, width=2)
            dr.text((x + 7, y - 8), name, fill=col, font=f)
    # 色标
    bx, by, bw, bh = W - 22, 24, 12, max(40, H - 90)
    for i in range(bh):
        c = _color(1 - i / max(1, bh - 1))
        dr.line([bx, by + i, bx + bw, by + i], fill=c)
    dr.text((bx - 54, by - 18), "%.4g" % vmax, fill=(255, 255, 255), font=f)
    dr.text((bx - 54, by + bh + 2), "%.4g" % vmin, fill=(255, 255, 255), font=f)
    dr.text((6, 6), title, fill=(255, 255, 255), font=f)
    dr.text((6, 24), unit, fill=(210, 210, 210), font=f)
    img.save(out)
    return out


# ------------------------------------------------------------------ 求解
def _mask_nodes(mask):
    ids = np.full(mask.shape, -1, np.int32)
    ids[mask] = np.arange(int(mask.sum()), dtype=np.int32)
    return ids


def _edge_arrays(ids, mask, G):
    """返回 (i,j) 数组，4 邻域。"""
    out = []
    # 水平
    m = mask[:, :-1] & mask[:, 1:]
    if m.any():
        ii = ids[:, :-1][m]
        jj = ids[:, 1:][m]
        out.append((ii, jj))
    m = mask[:-1, :] & mask[1:, :]
    if m.any():
        ii = ids[:-1, :][m]
        jj = ids[1:, :][m]
        out.append((ii, jj))
    return out


def _pad_cells(design, des, num, layers, bbox, h_mm, masks, ids):
    p = next((x for x in design.pads if x["des"] == des
              and x["num"] == str(num)), None)
    if p is None:
        raise ValueError("找不到焊盘 %s.%s" % (des, num))
    cells = {}
    for lid in layers:
        g = pad_geometry(p, p.get("comp"), lid)
        if g is None or g.is_empty:
            continue
        from shapely import affinity
        g_mm = affinity.scale(g, xfact=MIL2MM, yfact=MIL2MM, origin=(0, 0))
        m = _raster(g_mm, bbox, h_mm) & masks[lid]
        if m.any():
            cells[lid] = np.argwhere(m)
    if not cells:
        # 局部兜底：只允许焊盘附近 2mm 内的同网络铜，避免跨岛误连
        px = (p["x"] * MIL2MM - bbox[0]) / h_mm
        py = (bbox[3] - p["y"] * MIL2MM) / h_mm
        best = None
        for lid, m in masks.items():
            yy, xx = np.nonzero(m)
            if not len(xx):
                continue
            d2 = (xx - px) ** 2 + (yy - py) ** 2
            k = int(np.argmin(d2))
            dist_mm = math.sqrt(float(d2[k])) * h_mm
            if dist_mm <= 2.0 and (best is None or dist_mm < best[0]):
                best = (dist_mm, lid, int(yy[k]), int(xx[k]))
        if best is None:
            raise ValueError("焊盘不在所选铜层（或焊盘几何缺失）: %s.%s"
                             % (des, num))
        cells[best[1]] = np.array([[best[2], best[3]]])
    return p, cells


def solve_pdn(design, spec):
    layers = [int(x) for x in (spec.get("layers") or design.copper_layers())]
    net = spec["net"]
    h_mm = float(spec.get("grid_mm") or 0.1)
    cu_um = spec.get("copper_um") or {}
    stack_cu = {r["layer_id"]: r["thickness_mil"] * 25.4
                for r in design.stackup() if r["is_copper"]}
    t = {lid: float(cu_um.get(str(lid), stack_cu.get(
        lid, 35 if lid in (1, 2) else 15))) * 1e-3
         for lid in layers}  # mm

    ex = get_exact(design)
    geoms = {}
    for lid in layers:
        g = ex.nets(lid).get(net)
        if g is not None and not g.is_empty:
            geoms[lid] = g
    if not geoms:
        raise ValueError("所选层没有网络 %s 的铜" % net)

    # 统一 bbox（mm），留 0.5mm 余量
    xs, ys = [], []
    for g in geoms.values():
        b = g.bounds
        xs += [b[0] * MIL2MM, b[2] * MIL2MM]
        ys += [b[1] * MIL2MM, b[3] * MIL2MM]
    bbox = (min(xs) - 0.5, min(ys) - 0.5, max(xs) + 0.5, max(ys) + 0.5)

    masks, ids = {}, {}
    offset = 0
    for lid in layers:
        if lid not in geoms:
            continue
        # mil -> mm 几何
        from shapely import affinity
        g_mm = affinity.scale(geoms[lid], xfact=MIL2MM, yfact=MIL2MM,
                              origin=(0, 0))
        m = _raster(g_mm, bbox, h_mm)
        masks[lid] = m
        # 全层统一节点编号，避免各层从 0 开始相互覆盖
        arr = np.full(m.shape, -1, np.int32)
        n = int(m.sum())
        arr[m] = np.arange(offset, offset + n, dtype=np.int32)
        offset += n
        ids[lid] = arr
    if not masks:
        raise ValueError("栅格化失败")
    N = sum(int(m.sum()) for m in masks.values())

    # 焊盘
    src_pad, src_cells = _pad_cells(design, spec["source"]["designator"],
                                    spec["source"]["pad"], list(masks), bbox,
                                    h_mm, masks, ids)
    sinks = spec.get("sinks") or [spec["sink"]]
    sink_cells = []
    sink_pad = None
    for s in sinks:
        sp, cc = _pad_cells(design, s["designator"], s["pad"], list(masks),
                            bbox, h_mm, masks, ids)
        if sink_pad is None:
            sink_pad = sp
        for lid, arr in cc.items():
            sink_cells.append((lid, arr))
    if not sink_cells:
        raise ValueError("没有 sink 铜单元")
    if src_pad.get("net") != net:
        raise ValueError("source 焊盘网络不是 %s: %s.%s (%s)"
                         % (net, spec["source"]["designator"],
                            spec["source"]["pad"], src_pad.get("net")))
    for s in sinks:
        sp = next((p for p in design.pads if p["des"] == s["designator"]
                   and p["num"] == str(s["pad"])), None)
        if sp is not None and sp.get("net") != net:
            raise ValueError("sink 焊盘网络不是 %s: %s.%s (%s)"
                             % (net, s["designator"], s["pad"],
                                sp.get("net")))
    src_xy = ((src_pad["x"] * MIL2MM - bbox[0]) / h_mm,
              (bbox[3] - src_pad["y"] * MIL2MM) / h_mm)
    sink_xy = ((sink_pad["x"] * MIL2MM - bbox[0]) / h_mm,
               (bbox[3] - sink_pad["y"] * MIL2MM) / h_mm)

    fixed = np.zeros(N, bool)
    vfix = np.zeros(N)
    for lid, arr in src_cells.items():
        for y, x in arr:
            fixed[ids[lid][y, x]] = True
            vfix[ids[lid][y, x]] = float(spec["voltage"])
    total_i = float(spec["current"])
    sink_nodes = []
    for lid, arr in sink_cells:
        for y, x in arr:
            n = ids[lid][y, x]
            if n >= 0:
                sink_nodes.append(n)
    sink_nodes = np.array(sorted(set(sink_nodes)), dtype=np.int64)
    if not len(sink_nodes):
        raise ValueError("sink 未落在铜上")
    if fixed[sink_nodes].any():
        raise ValueError("source 与 sink 重叠")

    # 电阻边
    edges = []   # (i,j,G,layer)
    for lid, m in masks.items():
        G = SIGMA_CU * t[lid] * 1e-3  # S (t mm -> m)
        for ii, jj in _edge_arrays(ids[lid], m, G):
            edges.append((ii, jj, np.full(len(ii), G), lid))
    # 过孔（同网络）
    r_via = None
    board_mm = float(spec.get("board_mm") or 1.6)
    plate_m = 25e-6
    for v in design.vias:
        if v.get("net") != net:
            continue
        d_m = float(v.get("d") or 0) * MIL2MM * 1e-3
        if d_m <= 0:
            continue
        area = math.pi * d_m * plate_m
        rv = RHO_CU * board_mm * 1e-3 / max(area, 1e-15)
        cell = (int((v["x"] * MIL2MM - bbox[0]) / h_mm),
                int((bbox[3] - v["y"] * MIL2MM) / h_mm))
        x, y = cell
        avail = [lid for lid in masks if 0 <= y < masks[lid].shape[0]
                 and 0 <= x < masks[lid].shape[1] and masks[lid][y, x]]
        for a, b in zip(avail, avail[1:]):
            edges.append((np.array([ids[a][y, x]]),
                          np.array([ids[b][y, x]]),
                          np.array([1.0 / rv]), "via"))

    if not edges:
        raise ValueError("没有铜连接")
    ri = np.concatenate([e[0] for e in edges])
    ci = np.concatenate([e[1] for e in edges])
    gd = np.concatenate([e[2] for e in edges])

    # 连通分量：只保留同时含 source/sink 的分量，孤立铜岛不参与求解
    adj = sparse.coo_matrix((np.ones(len(ri)), (ri, ci)),
                            shape=(N, N)).tocsr()
    adj = adj + adj.T
    _ncomp, labels = connected_components(adj, directed=False)
    src_nodes = np.where(fixed)[0]
    comps_src = set(labels[src_nodes].tolist())
    comps_sink = set(labels[sink_nodes].tolist())
    common = comps_src & comps_sink
    if not common:
        raise ValueError(
            "source/sink 不连通：source 分量=%s，sink 分量=%s"
            "（检查铜岛/过孔连接或换 source/sink 焊盘）"
            % (sorted(comps_src), sorted(comps_sink)))
    comp = min(common)
    keep = labels == comp
    dropped = int((~keep).sum())
    new = np.full(N, -1, np.int64)
    new[keep] = np.arange(int(keep.sum()))
    em = (new[ri] >= 0) & (new[ci] >= 0)
    ri2, ci2, gd2 = new[ri][em], new[ci][em], gd[em]
    N2 = int(keep.sum())

    rows = np.concatenate([ri2, ci2, ri2, ci2])
    cols = np.concatenate([ri2, ci2, ci2, ri2])
    data = np.concatenate([gd2, gd2, -gd2, -gd2])
    A = sparse.coo_matrix((data, (rows, cols)), shape=(N2, N2)).tocsr()

    fixed2 = np.zeros(N2, bool)
    vfix2 = np.zeros(N2)
    for s in src_nodes:
        if keep[s]:
            fixed2[new[s]] = True
            vfix2[new[s]] = vfix[s]
    sink2 = new[sink_nodes]
    sink2 = sink2[sink2 >= 0]
    if not len(sink2):
        raise ValueError("sink 不在连通分量内")
    b = np.zeros(N2)
    # 负载电流从 sink 流出网络：注入电流为负
    b[sink2] -= total_i / len(sink2)
    free = ~fixed2
    Aff = A[free][:, free]
    bf = b[free] - A[free][:, fixed2] @ vfix2[fixed2]
    V2 = np.full(N2, np.nan)
    V2[fixed2] = vfix2[fixed2]
    V2[free] = spsolve(Aff.tocsc(), bf)
    if not np.all(np.isfinite(V2)):
        raise RuntimeError("求解结果非有限（网络可能不连通）")
    V = np.full(N, np.nan)
    V[keep] = V2

    # 电压/电流/功率图（沿用原始节点 ID；跳过被丢弃的岛）
    jmap = {}
    pmap = {}
    jmax = {}
    keep_masks = {}
    node_y = np.full(N, -1, np.int64)
    node_x = np.full(N, -1, np.int64)
    for lid, m in masks.items():
        yy, xx = np.nonzero(m)
        nn = ids[lid][yy, xx]
        node_y[nn] = yy
        node_x[nn] = xx
    for lid, m in masks.items():
        jc = np.zeros(m.shape)
        pc = np.zeros(m.shape)
        t_m = t[lid] * 1e-3
        for ii, jj, g, el in edges:
            if el != lid:
                continue
            vm = keep[ii] & keep[jj]
            if not np.any(vm):
                continue
            ii2, jj2, g2 = ii[vm], jj[vm], g[vm]
            I = g2 * (V[ii2] - V[jj2])
            J = np.abs(I) / (t_m * h_mm * 1e-3)  # A/m2
            ya, xa = node_y[ii2], node_x[ii2]
            yb, xb = node_y[jj2], node_x[jj2]
            np.maximum.at(jc, (ya, xa), J)
            np.maximum.at(jc, (yb, xb), J)
            np.add.at(pc, (ya, xa), (I * I / g2) / 2)
            np.add.at(pc, (yb, xb), (I * I / g2) / 2)
        jmap[lid] = jc / 1e6       # A/mm2
        pmap[lid] = pc             # W/cell
        jmax[lid] = float(np.nanmax(jc)) / 1e6
        km = np.zeros_like(m, bool)
        valid = ids[lid] >= 0
        km[valid] = keep[ids[lid][valid]]
        keep_masks[lid] = km

    sink_v = float(np.mean(V[sink_nodes[np.isfinite(V[sink_nodes])]]))
    # 过孔功率计入总功耗（电流密度图不显示过孔内部）
    via_power = 0.0
    for ii, jj, g, el in edges:
        if el != "via":
            continue
        vm = keep[ii] & keep[jj]
        if not np.any(vm):
            continue
        I = g[vm] * (V[ii[vm]] - V[jj[vm]])
        via_power += float(np.sum(I * I / g[vm]))
    total_power = (sum(float(np.sum(p)) for p in pmap.values())
                   + via_power)
    return {
        "V": V, "masks": keep_masks, "ids": ids, "bbox": bbox, "h": h_mm,
        "jmap": jmap, "pmap": pmap, "fixed": fixed, "vfix": vfix,
        "sink_nodes": sink_nodes, "edges": edges, "layers": layers,
        "copper_t": t, "board_mm": board_mm,
        "Vsrc": float(spec["voltage"]), "current": total_i, "net": net,
        "pad_src": spec["source"], "sinks": sinks,
        "src_xy": src_xy, "sink_xy": sink_xy,
        "vmin": float(np.nanmin(V)), "vmax": float(np.nanmax(V)),
        "sink_v": sink_v,
        "max_j": max(jmax.values()) if jmax else 0.0,
        "power_total": total_power,
        "dropped_nodes": dropped, "kept_nodes": N2,
    }


def _all_copper_mask(ex, lid, bbox, h_mm):
    from shapely import affinity
    from shapely.ops import unary_union
    geoms = [g for g in ex.nets(lid).values() if g is not None and not g.is_empty]
    if not geoms:
        return None
    g = unary_union(geoms)
    g_mm = affinity.scale(g, xfact=MIL2MM, yfact=MIL2MM, origin=(0, 0))
    return _raster(g_mm, bbox, h_mm)


def run(design, spec, outdir):
    import os
    os.makedirs(outdir, exist_ok=True)
    res = solve_pdn(design, spec)
    prefix = "pdn_%s" % spec["net"].replace("/", "_").replace("\\", "_")
    files = []
    ex = get_exact(design)
    bg = {}
    for lid in res["masks"]:
        try:
            bg[lid] = _all_copper_mask(ex, lid, res["bbox"], res["h"])
        except Exception:
            bg[lid] = None
    # 电压/电流逐层 + 电流合成
    vmin, vmax = res["vmin"], res["vmax"]
    all_j = None
    all_v = None
    for lid in res["masks"]:
        m = res["masks"][lid]
        v = np.full(m.shape, np.nan)
        for y, x in np.argwhere(m):
            n = res["ids"][lid][y, x]
            v[y, x] = res["V"][n]
        all_v = v if all_v is None else np.fmax(all_v, v)
        files.append(_heatmap(v, m, os.path.join(outdir, "%s_L%s_voltage.png"
                                                % (prefix, lid)),
                              "%s L%s voltage" % (res["net"], lid),
                              "V (min %.4f, max %.4f)" % (vmin, vmax),
                              src=res["src_xy"], sink=res["sink_xy"],
                              bg_mask=bg.get(lid)))
        j = res["jmap"][lid]
        jc = _pclip(j[m]) if m.any() else None
        files.append(_heatmap(j, m, os.path.join(outdir, "%s_L%s_current.png"
                                                % (prefix, lid)),
                              "%s L%s current density" % (res["net"], lid),
                              "A/mm2 (max %.4f%s)" % (
                                  float(np.max(j)),
                                  ", color clip %.3f" % jc if jc else ""),
                              src=res["src_xy"], sink=res["sink_xy"],
                              vmax=jc, bg_mask=bg.get(lid)))
        all_j = j if all_j is None else np.maximum(all_j, j)
    if all_j is not None:
        mask = np.zeros_like(all_j, bool)
        bg_all = np.zeros_like(all_j, bool)
        for lid, m in res["masks"].items():
            mask |= m
            if bg.get(lid) is not None:
                bg_all |= bg[lid]
        aj = _pclip(all_j[mask]) if mask.any() else None
        files.append(_heatmap(all_j, mask,
                              os.path.join(outdir, "%s_current_all.png" % prefix),
                              "%s current density (all layers)"
                              % res["net"],
                              "A/mm2 (max %.4f%s)" % (
                                  float(np.max(all_j)),
                                  ", color clip %.3f" % aj if aj else ""),
                              src=res["src_xy"], sink=res["sink_xy"],
                              vmax=aj, bg_mask=bg_all))
    if all_v is not None:
        mask = np.zeros_like(all_v, bool)
        bg_all = np.zeros_like(all_v, bool)
        for lid, m in res["masks"].items():
            mask |= m
            if bg.get(lid) is not None:
                bg_all |= bg[lid]
        files.append(_heatmap(all_v, mask,
                              os.path.join(outdir, "%s_voltage_all.png" % prefix),
                              "%s voltage (all layers, max)" % res["net"],
                              "V (min %.4f, max %.4f)" % (vmin, vmax),
                              src=res["src_xy"], sink=res["sink_xy"],
                              bg_mask=bg_all))
    summary = {k: res[k] for k in ("net", "Vsrc", "current", "sink_v",
                                   "vmin", "vmax", "max_j", "power_total",
                                   "bbox", "h", "kept_nodes", "dropped_nodes")}
    summary["ir_drop"] = res["Vsrc"] - res["sink_v"]
    summary["drop_mv"] = summary["ir_drop"] * 1000.0
    summary["r_ohm"] = summary["ir_drop"] / res["current"]
    summary["files"] = [f for f in files if f]
    with open(os.path.join(outdir, "%s_summary.json" % prefix), "w",
              encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    return summary


# ------------------------------------------------------------------ 解析校验
def analytic_trace_resistance(length_mm, width_mm, t_um=35):
    """R = ρL/(w·t)，用于网格收敛/求解器校验。"""
    return RHO_CU * (length_mm * 1e-3) / ((width_mm * 1e-3) *
                                          (t_um * 1e-6))
