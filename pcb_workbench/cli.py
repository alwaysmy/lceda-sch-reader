"""PCB 工作台 CLI（只读）。

  python -m pcb_workbench stats  <工程目录|.eprj3|.epcb2> [--pcb PCB1] [--json]
  python -m pcb_workbench pads   <...> --designator U601 [--json]
  python -m pcb_workbench render <...> --around U601,350 --layers top \
         --scale 3 --out u601.png [--no-pours] [--no-round-caps]

工程目录 / .eprj3 会读取 pcb/*.epcb2；多个 PCB 时用 --pcb 指定标题。
坐标单位 mil（100 mil = 2.54 mm）。
"""
import argparse
import json
import os
import sys

from .v4 import MIL2MM, load_epcb2, load_project
from .render import render_png
from .exact import layer_areas, cache_status
from .dfm import check as dfm_check


def open_designs(path, pcb=None):
    p = str(path).lower()
    if p.endswith(".epcb2"):
        return [load_epcb2(path)]
    return load_project(path, pcb)


def pick(designs, pcb=None):
    if pcb:
        hit = [d for d in designs if d.title == pcb or d.path.stem == pcb]
        if hit:
            return hit[0]
        raise SystemExit("找不到 PCB %r；候选: %s"
                         % (pcb, ", ".join(d.title for d in designs)))
    if len(designs) > 1:
        raise SystemExit("工程含多个 PCB，请用 --pcb 指定: %s"
                         % ", ".join(d.title for d in designs))
    return designs[0]


def cmd_stats(args):
    d = pick(open_designs(args.input, args.pcb), args.pcb)
    if args.json:
        print(json.dumps(d.summary(), ensure_ascii=False, indent=1))
        return
    s = d.summary()
    print("PCB: %s  (%s)" % (s["title"], s["file"]))
    print("区域: x %.0f..%.0f  y %.0f..%.0f mil (%.1f x %.1f mm)"
          % (s["bbox_mil"][0], s["bbox_mil"][2], s["bbox_mil"][1],
             s["bbox_mil"][3],
             (s["bbox_mil"][2] - s["bbox_mil"][0]) * MIL2MM,
             (s["bbox_mil"][3] - s["bbox_mil"][1]) * MIL2MM))
    print("元件 %d / 焊盘 %d / 走线 %d / 过孔 %d / 覆铜 %d / 网络 %d"
          % (s["components"], s["pads"], s["tracks"], s["vias"],
             s["pours"], s["nets"]))
    print("铜层:", ", ".join("%s(%s)" % (l["name"], l["id"])
                             for l in s["copper_layers"]))
    if args.exact:
        areas = layer_areas(d, arc_tol=args.arc_tol)
        print("\n精确铜面积（POURED 实铜 + 全焊盘 + 孔挖除）:")
        for l in s["copper_layers"]:
            print("  L%-3s %-14s %9.3f mm2"
                  % (l["id"], l["name"], areas.get(l["id"], 0.0)))
        cs = cache_status(d)
        print("  铺铜缓存: %d 个；cache max ticket=%s，铜编辑 max ticket=%s%s"
              % (cs["cached_pours"], cs["max_cache_ticket"],
                 cs["max_copper_ticket"],
                 "  ⚠ 可能落后（建议在 LCEDA 重新覆铜）"
                 if cs["cache_may_be_stale"] else "  (不早于铜编辑)"))
    st = d.net_stats()
    rows = []
    for net, v in st.items():
        if not net:
            continue
        rows.append((v["length"], net, v))
    rows.sort(reverse=True)
    print("\n网络走线（按总长排序，mil / mm）:")
    for _l, net, v in rows[:args.top]:
        print("  %-16s seg=%4d len=%8.1f (%6.1f mm) w=%s..%s mil (%s..%s mm) vias=%d"
              % (net, v["segments"], v["length"], v["length"] * MIL2MM,
                 _num(v["wmin"]), _num(v["wmax"]),
                 _num(v["wmin"] * MIL2MM), _num(v["wmax"] * MIL2MM),
                 v["vias"]))


