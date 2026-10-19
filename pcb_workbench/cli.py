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
import sys

from .v4 import MIL2MM, load_epcb2, load_project
from .render import render_png


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
        print(json.dumps(pads, ensure_ascii=False, indent=1))
        return
    print("%s 焊盘 %d 个（mil）:" % (args.designator, len(pads)))
    for p in sorted(pads, key=lambda x: (len(x["num"]), x["num"])):
        print("  #%-3s %-7s net=%-16s at (%.1f, %.1f) %.1fx%.1f"
              % (p["num"], p["shape"], p["net"] or "-", p["x"], p["y"],
                 p["w"], p["h"]))


def cmd_render(args):
    d = pick(open_designs(args.input, args.pcb), args.pcb)
    if args.around:
        des, _, r = args.around.partition(",")
        pads = d.pads_of(des.strip())
        if not pads:
            raise SystemExit("找不到器件 %r 的焊盘" % des)
        cx = sum(p["x"] for p in pads) / len(pads)
        cy = sum(p["y"] for p in pads) / len(pads)
        r = float(r or 300)
        bbox = (cx - r, cy - r, cx + r, cy + r)
    elif args.region:
        vals = [float(v) for v in args.region.split(",")]
        if len(vals) != 4:
            raise SystemExit("--region 需要 x1,y1,x2,y2")
        bbox = tuple(vals)
    else:
        bbox = None
    layers = args.layers.split(",") if args.layers else None
    out = render_png(d, out=args.out, bbox=bbox, scale=args.scale,
                     layers=layers, round_caps=not args.no_round_caps,
                     supersample=args.supersample,
                     show_pours=not args.no_pours,
                     show_pads=not args.no_pads,
                     show_vias=not args.no_vias,
                     show_labels=not args.no_labels,
                     title=args.title or d.title)
    print("saved", out)


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
    rp.set_defaults(fn=cmd_render)

    args = ap.parse_args(argv)
    if hasattr(args, "input") and not args.input:
        ap.error("需要工程目录 / .eprj3 / .epcb2")
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
