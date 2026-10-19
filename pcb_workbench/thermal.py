"""严格的板级 + 封装紧凑热模型（3D 分层有限体积 + 器件紧凑网络）。

这不是当前 `pdn.py` 里的 2D 等效热图。这里的目标是：

  - 板：按 `.epcb2` 的 `LAYER_PHYS` 实际叠层（铜厚/介质厚/材料）建 3D 分层
    有限体积节点，每层有独立的横向导热；层间有垂向导热；过孔作为铜柱
    并联到介质热阻上。
  - 器件：每个器件一个/两个封装节点，要求显式给出 `power_w` 和
    `theta_jb`（结到板）、`theta_jc`（结到壳）、`theta_ca`（壳到环境）
    或 `theta_ja`（结到环境）。没有数据就拒绝运行，不猜。
  - 边界：板上下表面对流 + 可选线性化辐射；板边对流；环境温度固定。
  - 输出：板 Top/Bottom 温度图、器件 Tj/Tc/板下温度表、能量平衡。

明确边界：封装是紧凑热阻网络（不是封装内部 3D 场）；板是分层 FVM，
铜层用 `POURED` 铜面积分数做等效横向导热；没有焊锡/TIM/连接器/风道。
缺少任何器件的功耗或热阻，工具只报错，不出图。
"""
import json
import math
import os
from dataclasses import dataclass

import numpy as np
from PIL import ImageDraw
from scipy import ndimage, sparse
from scipy.sparse.linalg import spsolve
from shapely import affinity
from shapely.geometry import box
from shapely.ops import unary_union

from .exact import get_exact
from . import pdn

MIL2MM = pdn.MIL2MM
K_CU = pdn.K_CU
K_DIELECTRIC_XY = 0.6      # FR4 面内，W/mK
K_DIELECTRIC_Z = 0.3       # FR4 法向
SIGMA_SB = 5.670374419e-8


class ThermalInputError(ValueError):
    pass


def _board_bbox(design):
    """板框 bbox（mm）；优先 BOARD_OUTLINE 的 R/L 路径。"""
    for o in design.outline:
        path = o.get("path") or []
        if path and path[0] == "R" and len(path) >= 5:
            x, y, w, h = [float(v) for v in path[1:5]]
            # EDA 的 R 高度沿 -Y 方向；用 min/max 兼容两种符号约定
            return (min(x, x + w), min(y, y - h),
                    max(x, x + w), max(y, y - h))
        nums = [float(v) for v in path if isinstance(v, (int, float))]
        if len(nums) >= 4:
            xs = nums[0::2]
            ys = nums[1::2]
            if xs and ys:
                return (min(xs), min(ys), max(xs), max(ys))
    bb = design.bbox()
    return (bb[0], bb[1], bb[2], bb[3])


def _grid(design, h_mm):
    xmin, ymin, xmax, ymax = _board_bbox(design)
    xmin *= MIL2MM
    xmax *= MIL2MM
    ymin *= MIL2MM
    ymax *= MIL2MM
    W = max(1, int(math.ceil((xmax - xmin) / h_mm)))
    H = max(1, int(math.ceil((ymax - ymin) / h_mm)))
    bbox = (xmin, ymin, xmin + W * h_mm, ymin + H * h_mm)
    mask = np.ones((H, W), bool)
    return bbox, mask


def _copper_frac(design, lid, bbox, h, sub=2):
    """铜面积分数：子栅格采样后按 h 单元平均，避免 0.5 mm 网格吞掉细走线。"""
    sub = max(1, int(round(sub)))
    hs = h / sub
    ex = get_exact(design)
    m = pdn._all_copper_mask(ex, lid, bbox, hs)
    H = int(math.ceil((bbox[3] - bbox[1]) / h))
    W = int(math.ceil((bbox[2] - bbox[0]) / h))
    if m is None:
        return np.zeros((H, W), float)
    Hs, Ws = H * sub, W * sub
    out = np.zeros((Hs, Ws), float)
    hh = min(Hs, m.shape[0])
    ww = min(Ws, m.shape[1])
    out[:hh, :ww] = m[:hh, :ww]
    return out.reshape(H, sub, W, sub).mean(axis=(1, 3))


