"""V4 .epcb2 / .eprj3 PCB 源码读取（只读，mil，Y 向上）。

不依赖官方 lceda_pcb.py 的导出几何（该入口在本工程会因 MULTI 层矩形
挖孔报 UNSUPPORTED_MULTI_CUTOUT）。直接读 V4 源码里的：
  LINE(netName/layer/width) / VIA / POUR / FILL / PAD_NET(padNet) /
  COMPONENT + 内嵌 FOOTPRINT(PAD)。

边界：这是审阅用的候选几何，不是制造签核；焊盘只取 defaultPad，覆铜只取
POUR 路径，不处理圆弧（当前工程 PCB 无 ARC 铜）、挖孔与阻焊/丝印细节。
"""
import io
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

MIL2MM = 0.0254


def _read_logs(path):
    """{type,id,ticket}||{data}| 行日志 -> [doc...]。同 id 取 ticket 最大。"""
    docs = []
    cur = None
    for line in io.open(path, encoding="utf-8"):
        head, sep, body = line.rstrip("\n").partition("||")
        if not sep:
            continue
        try:
            h = json.loads(head)
        except ValueError:
            continue
        try:
            b = json.loads(body.rstrip("|") or "{}")
        except ValueError:
            b = {}
        t = h.get("type")
        if t == "DOCHEAD":
            cur = {"uuid": b.get("uuid"), "docType": b.get("docType"),
                   "records": [], "meta": {}, "canvas": {}}
            docs.append(cur)
            continue
        if cur is None:
            continue
        if t == "META":
            cur["meta"] = b
        elif t == "CANVAS":
            cur["canvas"] = b
        else:
            cur["records"].append((h, b))
    best = {}
    for doc in docs:
        best[doc["uuid"]] = doc
    return list(best.values())


def load_epcb2(path):
    """读单个 .epcb2，返回 PCBDesign。"""
    path = Path(path)
    docs = _read_logs(path)
    pcb = next((d for d in docs if d["docType"] == "PCB"), None)
    if pcb is None:
        raise ValueError(f"{path} 内没有 PCB 文档")
    return PCBDesign(path, docs, pcb)


def load_project(path, pcb=None):
    """读 .eprj3 工程目录（或索引文件），可选 --pcb 名字/文件。"""
    p = Path(path)
    root = p if p.is_dir() else p.parent
    files = sorted(root.glob("pcb/*.epcb2"))
    if not files:
        raise ValueError(f"{root} 下没有 pcb/*.epcb2")
    if pcb:
        hit = [f for f in files if f.stem == pcb or f.name == pcb]
        if not hit:
            raise ValueError("找不到 PCB: %s（候选: %s）"
                             % (pcb, ", ".join(f.stem for f in files)))
        files = hit
    out = []
    for f in files:
        try:
            out.append(load_epcb2(f))
        except ValueError:
            continue
    if not out:
        raise ValueError("无可用 PCB 文档")
    return out


