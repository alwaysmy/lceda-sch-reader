"""回归：pcb_workbench 转角补全 + 真实 V4 PCB 冒烟。

1) 合成 45° 折线：butt 线帽在关节外侧会留缺口，round 线帽必须补上
   （像素级断言，防止退回"段段独立画线"）。
2) 真实 .epcb2（可选，默认 Fresnel 工程）：U601 pad1/pad2 同网络、
   走线/过孔/覆铜计数非零。

用法: python probes\\verify_pcb_workbench.py [.epcb2 路径]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from pcb_workbench.render import render_png  # noqa: E402
from pcb_workbench.v4 import load_epcb2  # noqa: E402

DEFAULT = (r"C:\Users\dell\Documents\LCEDA-Pro\projects"
           r"\Fresnel_V2.1_LaserDriver_EVM\pcb\PCB1.epcb2")
PATH = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LCEDA_PCB1", DEFAULT)

FAILS = []


def check(name, cond, detail=""):
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           ("  -- " + detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


class Dummy:
    layers = {1: "TOP"}
    layer_names = {1: "Top"}
    components = {}
    pads = []
    vias = []
    pours = []
    fills = []
    tracks = [
        {"net": "N", "layer": 1, "x1": 0, "y1": 0, "x2": 100, "y2": 0, "w": 20},
        {"net": "N", "layer": 1, "x1": 100, "y1": 0, "x2": 150, "y2": 50, "w": 20},
    ]

    def copper_layers(self):
        return [1]

    def bbox(self):
        return (-20, -40, 170, 80)


def pix(img, x, y, bbox, scale):
    xmin, ymin, xmax, ymax = bbox
    return img.getpixel((int((x - xmin) * scale), int((ymax - y) * scale)))


BB = (-20, -40, 170, 80)
S = 4.0
img_round = render_png(Dummy(), out=None, bbox=BB, scale=S, layers=["top"],
                       round_caps=True, supersample=1, show_pours=False,
                       show_pads=False, show_vias=False, show_labels=False)
img_butt = render_png(Dummy(), out=None, bbox=BB, scale=S, layers=["top"],
                      round_caps=False, supersample=1, show_pours=False,
                      show_pads=False, show_vias=False, show_labels=False)
# 45° 关节外侧缺口点：round 应在铜内，butt 应为背景
p_round = pix(img_round, 103, -6, BB, S)
p_butt = pix(img_butt, 103, -6, BB, S)
check("round 线帽填充 45° 关节缺口",
      p_round != (12, 12, 16), "px=%r" % (p_round,))
check("butt 线帽对照确实留缺口",
      p_butt == (12, 12, 16), "px=%r" % (p_butt,))

if os.path.isfile(PATH):
    d = load_epcb2(PATH)
    check("真实 PCB 解析：元件/走线/过孔/覆铜非零",
          len(d.components) > 100 and len(d.tracks) > 1000
          and len(d.vias) > 100 and len(d.pours) > 10,
          "comp=%d track=%d via=%d pour=%d"
          % (len(d.components), len(d.tracks), len(d.vias), len(d.pours)))
    pads = d.pads_of("U601")
    nets = {p["num"]: p["net"] for p in pads}
    check("U601 pad1/2 同网络（IN2N–OUT2）",
          nets.get("1") and nets.get("1") == nets.get("2"),
          "%r/%r" % (nets.get("1"), nets.get("2")))
    check("U601 pad20 无网络（TMPGD 悬空）", not nets.get("20"),
          repr(nets.get("20")))
else:
    print("  SKIP 真实 PCB（不存在: %s）" % PATH)

print()
print("ALL: %s" % ("PASS" if not FAILS else "FAIL(%d)" % len(FAILS)))
sys.exit(0 if not FAILS else 1)