def build_stack(design, spec, bbox, h):
    rows = design.stackup()
    if not rows:
        raise ThermalInputError("缺少 LAYER_PHYS 叠层记录；不能猜板厚/铜厚")
    st = spec.get("stackup") or {}
    cu_k = float(st.get("copper_k") or K_CU)
    dxy = float(st.get("dielectric_k_xy") or K_DIELECTRIC_XY)
    dz = float(st.get("dielectric_k_z") or K_DIELECTRIC_Z)
    sub = st.get("copper_subsample", 2)
    layers = []
    for r in rows:
        t_m = r["thickness_mil"] * MIL2MM * 1e-3
        if t_m <= 0:
            continue
        if r["is_copper"]:
            f = _copper_frac(design, r["layer_id"], bbox, h, sub)
            layers.append({
                "name": r["name"], "material": r["material"],
                "copper": True, "lid": r["layer_id"], "t": t_m,
                "kxy": f * cu_k + (1 - f) * dxy,
                "kz": f * cu_k + (1 - f) * dz,
                "frac": f,
            })
        else:
            layers.append({
                "name": r["name"], "material": r["material"],
                "copper": False, "lid": None, "t": t_m,
                "kxy": np.full((int(math.ceil((bbox[3] - bbox[1]) / h)),
                                int(math.ceil((bbox[2] - bbox[0]) / h))), dxy),
                "kz": np.full((int(math.ceil((bbox[3] - bbox[1]) / h)),
                               int(math.ceil((bbox[2] - bbox[0]) / h))), dz),
                "frac": None,
            })
    if not layers:
        raise ThermalInputError("叠层没有有效厚度")
    return layers


def _component_footprint(design, spec):
    comp = design.component(spec["designator"])
    if comp is None:
        raise ThermalInputError("找不到器件 %s" % spec["designator"])
    if spec.get("footprint_mm"):
        w, h = [float(x) for x in spec["footprint_mm"]]
        cx, cy = comp["x"] * MIL2MM, comp["y"] * MIL2MM
        x0, x1 = cx - w / 2, cx + w / 2
        y0, y1 = cy - h / 2, cy + h / 2
    else:
        pads = design.pads_of(spec["designator"])
        if not pads:
            raise ThermalInputError("器件 %s 没有焊盘，无法定封装 footprint"
                                    % spec["designator"])
        x0 = min(p["x"] for p in pads) * MIL2MM
        x1 = max(p["x"] for p in pads) * MIL2MM
        y0 = min(p["y"] for p in pads) * MIL2MM
        y1 = max(p["y"] for p in pads) * MIL2MM
        # 焊盘中心 bbox 只覆盖焊盘中心；按最大焊盘尺寸外扩
        wx = [p.get("w") or 0 for p in pads]
        hy = [p.get("h") or 0 for p in pads]
        if wx and hy:
            x0 -= max(wx) * MIL2MM / 2
            x1 += max(wx) * MIL2MM / 2
            y0 -= max(hy) * MIL2MM / 2
            y1 += max(hy) * MIL2MM / 2
    return comp, (x0, y0, x1, y1)


def _power_w(c):
    if c.get("power_w") is not None:
        return float(c["power_w"])
    if c.get("loss_model") == "i2r":
        i = c.get("current_a")
        r = c.get("resistance_ohm")
        if i is not None and r is not None:
            return float(i) ** 2 * float(r)
    raise ThermalInputError("%s 缺少 power_w 或可计算的 i2r 参数"
                            % c.get("designator"))


