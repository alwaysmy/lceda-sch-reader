"""意图式 PCB 渲染：按网络着色、按层过滤、圆头线帽/关节补全、2x 超采样。

设计意图（不是通用 EDA 截图）：
  - 颜色 = 网络，不是层：审阅关心"这个网络怎么走、和谁靠近"；
  - 层过滤：Top/Bottom/Inner 分开看，避免多层叠色造成误判；
  - 圆头线帽：逐段 LINE 渲染在 45°/T 型关节处会留缺口，用端点圆盘补全；
  - 2x 超采样后 LANCZOS 缩小，边缘平滑。

边界：焊盘取 defaultPad、覆铜取 POUR 路径；不处理圆弧铜/挖孔/丝印细节，
不能作为制造签核。
"""
import colorsys
import math
import os

from PIL import Image, ImageDraw, ImageFont

MIL2MM = 0.0254

# 已知网络固定配色（与 sch_review 的分析口径一致）
KNOWN = {
    "TEC_POS": (255, 127, 14),
    "TEC_NEG": (148, 103, 189),
    "+3V5_TEC": (214, 39, 40),
    "$6N7": (227, 119, 194),      # PVINS/PVINL
    "$6N30": (188, 189, 34),      # VDD
    "$6N1": (255, 215, 0),        # SW
    "$6N17": (31, 119, 180),      # VREF
    "$6N14": (23, 190, 207),
    "$6N15": (44, 160, 44),
    "$6N27": (140, 86, 75),
    "$6N26": (255, 187, 120),
    "$6N24": (174, 199, 232),
    "GND": (120, 120, 120),
    "PWR_SYNC_CLK_N": (0, 200, 255),
}
BG = (12, 12, 16)
_cache = {}


def net_color(net):
    if net in KNOWN:
        return KNOWN[net]
    if not net:
        return (110, 110, 110)
    if net in _cache:
        return _cache[net]
    h = (sum(ord(c) for c in net) * 0.61803398875) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, 0.55, 0.95)
    c = (int(r * 255), int(g * 255), int(b * 255))
    _cache[net] = c
    return c


def _blend(c, k=0.30):
    return tuple(int(c[i] * k + BG[i] * (1 - k)) for i in range(3))


def resolve_layers(design, layers):
    ids = design.copper_layers()
    if not layers or layers == ["all"]:
        return ids
    out = []
    for name in layers:
        n = str(name).lower()
        if n in ("all", "*"):
            return ids
        if n == "top":
            out += [i for i in ids if design.layers.get(i) == "TOP"]
        elif n in ("bottom", "bot"):
            out += [i for i in ids if design.layers.get(i) == "BOTTOM"]
        elif n.startswith("inner"):
            sig = [i for i in ids if design.layers.get(i) == "SIGNAL"]
            try:
                idx = int(n.replace("inner", "")) - 1
            except ValueError:
                idx = 0
            if 0 <= idx < len(sig):
                out.append(sig[idx])
        elif n.isdigit():
            out.append(int(n))
    return sorted(set(out))