def cmd_pads(args):
    d = pick(open_designs(args.input, args.pcb), args.pcb)
    pads = d.pads_of(args.designator)
    if args.json:
        out = [{k: v for k, v in p.items() if k not in ("comp", "raw")}
               for p in pads]
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    print("%s 焊盘 %d 个（mil）:" % (args.designator, len(pads)))
    for p in sorted(pads, key=lambda x: (len(x["num"]), x["num"])):
        print("  #%-3s %-7s net=%-16s at (%.1f, %.1f) %.1fx%.1f"
              % (p["num"], p["shape"], p["net"] or "-", p["x"], p["y"],
                 p["w"], p["h"]))


def cmd_render(args):
    d = pick(open_designs(args.input, args.pcb), args.pcb)
    bbox = _bbox_from_args(d, args)
    layers = args.layers.split(",") if args.layers else None
    out = render_png(d, out=args.out, bbox=bbox, scale=args.scale,
                     layers=layers, round_caps=not args.no_round_caps,
                     supersample=args.supersample,
                     show_pours=not args.no_pours,
                     show_pads=not args.no_pads,
                     show_vias=not args.no_vias,
                     show_labels=not args.no_labels,
                     title=args.title or d.title,
                     exact=args.exact, arc_tol=args.arc_tol)
    print("saved", out)


def _bbox_from_args(d, args):
    if args.around:
        des, _, r = args.around.partition(",")
        pads = d.pads_of(des.strip())
        if not pads:
            raise SystemExit("找不到器件 %r 的焊盘" % des)
        cx = sum(p["x"] for p in pads) / len(pads)
        cy = sum(p["y"] for p in pads) / len(pads)
        r = float(r or 300)
        return (cx - r, cy - r, cx + r, cy + r)
    if args.region:
        vals = [float(v) for v in args.region.split(",")]
        if len(vals) != 4:
            raise SystemExit("--region 需要 x1,y1,x2,y2")
        return tuple(vals)
    return None


def cmd_layers(args):
    d = pick(open_designs(args.input, args.pcb), args.pcb)
    bbox = _bbox_from_args(d, args)
    os.makedirs(args.outdir, exist_ok=True)
    areas = layer_areas(d, arc_tol=args.arc_tol)
    cs = cache_status(d)
    if cs["cache_may_be_stale"]:
        print("警告: 铺铜缓存 max ticket=%s 早于铜编辑 max ticket=%s，"
              "几何是缓存快照，建议在 LCEDA 重新覆铜"
              % (cs["max_cache_ticket"], cs["max_copper_ticket"]))
    ids = d.copper_layers()
    for lid in ids:
        name = d.layer_names.get(lid) or ("L%s" % lid)
        out = os.path.join(args.outdir, "layer%s.png" % lid)
        render_png(d, out=out, bbox=bbox, scale=args.scale, layers=[lid],
                   exact=not args.approx, supersample=args.supersample,
                   title="%s / %s (L%s)" % (d.title, name, lid))
        print("layer %-3s %-14s area=%8.3f mm2 -> %s"
              % (lid, name, areas.get(lid, 0.0), out))
    out = os.path.join(args.outdir, "all_layers.png")
    render_png(d, out=out, bbox=bbox, scale=args.scale, layers=ids,
               exact=not args.approx, supersample=args.supersample,
               title="%s / all copper" % d.title)
    print("composite -> %s" % out)