def validate(design, spec):
    errs = []
    if not spec.get("components"):
        errs.append("缺少 components（每个器件的 power/热阻不能猜）")
    for k in ("ambient_c", "grid_mm"):
        if spec.get(k) is None:
            errs.append("缺少 %s" % k)
    try:
        rows = design.stackup()
    except Exception as e:
        rows = []
        errs.append("叠层读取失败: %s" % e)
    if not rows:
        errs.append("缺少实际 LAYER_PHYS 叠层")
    if not design.outline:
        errs.append("缺少 BOARD_OUTLINE，热域不能猜")
    conv = spec.get("convection") or {}
    if conv.get("top_w_m2k") is None or conv.get("bottom_w_m2k") is None:
        errs.append("缺少 convection.top_w_m2k / bottom_w_m2k")
    for c in spec.get("components") or []:
        des = c.get("designator")
        if not des:
            errs.append("器件缺少 designator")
            continue
        if design.component(des) is None:
            errs.append("%s 不在 PCB 中" % des)
        p = c.get("power_w")
        if p is None:
            if c.get("loss_model") != "i2r":
                errs.append("%s 缺少有效 power_w（或 loss_model=i2r）" % des)
            else:
                if c.get("current_a") is None:
                    errs.append("%s loss_model=i2r 但缺 current_a" % des)
                if c.get("resistance_ohm") is None:
                    errs.append("%s loss_model=i2r 但缺 resistance_ohm" % des)
        else:
            try:
                pv = float(p)
            except (TypeError, ValueError):
                pv = -1
            if pv < 0:
                errs.append("%s power_w 无效" % des)
            elif pv > 20:
                errs.append("%s power_w=%s 异常大（>20W），请确认" % (des, p))
        model = c.get("model", "three_node")
        if model not in ("three_node", "two_node"):
            errs.append("%s model 必须是 three_node/two_node" % des)
        need = ["theta_jb"] if model == "three_node" else ["theta_jb", "theta_ja"]
        if model == "three_node":
            need += ["theta_jc", "theta_ca"]
        for key in need:
            v = c.get(key)
            if v is None or float(v) <= 0:
                errs.append("%s 缺少有效 %s（°C/W）" % (des, key))
        if not c.get("source"):
            errs.append("%s 缺少 source（数据来源/假设）" % des)
        elif str(c["source"]).strip().upper() in ("TBD", "TODO", "MISSING"):
            errs.append("%s 的 source 仍是占位符" % des)
        if not c.get("data_quality"):
            errs.append("%s 缺少 data_quality（datasheet/measured/estimate/test）" % des)
        elif str(c["data_quality"]).lower() in ("missing", "tbd", "todo"):
            errs.append("%s 的 data_quality 仍是 %s" % (des, c["data_quality"]))
    return errs