class PCBDesign:
    def __init__(self, path, docs, doc):
        self.path = Path(path)
        self.root = self.path.parent.parent
        self.docs = docs
        self.doc = doc
        self.title = (doc["meta"] or {}).get("title") or self.path.stem
        self.layer_names = {}
        self.layers = {}
        for d in docs:
            for h, b in d["records"]:
                if h.get("type") == "LAYER" and b.get("use"):
                    self.layers[b.get("layerId")] = b.get("layerType")
                    self.layer_names[b.get("layerId")] = b.get("layerName")
        self.records = doc["records"]
        self._parse()

    # ------------------------------------------------------------------
    def _parse(self):
        attrs = [(h, b) for h, b in self.records if h.get("type") == "ATTR"]
        des_of = {a.get("parentId"): a.get("value") for _h, a in attrs
                  if a.get("key") == "Designator"}
        fp_of = {a.get("parentId"): a.get("value") for _h, a in attrs
                 if a.get("key") == "Footprint"}
        self.components = {}
        for h, b in self.records:
            if h.get("type") != "COMPONENT":
                continue
            cid = h.get("id")
            self.components[cid] = dict(b, cid=cid, des=des_of.get(cid),
                                        fp=fp_of.get(cid))

        pad_nets = {}
        for h, b in self.records:
            if h.get("type") == "PAD_NET":
                try:
                    arr = json.loads(h.get("id") or "null")
                except ValueError:
                    arr = None
                if isinstance(arr, list) and len(arr) >= 4 and b.get("padNet"):
                    pad_nets[(arr[1], str(arr[2]))] = b["padNet"]

        fp_pads = {}
        for c in self.components.values():
            fp = c.get("fp")
            if not fp or fp in fp_pads:
                continue
            doc = next((d for d in self.docs if d["uuid"] == fp), None)
            if doc:
                fp_pads[fp] = [b for h, b in doc["records"]
                               if h.get("type") == "PAD"]

        self.pads = []
        for cid, c in self.components.items():
            fp = c.get("fp")
            if not fp or fp not in fp_pads:
                continue
            bottom = c.get("layerId") == 2
            for p in fp_pads[fp]:
                lx, ly = p.get("centerX", 0), p.get("centerY", 0)
                if bottom:
                    ly = -ly
                gx, gy = _rot(lx, ly, c.get("angle", 0))
                dp = p.get("defaultPad") or {}
                self.pads.append({
                    "des": c.get("des"), "num": str(p.get("num")),
                    "x": gx + c.get("x", 0), "y": gy + c.get("y", 0),
                    "w": dp.get("width") or 0, "h": dp.get("height") or 0,
                    "shape": dp.get("padType"), "angle": c.get("angle", 0),
                    "net": pad_nets.get((cid, str(p.get("num"))), ""),
                    "comp": c, "raw": p})

        self.tracks = [{"net": b.get("netName", ""), "layer": b.get("layerId"),
                        "x1": b.get("startX"), "y1": b.get("startY"),
                        "x2": b.get("endX"), "y2": b.get("endY"),
                        "w": b.get("width") or 0}
                       for h, b in self.records if h.get("type") == "LINE"]
        self.vias = [{"net": b.get("netName", ""), "x": b.get("centerX"),
                      "y": b.get("centerY"), "d": b.get("viaDiameter") or 0,
                      "hole": b.get("holeDiameter") or 0}
                     for h, b in self.records if h.get("type") == "VIA"]
        self.pours = [{"id": h.get("id"), "name": b.get("name"),
                       "net": b.get("netName", ""), "layer": b.get("layerId"),
                       "pourType": b.get("pourType"),
                       "path": b.get("path"),
                       "pts": _poly_points(b.get("path"))}
                      for h, b in self.records if h.get("type") == "POUR"]
        self.fills = [{"net": b.get("netName", ""), "layer": b.get("layerId"),
                       "path": (b.get("path") or [[]])[0]}
                      for h, b in self.records if h.get("type") == "FILL"]
        self.outline = [b for h, b in self.records
                        if h.get("type") == "POLY"
                        and b.get("polyType") == "BOARD_OUTLINE"]

    # ------------------------------------------------------------------
    def copper_layers(self):
        """活动铜层（Top/Bottom/Inner），按层号排序。"""
        return sorted(lid for lid, typ in self.layers.items()
                      if typ in ("TOP", "BOTTOM", "SIGNAL"))

    def component(self, des):
        return next((c for c in self.components.values() if c.get("des") == des), None)

    def pads_of(self, des):
        return [p for p in self.pads if p["des"] == des]

    def bbox(self):
        xs, ys = [], []
        for t in self.tracks:
            xs += [t["x1"], t["x2"]]
            ys += [t["y1"], t["y2"]]
        for v in self.vias:
            xs.append(v["x"])
            ys.append(v["y"])
        for p in self.pads:
            xs.append(p["x"])
            ys.append(p["y"])
        return (min(xs), min(ys), max(xs), max(ys))

    def net_stats(self):
        stats = defaultdict(lambda: {"segments": 0, "length": 0.0,
                                     "wmin": 1e18, "wmax": 0.0,
                                     "layers": set(), "vias": 0})
        for t in self.tracks:
            s = stats[t["net"]]
            s["segments"] += 1
            s["length"] += math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
            s["wmin"] = min(s["wmin"], t["w"])
            s["wmax"] = max(s["wmax"], t["w"])
            s["layers"].add(t["layer"])
        for v in self.vias:
            stats[v["net"]]["vias"] += 1
        return stats

    def summary(self):
        bb = self.bbox()
        return {
            "title": self.title,
            "file": str(self.path),
            "bbox_mil": bb,
            "components": len(self.components),
            "pads": len(self.pads),
            "tracks": len(self.tracks),
            "vias": len(self.vias),
            "pours": len(self.pours),
            "copper_layers": [
                {"id": lid, "type": self.layers.get(lid),
                 "name": self.layer_names.get(lid)}
                for lid in self.copper_layers()],
            "nets": len({t["net"] for t in self.tracks} | {v["net"] for v in self.vias}),
        }


def _rot(x, y, deg):
    a = math.radians(deg)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def _poly_points(path):
    nums = []
    for seg in path or []:
        for t in seg:
            if isinstance(t, (int, float)):
                nums.append(float(t))
    return [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