def cmd_dfm(args):
    d = pick(open_designs(args.input, args.pcb), args.pcb)
    ids = None
    if args.layers:
        from .render import resolve_layers
        ids = resolve_layers(d, args.layers.split(","))
    res = dfm_check(d, min_track=args.min_track, min_neck=args.min_neck,
                    min_clearance=args.min_clearance,
                    min_annular=args.min_annular,
                    layers=ids, max_items=args.max_items)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return
    s = res["summary"]
    print("DFM: %s  (%s)" % (d.title, d.path.name))
    print("阈值: 走线 %.3f / 窄颈 %.3f / 同层间距 %.3f / 环宽 %.3f mm"
          % (args.min_track, args.min_neck, args.min_clearance,
             args.min_annular))
    print("结果: track=%d neck=%d clearance=%d annular=%d  (总 %d)"
          % (s["track"], s["neck"], s["clearance"], s["annular"],
             s["violations"]))
    cs = res["cache"]
    if cs["cache_may_be_stale"]:
        print("⚠ 铺铜缓存 ticket=%s 早于铜编辑 ticket=%s，结果基于缓存快照"
              % (cs["max_cache_ticket"], cs["max_copper_ticket"]))
    if res.get("clearance_scope"):
        print("间距口径: %s" % res["clearance_scope"])
    for key, label, field in (
            ("track", "走线宽度不足", "width_mm"),
            ("neck", "覆铜窄颈", "neck_mm"),
            ("clearance", "同层间距不足", "gap_mm"),
            ("annular", "环宽不足", "ring_mm")):
        rows = res[key]
        if not rows:
            continue
        print("\n[%s] %d 项%s" % (key, len(rows), "（前 %d）" % args.max_items
                                   if len(rows) >= args.max_items else ""))
        for r in rows[:args.max_items]:
            extra = " %s.%s" % (r.get("des"), r.get("pad")) if r.get("des") else ""
            if key == "clearance":
                what = "%s <-> %s" % (r.get("net_a") or "-",
                                      r.get("net_b") or "-")
            else:
                what = r.get("net") or "-"
            print("  L%-3s %-24s %-10s %8.4f mm at %s"
                  % (r.get("layer"), what, extra, r.get(field),
                     r.get("at")))


def cmd_pdn(args):
    d = pick(open_designs(args.input, args.pcb), args.pcb)
    from . import pdn as pdn_mod
    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    if args.grid:
        spec["grid_mm"] = args.grid
    # 热模型不再走 pdn 的 2D 等效图；改用 `thermal` 子命令（严格封装热模型）
    summary = pdn_mod.run(d, spec, args.outdir)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return
    print("PDN: %s  net=%s  %.3fV / %.3fA  grid=%.3fmm"
          % (d.title, summary["net"], summary["Vsrc"],
             summary["current"], summary["h"]))
    print("sink 电压 %.6f V  |  IR drop %.6f V (%.3f mV)"
          % (summary["sink_v"], summary["ir_drop"],
             summary["ir_drop"] * 1000))
    print("max |J| %.4f A/mm2  |  总功耗 %.4f W"
          % (summary["max_j"], summary["power_total"]))
    print("输出目录: %s" % args.outdir)
    for f in summary["files"]:
        print("  ", f)


def cmd_thermal(args):
    d = pick(open_designs(args.input, args.pcb), args.pcb)
    from . import thermal as thermal_mod
    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    if args.grid:
        spec["grid_mm"] = args.grid
    errs = thermal_mod.validate(d, spec)
    if errs:
        print("热模型输入不完整，拒绝运行：")
        for e in errs:
            print(" -", e)
        raise SystemExit(2)
    summary = thermal_mod.run(d, spec, args.outdir)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return
    print("Thermal: ambient %.1f C  grid %.3f mm  q=%.4f W"
          % (summary["ambient_c"], summary["grid_mm"],
             summary["q_in_w"]))
    for c in summary["components"]:
        print("  %-6s P=%.4g W  Tj=%.3f C  Tc=%s  Tboard=%.3f C"
              % (c["designator"], c["power_w"], c["Tj_c"],
                 "-" if c["Tc_c"] is None else "%.3f" % c["Tc_c"],
                 c["Tboard_c"]))
    print("输出目录: %s" % args.outdir)