def _font(size):
    for p in (r"C:\Windows\Fonts\consola.ttf",
              r"C:\Windows\Fonts\arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def render_png(design, out=None, bbox=None, scale=3.0, layers=None,
               round_caps=True, supersample=2, show_pours=True,
               show_pads=True, show_vias=True, show_labels=True,
               title=None):
    """渲染指定区域；out 为 None 时返回 PIL.Image。"""
    ids = resolve_layers(design, layers)
    if bbox is None:
        x0, y0, x1, y1 = design.bbox()
        mx, my = (x1 - x0) * 0.02, (y1 - y0) * 0.02
        bbox = (x0 - mx, y0 - my, x1 + mx, y1 + my)
    xmin, ymin, xmax, ymax = bbox
    ss = max(1, int(supersample))
    W = max(1, int((xmax - xmin) * scale * ss))
    H = max(1, int((ymax - ymin) * scale * ss))
    if W * H > 80_000_000:
        raise ValueError("渲染尺寸过大: %dx%d，请降低 scale 或缩小区域" % (W, H))
    img = Image.new("RGB", (W, H), BG)
    dr = ImageDraw.Draw(img)

    def px(x, y):
        return ((x - xmin) * scale * ss, (ymax - y) * scale * ss)

    # 覆铜（低透明度，作为背景）
    if show_pours:
        for p in design.pours:
            if p["layer"] not in ids or len(p["pts"]) < 3:
                continue
            dr.polygon([px(x, y) for x, y in p["pts"]],
                       fill=_blend(net_color(p["net"]), 0.22))
        for f in design.fills:
            path = f["path"]
            if f["layer"] not in ids or not path or path[0] != "R" or len(path) < 5:
                continue
            x1, y1, x2, y2 = path[1:5]
            p1, p2 = px(x1, y1), px(x2, y2)
            dr.rectangle([min(p1[0], p2[0]), min(p1[1], p2[1]),
                          max(p1[0], p2[0]), max(p1[1], p2[1])],
                         fill=_blend(net_color(f["net"]), 0.22))

    # 走线 + 圆头线帽（关节补全）
    for t in design.tracks:
        if t["layer"] not in ids:
            continue
        c = net_color(t["net"])
        w = max(1, int(round(t["w"] * scale * ss)))
        p1, p2 = px(t["x1"], t["y1"]), px(t["x2"], t["y2"])
        dr.line([p1, p2], fill=c, width=w)
        if round_caps and t["w"] > 0:
            r = w / 2.0
            for x, y in (p1, p2):
                dr.ellipse([x - r, y - r, x + r, y + r], fill=c)

    # 过孔
    if show_vias:
        for v in design.vias:
            r = max(1.2, v["d"] * scale * ss / 2)
            x, y = px(v["x"], v["y"])
            dr.ellipse([x - r, y - r, x + r, y + r],
                       fill=net_color(v["net"]), outline=(0, 0, 0))

    # 焊盘（仅在 Top/Bottom 视图显示）
    if show_pads:
        pad_layers = [i for i in ids
                      if design.layers.get(i) in ("TOP", "BOTTOM")]
        for p in design.pads:
            if not pad_layers:
                continue
            c = net_color(p["net"])
            w, h = p["w"], p["h"]
            x, y = px(p["x"], p["y"])
            if p["shape"] == "ROUND":
                r = max(1, w * scale * ss / 2)
                dr.ellipse([x - r, y - r, x + r, y + r],
                           fill=c, outline=(10, 10, 10))
                continue
            pts = []
            for cx, cy in ((-w / 2, -h / 2), (w / 2, -h / 2),
                           (w / 2, h / 2), (-w / 2, h / 2)):
                a = math.radians(p.get("angle") or 0)
                rx = cx * math.cos(a) - cy * math.sin(a)
                ry = cx * math.sin(a) + cy * math.cos(a)
                pts.append(px(p["x"] + rx, p["y"] + ry))
            dr.polygon(pts, fill=c, outline=(10, 10, 10))

    # 位号
    if show_labels:
        f = _font(max(12, int(18 * ss)))
        for c in design.components.values():
            des = c.get("des")
            x, y = c.get("x", 0), c.get("y", 0)
            if not des or not (xmin <= x <= xmax and ymin <= y <= ymax):
                continue
            tx, ty = px(x, y)
            dr.text((tx + 4 * ss, ty - 20 * ss), des,
                    fill=(255, 255, 255), font=f)

    # 图例 + 比例尺 + 标题
    f = _font(max(12, int(18 * ss)))
    nets = []
    for t in design.tracks:
        if t["layer"] in ids and t["net"] and t["net"] not in nets:
            nets.append(t["net"])
    for p in design.pours:
        if p["layer"] in ids and p["net"] and p["net"] not in nets:
            nets.append(p["net"])
    nodes = [n for n in nets if n in KNOWN][:10] + \
            [n for n in nets if n not in KNOWN][:6]
    lx, ly = 10 * ss, 10 * ss
    for n in nodes:
        dr.rectangle([lx, ly, lx + 14 * ss, ly + 14 * ss],
                     fill=net_color(n))
        dr.text((lx + 20 * ss, ly - 2 * ss), n,
                fill=(225, 225, 225), font=f)
        ly += 22 * ss
    bar = 100 * scale * ss
    dr.line([10 * ss, H - 18 * ss, 10 * ss + bar, H - 18 * ss],
            fill=(255, 255, 255), width=max(2, ss))
    dr.text((10 * ss, H - 44 * ss), "100 mil = 2.54 mm",
            fill=(255, 255, 255), font=f)
    if title:
        dr.text((10 * ss, 8 * ss), title, fill=(255, 255, 255), font=f)

    if ss > 1:
        img = img.resize((W // ss, H // ss), Image.LANCZOS)
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        img.save(out)
        return out
    return img