def solve(design, spec):
    errs = validate(design, spec)
    if errs:
        raise ThermalInputError("\n".join(" - " + e for e in errs))
    h = float(spec["grid_mm"])
    amb = float(spec["ambient_c"])
    bbox, mask = _grid(design, h)
    stack = build_stack(design, spec, bbox, h)
    H, W = mask.shape
    ys, xs = np.nonzero(mask)
    Nc = len(xs)
    cid = np.full((H, W), -1, np.int64)
    cid[ys, xs] = np.arange(Nc)
    NL = len(stack)
    Nboard = Nc * NL

    # 焊盘/封装
    comp_specs = spec["components"]
    comps = []
    for c in comp_specs:
        comp, (x0, y0, x1, y1) = _component_footprint(design, c)
        ix0 = int(math.floor((x0 - bbox[0]) / h))
        ix1 = int(math.ceil((x1 - bbox[0]) / h))
        iy1 = int(math.ceil((bbox[3] - y0) / h))
        iy0 = int(math.floor((bbox[3] - y1) / h))
        ix0, ix1 = max(0, ix0), min(W, ix1)
        iy0, iy1 = max(0, iy0), min(H, iy1)
        inside = mask[iy0:iy1, ix0:ix1]
        if not inside.any():
            raise ThermalInputError("%s 的封装 footprint 不在板内"
                                    % c["designator"])
        side = 0 if comp.get("layerId") != 2 else NL - 1
        cells = cid[iy0:iy1, ix0:ix1][inside]
        comps.append(dict(c, comp=comp, board_layer=side,
                          cells=cells.astype(np.int64)))
    ncomp = len(comps)
    node_count = 0
    for c in comps:
        c["tj"] = Nboard + node_count
        if c.get("model", "three_node") == "three_node":
            c["tc"] = c["tj"] + 1
            node_count += 2
        else:
            c["tc"] = None
            node_count += 1
    N = Nboard + node_count

    edges = []  # (i,j,G)

    def add(i, j, g):
        edges.append((i, j, g))

    # 横向
    for li, lay in enumerate(stack):
        kxy = lay["kxy"]
        t = lay["t"]
        for dy, dx in ((0, 1), (1, 0)):
            m = mask[:H-dy, :W-dx] & mask[dy:, dx:]
            if not m.any():
                continue
            a = cid[:H-dy, :W-dx][m]
            b = cid[dy:, dx:][m]
            ka = kxy[:H-dy, :W-dx][m]
            kb = kxy[dy:, dx:][m]
            g = 0.5 * (ka + kb) * t
            base = li * Nc
            for x, y, gg in zip(a, b, g):
                add(base + x, base + y, gg)

    # 垂向
    A = (h * 1e-3) ** 2
    for li in range(NL - 1):
        la, lb = stack[li], stack[li + 1]
        R = (la["t"] / (2 * la["kz"]) +
             lb["t"] / (2 * lb["kz"]))
        g = A / np.maximum(R, 1e-15)
        basea, baseb = li * Nc, (li + 1) * Nc
        for c in range(Nc):
            add(basea + c, baseb + c, float(g[ys[c], xs[c]]))

    # 过孔：铜柱并联到相邻铜层之间的介质
    cu_idx = [li for li, lay in enumerate(stack) if lay["copper"]]
    plate = float(spec.get("via_plating_um") or 25.0) * 1e-6
    for v in design.vias:
        d_m = float(v.get("d") or 0) * MIL2MM * 1e-3
        if d_m <= 0 or plate <= 0:
            continue
        cell = cid[int((bbox[3] - v["y"] * MIL2MM) / h),
                   int((v["x"] * MIL2MM - bbox[0]) / h)]
        if cell < 0:
            continue
        av = math.pi * d_m * plate
        for a, b in zip(cu_idx, cu_idx[1:]):
            t_d = sum(stack[k]["t"] for k in range(a + 1, b)
                      if not stack[k]["copper"])
            if t_d <= 0:
                continue
            add(a * Nc + cell, b * Nc + cell, K_CU * av / t_d)

    # 边界：上下对流 + 线性化辐射
    conv = spec["convection"]
    htop = float(conv.get("top_w_m2k") or 0)
    hbot = float(conv.get("bottom_w_m2k") or 0)
    hedge = float(conv.get("edge_w_m2k") or 0)
    eps = float(spec.get("radiation_emissivity") or 0)
    if eps > 0:
        tm = float(spec.get("radiation_t_mean_c") or 40) + 273.15
        ta = amb + 273.15
        hrad = eps * SIGMA_SB * (tm + ta) * (tm * tm + ta * ta)
        htop += hrad
        hbot += hrad
    A_cell = (h * 1e-3) ** 2
    boundary = []
    for li, lay in enumerate(stack):
        if li == 0:
            hc = htop
        elif li == NL - 1:
            hc = hbot
        else:
            hc = 0.0
        if hc > 0:
            for c in range(Nc):
                boundary.append((li * Nc + c, hc * A_cell))
    # 板边：每个边界单元、每层侧面
    if hedge > 0:
        er = ndimage.binary_erosion(mask)
        edge = mask & ~er
        for li, lay in enumerate(stack):
            gedge = hedge * lay["t"] * (h * 1e-3)
            for c in cid[edge]:
                boundary.append((li * Nc + int(c), gedge))

    # 器件紧凑网络
    rhs = np.zeros(N)
    diag_extra = np.zeros(N)
    ambient_edges = []
    for k, c in enumerate(comps):
        tj = c["tj"]
        tc = c["tc"]
        p = _power_w(c)
        rhs[tj] += p
        gjb = 1.0 / float(c["theta_jb"])
        for cell in c["cells"]:
            g = gjb / len(c["cells"])
            add(tj, c["board_layer"] * Nc + int(cell), g)
        if c.get("model", "three_node") == "three_node":
            gjc = 1.0 / float(c["theta_jc"])
            gca = 1.0 / float(c["theta_ca"])
            add(tj, tc, gjc)
            ambient_edges.append((tc, gca))
        else:
            gja = 1.0 / float(c["theta_ja"])
            ambient_edges.append((tj, gja))

    # 组装
    ri, ci, gd = [], [], []
    for i, j, g in edges:
        ri += [i, j, i, j]
        ci += [i, j, j, i]
        gd += [g, g, -g, -g]
    if ri:
        A = sparse.coo_matrix((gd, (ri, ci)), shape=(N, N)).tocsr()
    else:
        A = sparse.csr_matrix((N, N))
    A = A + sparse.diags(diag_extra, format="csr")
    for n, g in boundary:
        A[n, n] += g
        rhs[n] += g * amb
    for n, g in ambient_edges:
        A[n, n] += g
        rhs[n] += g * amb
    T = spsolve(A.tocsc(), rhs)
    if not np.all(np.isfinite(T)):
        raise RuntimeError("热求解结果非有限")

    # 能量平衡
    qin = sum(_power_w(c) for c in comps)
    qout = sum(g * (T[n] - amb) for n, g in boundary)
    qout += sum(g * (T[n] - amb) for n, g in ambient_edges)
    if qin > 0 and abs(qin - qout) / qin > 1e-5:
        raise RuntimeError("能量不平衡：in=%.6g out=%.6g" % (qin, qout))

    comp_rows = []
    for k, c in enumerate(comps):
        tj = T[c["tj"]]
        tc = T[c["tc"]] if c["tc"] is not None else None
        board_nodes = [c["board_layer"] * Nc + int(x) for x in c["cells"]]
        tb = float(np.mean(T[board_nodes]))
        comp_rows.append({
            "designator": c["designator"], "power_w": _power_w(c),
            "Tj_c": float(tj), "Tc_c": None if tc is None else float(tc),
            "Tboard_c": tb, "data_quality": c.get("data_quality"),
            "source": c.get("source"),
        })

    tlayers = []
    for li, lay in enumerate(stack):
        arr = np.full((H, W), np.nan)
        arr[ys, xs] = T[li * Nc: (li + 1) * Nc]
        tlayers.append(dict(layer=lay, T=arr))

    return {
        "T": T, "stack": stack, "masks": mask, "cid": cid, "bbox": bbox,
        "h": h, "ambient_c": amb, "components": comp_rows,
        "T_top": tlayers[0]["T"], "T_bottom": tlayers[-1]["T"],
        "T_layers": tlayers, "q_in_w": qin, "q_out_w": qout,
        "N": N, "Ncell": Nc, "Nlayer": NL,
    }


def run(design, spec, outdir):
    os.makedirs(outdir, exist_ok=True)
    res = solve(design, spec)
    files = []
    # 复用 pdn 的色图函数
    for tag, T in (("top", res["T_top"]), ("bottom", res["T_bottom"])):
        vmin = float(np.nanmin(T))
        vmax = float(np.nanmax(T))
        f = pdn._heatmap(T, res["masks"],
                         os.path.join(outdir, "thermal_%s.png" % tag),
                         "steady thermal %s" % tag,
                         "degC (ambient %.1f, min %.2f, max %.2f)"
                         % (res["ambient_c"], vmin, vmax))
        if f:
            files.append(f)
    rows = res["components"]
    with open(os.path.join(outdir, "thermal_components.json"), "w",
              encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    summary = {
        "ambient_c": res["ambient_c"],
        "grid_mm": res["h"],
        "layers": [{"name": x["name"], "thickness_mm": x["t"] * 1e3,
                    "copper": x["copper"]} for x in res["stack"]],
        "components": rows,
        "q_in_w": res["q_in_w"], "q_out_w": res["q_out_w"],
        "files": files,
    }
    with open(os.path.join(outdir, "thermal_summary.json"), "w",
              encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    return summary