def _num(v):
    return ("%.1f" % v).rstrip("0").rstrip(".")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pcb_workbench")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("stats", help="PCB 概要 + 网络走线统计")
    sp.add_argument("input")
    sp.add_argument("--pcb")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--top", type=int, default=15)
    sp.add_argument("--exact", action="store_true",
                    help="额外输出各铜层精确面积")
    sp.add_argument("--arc-tol", type=float, default=0.05)
    sp.set_defaults(fn=cmd_stats)

    pp = sub.add_parser("pads", help="按位号列出焊盘网络")
    pp.add_argument("input")
    pp.add_argument("--pcb")
    pp.add_argument("--designator", required=True)
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(fn=cmd_pads)

    rp = sub.add_parser("render", help="按网络着色的区域渲染")
    rp.add_argument("input")
    rp.add_argument("--pcb")
    rp.add_argument("--region", help="x1,y1,x2,y2（mil）")
    rp.add_argument("--around", help="位号,半径（mil），如 U601,350")
    rp.add_argument("--layers", help="top,bottom,inner1,inner2,all")
    rp.add_argument("--scale", type=float, default=3.0, help="px/mil")
    rp.add_argument("--supersample", type=int, default=2)
    rp.add_argument("--out", required=True)
    rp.add_argument("--title")
    rp.add_argument("--no-pours", action="store_true")
    rp.add_argument("--no-pads", action="store_true")
    rp.add_argument("--no-vias", action="store_true")
    rp.add_argument("--no-labels", action="store_true")
    rp.add_argument("--no-round-caps", action="store_true")
    rp.add_argument("--exact", action="store_true",
                    help="Shapely 布尔几何（POURED 实铜 + 全焊盘 + 孔挖除）")
    rp.add_argument("--arc-tol", type=float, default=0.05,
                    help="圆弧弦高容差（mil）")
    rp.set_defaults(fn=cmd_render)

    lp = sub.add_parser("layers", help="逐铜层渲染 + 面积统计")
    lp.add_argument("input")
    lp.add_argument("--pcb")
    lp.add_argument("--region", help="x1,y1,x2,y2（mil）")
    lp.add_argument("--around", help="位号,半径（mil），如 U601,350")
    lp.add_argument("--scale", type=float, default=2.0, help="px/mil")
    lp.add_argument("--supersample", type=int, default=2)
    lp.add_argument("--outdir", required=True)
    lp.add_argument("--approx", action="store_true",
                    help="用快速审阅模式而非精确几何")
    lp.add_argument("--arc-tol", type=float, default=0.05)
    lp.set_defaults(fn=cmd_layers)

    dp = sub.add_parser("dfm", help="批量 DFM 检查（走线/窄颈/间距/环宽）")
    dp.add_argument("input")
    dp.add_argument("--pcb")
    dp.add_argument("--min-track", type=float, default=0.20,
                    help="最小走线宽度 mm（默认 0.20）")
    dp.add_argument("--min-neck", type=float, default=0.20,
                    help="最小覆铜窄颈 mm（默认 0.20，腐蚀拓扑法）")
    dp.add_argument("--min-clearance", type=float, default=0.15,
                    help="同层不同网络最小间距 mm（默认 0.15）")
    dp.add_argument("--min-annular", type=float, default=0.10,
                    help="过孔/THT 最小环宽 mm（默认 0.10）")
    dp.add_argument("--layers", help="top,bottom,inner1,inner2（默认全部铜层）")
    dp.add_argument("--max-items", type=int, default=100)
    dp.add_argument("--json", action="store_true")
    dp.set_defaults(fn=cmd_dfm)

    pp = sub.add_parser("pdn", help="2.5D FDM PDN（仅电压/电流密度）")
    pp.add_argument("input")
    pp.add_argument("--pcb")
    pp.add_argument("--spec", required=True,
                    help="JSON：net/voltage/current/source/sinks/...")
    pp.add_argument("--outdir", required=True)
    pp.add_argument("--grid", type=float, help="覆盖 spec.grid_mm（mm）")
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(fn=cmd_pdn)

    tp = sub.add_parser("thermal",
                        help="3D 分层板 + 封装紧凑热模型（严格输入）")
    tp.add_argument("input")
    tp.add_argument("--pcb")
    tp.add_argument("--spec", required=True,
                    help="JSON：ambient/convection/components(power+θ)/...")
    tp.add_argument("--outdir", required=True)
    tp.add_argument("--grid", type=float, help="覆盖 spec.grid_mm（mm）")
    tp.add_argument("--json", action="store_true")
    tp.set_defaults(fn=cmd_thermal)

    args = ap.parse_args(argv)
    if hasattr(args, "input") and not args.input:
        ap.error("需要工程目录 / .eprj3 / .epcb2")
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
