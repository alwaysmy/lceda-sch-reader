#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lceda_reader.py — 立创EDA专业版 (.eprj2) 原理图读取工具（通用格式工具）

针对立创EDA专业版工程格式（.eprj2 SQLite + 内置 NDJSON 文档流）的只读解析器，
不绑定特定工程/器件/网络名，可读取任何该格式的工程。仅依赖 Python 标准库。

文件格式（与官方规范一致，见 6_tools/lceda_sch_reader/reference/ 与
https://image.lceda.cn/files/lceda-pro-file-format-v3_2025.10.21.md）：
  .eprj2  = SQLite 数据库（非 zip）。表: schematics / documents / components /
            devices / attributes 等。
  documents.docType: 1=原理图页, 3=PCB 页。
  documents.dataStr = "base64" 前缀 + base64( gzip( NDJSON ) )：
      - 解码后为 NDJSON，每行一个 JSON 数组（旧版数组式记录），如
          ["DOCTYPE","SCH","1.1"]
          ["COMPONENT", id, title, x, y, rot, mirror, {}, flags]
          ["ATTR", attr_uuid, comp_id, attr_name, value, ...]
          ["WIRE", id, [[x1,y1,x2,y2],...], style, flags]
      - 网络连接：ATTR 记录 name="NET"/"Global Net Name" 挂在 WIRE 上，
        值即网络名（官方约定：导线必须带 NET 属性）。
      - 符号/引脚真源：components 表的 dataStr（DOCTYPE=SYMBOL），PIN 记录
        含相对坐标，ATTR NAME/NUMBER 给出引脚名/号。
  坐标单位：0.01 inch（官方约定，旋转角为角度制）。
  uuid 命名空间（两个表互斥，交集为 0）：
      Symbol uuid -> components 表（符号定义，含 PIN 引脚表）
      Device  uuid -> devices 表（器件型号/封装/描述，值真源）
      Device->Symbol 桥接：attributes 表 key='Symbol'

用法示例：
  python lceda_reader.py list
  python lceda_reader.py boards
  python lceda_reader.py components ["页名"]
  python lceda_reader.py nets "页名"
  python lceda_reader.py pins "页名"
  python lceda_reader.py netlist
  python lceda_reader.py trace U1 [--no-power] [--depth N]
  python lceda_reader.py find U1
  python lceda_reader.py search 器件型号
  python lceda_reader.py bom [--board 板名]
  python lceda_reader.py datasheets
  python lceda_reader.py attrs "页名"
  python lceda_reader.py devmap
  python lceda_reader.py raw "页名" [-o out.ndjson]
  python lceda_reader.py --json [--eprj PATH] <命令>
"""

import argparse
import base64
import gzip
import json
import math
import os
import re
import sqlite3
import sys
import zipfile
from pathlib import Path


# ---------------------------------------------------------------- 基础层

def out(s=""):
    print(s)


def outj(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def find_eprj(path=None):
    """定位工程文件（通用，不绑定任何工程目录结构）：
    1) 显式 --eprj 优先；
    2) 否则搜索当前工作目录及其父目录的 *.eprj2，再退化为 *.epro。"""
    import glob
    if path:
        return path
    bases = [os.getcwd()]
    d = bases[0]
    while True:
        parent = os.path.dirname(d)
        if parent == d:
            break
        bases.append(parent)
        d = parent
    for pattern in ("*.eprj2", "*.epro"):
        for base in bases:
            hits = glob.glob(os.path.join(base, pattern))
            if hits:
                return hits[0]
    return None


def natkey(s):
    s = s or ""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


class LcedaDB:
    def __init__(self, path):
        self.conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self.cur = self.conn.cursor()
        self._text_cache = {}

    def schematics(self):
        return list(self.cur.execute(
            "SELECT uuid, name, display_name FROM schematics"))

    def schem_map(self):
        return {r[0]: (r[1], r[2]) for r in self.schematics()}

    def sheets(self, doc_type=1):
        return list(self.cur.execute(
            "SELECT uuid, display_title, schematic_uuid, docType FROM documents"))

    @staticmethod
    def decompress(ds):
        if not ds:
            return ""
        s = ds[6:] if isinstance(ds, str) and ds.startswith("base64") else ds
        try:
            data = base64.b64decode(s)
        except Exception:
            return ""
        try:
            return gzip.decompress(data).decode("utf-8")
        except Exception:
            return data.decode("utf-8", errors="replace")

    def sheet_text(self, title, doc_type=1):
        key = (doc_type, title)
        if key in self._text_cache:
            return self._text_cache[key]
        row = self.cur.execute(
            "SELECT dataStr FROM documents WHERE docType=? AND display_title=?",
            (doc_type, title)).fetchone()
        text = self.decompress(row[0]) if row else None
        self._text_cache[key] = text
        return text

    def sheet_records(self, title, doc_type=1):
        key = (doc_type, title, "recs")
        if key in self._text_cache:
            return self._text_cache[key]
        text = self.sheet_text(title, doc_type)
        if text is None:
            return None
        arrs = []
        for ln in text.splitlines():
            try:
                arrs.append(json.loads(ln))
            except Exception:
                continue
        self._text_cache[key] = arrs
        return arrs

    def device_map(self):
        """uuid -> (title, display_title, description)
        Symbol uuid -> components 表；Device uuid -> devices 表（两表互斥）。"""
        m = {}
        for r in self.cur.execute(
                "SELECT uuid, title, display_title, description FROM devices"):
            m[r[0]] = (r[1], r[2] or "", r[3] or "")
        for r in self.cur.execute(
                "SELECT uuid, title, display_title, description FROM components"):
            if r[0] not in m:
                m[r[0]] = (r[1], r[2] or "", r[3] or "")
        return m

    def device_attrs(self, device_uuid):
        """attributes 表 -> {key: value}（Datasheet/Manufacturer/Symbol 等）。
        key='Symbol' 的值是 device_uuid -> symbol_uuid 的桥。"""
        return {k: v for k, v in self.cur.execute(
            "SELECT key, value FROM attributes WHERE device_uuid=?",
            (device_uuid,)) if v}

    def symbol_of_device(self, device_uuid):
        """通过 attributes 表把 Device uuid 桥接到 Symbol uuid。"""
        r = self.cur.execute(
            "SELECT value FROM attributes WHERE device_uuid=? AND key='Symbol'",
            (device_uuid,)).fetchone()
        return r[0] if r else None

    def symbol_pins(self, symbol_uuid):
        """components.dataStr（SYMBOL 定义）-> 引脚表
        [{id, name, number, x, y, rot, part}]（坐标为符号相对坐标）。"""
        row = self.cur.execute(
            "SELECT dataStr FROM components WHERE uuid=?", (symbol_uuid,)
        ).fetchone()
        if not row:
            return None
        text = self.decompress(row[0])
        pins = {}
        names, numbers = {}, {}
        pin_types = {}
        bbox = None
        cur_part = None
        symbol_type = None
        for ln in text.splitlines():
            try:
                a = json.loads(ln)
            except Exception:
                continue
            if not isinstance(a, list) or len(a) < 2:
                continue
            if a[0] == "HEAD" and len(a) > 1 and isinstance(a[1], dict):
                symbol_type = a[1].get("symbolType")
            elif a[0] == "PART" and len(a) > 2 and isinstance(a[2], dict):
                cur_part = a[1]
                b = a[2].get("BBOX")
                if b and len(b) == 4:
                    # BBOX 顺序 [xmin, y1, xmax, y2]，y 可能倒序
                    bbox = [min(b[0], b[2]), min(b[1], b[3]),
                            max(b[0], b[2]), max(b[1], b[3])]
            elif a[0] == "PIN" and len(a) >= 8:
                pins[a[1]] = {"id": a[1], "x": a[4], "y": a[5],
                              "rot": a[7] if a[7] is not None else 0,
                              "part": cur_part,
                              "name": None, "number": None,
                              "pin_type": None}
            elif a[0] == "ATTR" and len(a) >= 5 and a[2] in pins:
                if a[3] == "NAME":
                    names[a[2]] = a[4]
                elif a[3] == "NUMBER":
                    numbers[a[2]] = str(a[4])
                elif a[3] == "Pin Type":
                    pin_types[a[2]] = a[4]
        for pid, p in pins.items():
            p["name"] = names.get(pid)
            p["number"] = numbers.get(pid)
            p["pin_type"] = pin_types.get(pid)
        return {"pins": list(pins.values()), "bbox": bbox, "parts": sorted(
            {p["part"] for p in pins.values()}),
            "symbol_type": symbol_type}


class EproDB:
    """Minimal LCEDA ``.epro`` (ZIP export) backend.

    Implements the same duck-typed interface as :class:`LcedaDB` so the CLI
    commands (list/boards/components/nets/pinmap/pins/netfind/trace/...) can
    transparently read a ZIP export as well as the SQLite ``.eprj2`` format.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path)
        self.obj = json.loads(self.zip.read("project.json"))
        self.devices = self.obj.get("devices", {})
        self.symbols = self.obj.get("symbols", {})
        self.boards = self.obj.get("boards", {})
        self.schematics = self.obj.get("schematics", {})
        self._names = set(self.zip.namelist())
        self._page_index = {}      # unique_title -> (schematic uuid, page id)
        self._records_cache = {}
        self._symbol_pin_cache = {}
        self._build_page_index()

    def _build_page_index(self):
        for board_name, board in self.boards.items():
            sch_uuid = board.get("schematic")
            if not sch_uuid:
                continue
            sch = self.schematics.get(sch_uuid, {})
            for page in sch.get("sheets", []):
                page_name = page.get("display_title") or page.get("name") or str(page.get("id"))
                self._page_index[f"{board_name}::{page_name}"] = (sch_uuid, int(page["id"]))
        # CBB module schematics are also reachable through their own namespace.
        for sch_uuid, sch in self.schematics.items():
            sch_name = sch.get("name", sch_uuid)
            for page in sch.get("sheets", []):
                page_name = page.get("display_title") or page.get("name") or str(page.get("id"))
                self._page_index[f"CBBMOD::{sch_name}::{page_name}"] = (sch_uuid, int(page["id"]))

    def decompress(self, ds):
        return ds

    # -- lceda_reader-compatible API ----------------------------------------
    def schematics(self):
        return [(name, name, name) for name in self.boards]

    def schem_map(self):
        return {name: (name, name) for name in self.boards}

    def sheets(self, doc_type=1):
        rows = []
        for board_name, board in self.boards.items():
            sch_uuid = board.get("schematic")
            sch = self.schematics.get(sch_uuid, {})
            for page in sch.get("sheets", []):
                title = f"{board_name}::{page.get('display_title') or page.get('name') or page['id']}"
                rows.append((page.get("uuid"), title, board_name, 1))
        return rows

    def sheet_records(self, title, doc_type=1):
        if title in self._records_cache:
            return self._records_cache[title]
        key = self._page_index.get(title)
        if key is None:
            return None
        sch_uuid, page_id = key
        fname = f"SHEET/{sch_uuid}/{page_id}.esch"
        if fname not in self._names:
            return None
        text = self.zip.read(fname).decode("utf-8", errors="replace")
        records = []
        for line in text.splitlines():
            try:
                records.append(json.loads(line))
            except Exception:
                continue
        self._records_cache[title] = records
        return records

    def device_map(self):
        out = {}
        for uuid, dev in self.devices.items():
            if not isinstance(dev, dict):
                continue
            attrs = dev.get("attributes") or {}
            out[uuid] = (dev.get("title") or "",
                         attrs.get("Supplier Part") or "",
                         attrs.get("Description") or dev.get("description") or "")
        for uuid, sym in self.symbols.items():
            if not isinstance(sym, dict) or uuid in out:
                continue
            out[uuid] = (sym.get("title") or "", "", "")
        return out

    def device_attrs(self, device_uuid):
        dev = self.devices.get(device_uuid)
        if isinstance(dev, dict):
            return dict(dev.get("attributes") or {})
        return {}

    def symbol_of_device(self, device_uuid):
        if not device_uuid:
            return None
        dev = self.devices.get(device_uuid)
        if isinstance(dev, dict) and isinstance(dev.get("attributes"), dict):
            return dev["attributes"].get("Symbol")
        return None

    def symbol_pins(self, symbol_uuid):
        """Parse SYMBOL/<uuid>.esym into lceda_reader's dict shape.

        ``HEAD.originX/Y`` is the symbol-local origin; instance coordinates are
        origin-relative, so pin coordinates subtract it.
        """
        if not symbol_uuid:
            return None
        if symbol_uuid in self._symbol_pin_cache:
            return self._symbol_pin_cache[symbol_uuid]
        fname = f"SYMBOL/{symbol_uuid}.esym"
        if fname not in self._names:
            return None
        text = self.zip.read(fname).decode("utf-8", errors="replace")
        pins, names, numbers, pin_types = {}, {}, {}, {}
        bbox = None
        cur_part = None
        symbol_type = None
        origin_x = origin_y = 0.0
        for line in text.splitlines():
            try:
                a = json.loads(line)
            except Exception:
                continue
            if not isinstance(a, list) or len(a) < 2:
                continue
            if a[0] == "HEAD" and len(a) > 1 and isinstance(a[1], dict):
                symbol_type = a[1].get("symbolType")
                origin_x = float(a[1].get("originX", 0) or 0)
                origin_y = float(a[1].get("originY", 0) or 0)
            elif a[0] == "PART" and len(a) > 2 and isinstance(a[2], dict):
                cur_part = a[1]
                b = a[2].get("BBOX")
                if b and len(b) == 4:
                    bbox = [min(b[0], b[2]), min(b[1], b[3]),
                            max(b[0], b[2]), max(b[1], b[3])]
            elif a[0] == "PIN" and len(a) >= 8:
                pins[a[1]] = {"id": a[1], "x": (a[4] or 0) - origin_x,
                              "y": (a[5] or 0) - origin_y,
                              "rot": a[7] if a[7] is not None else 0,
                              "part": cur_part, "name": None,
                              "number": None, "pin_type": None}
            elif a[0] == "ATTR" and len(a) >= 5 and a[2] in pins:
                if a[3] == "NAME":
                    names[a[2]] = a[4]
                elif a[3] == "NUMBER":
                    numbers[a[2]] = str(a[4])
                elif a[3] == "Pin Type":
                    pin_types[a[2]] = a[4]
        for pid, p in pins.items():
            p["name"] = names.get(pid)
            p["number"] = numbers.get(pid)
            p["pin_type"] = pin_types.get(pid)
        result = {"pins": list(pins.values()), "bbox": bbox,
                  "parts": sorted({p["part"] for p in pins.values()}),
                  "symbol_type": symbol_type}
        self._symbol_pin_cache[symbol_uuid] = result
        return result


# ---------------------------------------------------------------- 解析层

def parse_sheet(db, title):
    """把一张原理图页解析为结构化 dict。"""
    recs = db.sheet_records(title)
    if recs is None:
        return None
    sheet = {"title": title, "components": [], "nets": [], "attrs": {}}
    comps = {}      # cid -> component dict
    net_of = {}     # wire/comp id -> net name
    wires = []      # (net, segs)
    for a in recs:
        if not isinstance(a, list) or len(a) < 2:
            continue
        kind = a[0]
        if kind == "COMPONENT":
            cid = a[1]
            comps[cid] = {"cid": cid,
                          "title": a[2] if len(a) > 2 else "",
                          "x": a[3] if len(a) > 3 else 0,
                          "y": a[4] if len(a) > 4 else 0,
                          "rot": a[5] if len(a) > 5 else 0,
                          "mirror": a[6] if len(a) > 6 else 0,
                          "attrs": {}}
        elif kind == "ATTR" and len(a) >= 5:
            cid, name, val = a[2], a[3], a[4]
            if cid in comps:
                comps[cid]["attrs"][name] = val
            if name in ("NET", "Global Net Name"):
                net_of[cid] = val
        elif kind == "WIRE" and len(a) >= 3:
            wires.append((a[1], a[2]))
    for c in comps.values():
        a = c["attrs"]
        if a.get("Designator") is not None:
            c["designator"] = a["Designator"]
        else:
            c["designator"] = None
        c["symbol_uuid"] = a.get("Symbol")
        c["device_uuid"] = a.get("Device")
        c["net"] = net_of.get(c["cid"]) or a.get("Name")
        # 保留有 Symbol/Device 的实例（含 short 短接符/netport 等无 title 的）
        if c["title"] or c["designator"] or c["symbol_uuid"] or c["device_uuid"]:
            sheet["components"].append(c)
    # stub 网络：NET 挂在 WIRE 上；无名 wire 保留为 net=None stub
    for wid, segs in wires:
        net = net_of.get(wid) or None
        pts = set()
        for s_ in segs:
            pts.add((s_[0], s_[1]))
            pts.add((s_[2], s_[3]))
        sheet["nets"].append({"net": net, "points": sorted(pts)})
    # 页标题块
    for c in comps.values():
        if c["cid"] == "e1":
            sheet["attrs"] = c["attrs"]
    return sheet



def symbol_of(db, c):
    """取元件符号 uuid：优先 Symbol 属性，其次 Device->attributes 桥接。"""
    if c.get("symbol_uuid"):
        return c["symbol_uuid"]
    if c.get("device_uuid"):
        return db.symbol_of_device(c["device_uuid"])
    return None



def parse_value(description):
    """把器件描述解析为结构化字段。
    格式1: "10KΩ (1002) ±1%" / "12pF (120) ±5% 50V"
    格式2: "容值:12pF;精度:±5%;额定电压:50V;材质(温度系数):C0G;"
    """
    if not description:
        return {}
    r = {}
    if ";" in description and ":" in description:
        for kv in description.split(";"):
            kv = kv.strip()
            if ":" in kv:
                k, v = kv.split(":", 1)
                r[k.strip()] = v.strip()
    else:
        m = re.search(r"([\d.]+(?:[kKMGmΩuµnpfF]?)Ω?)", description)
        if m:
            r["value"] = m.group(1)
        m = re.search(r"\((\w+)\)", description)
        if m:
            r["code"] = m.group(1)
        m = re.search(r"±([\d.]+)%", description)
        if m:
            r["tolerance"] = f"±{m.group(1)}%"
        m = re.search(r"(\d+(?:\.\d+)?)(V|uF|nF|pF|mF)", description)
        if m:
            r[m.group(2).upper()] = f"{m.group(1)}{m.group(2)}"
    return r


# ---------------------------------------------------------------- 输出层

def _fmt_comp(c, dev, with_value=True):
    d = dev.get(c.get("symbol_uuid") or c.get("device_uuid") or "",
                ("", "", ""))
    row = {
        "designator": c.get("designator"),
        "title": c["title"],
        "symbol_uuid": c.get("symbol_uuid"),
        "device_uuid": c.get("device_uuid"),
    }
    if with_value:
        row.update({
            "device": d[1],
            "description": d[2],
            "value": parse_value(d[2]),
        })
    return row


# ---------------------------------------------------------------- 命令

def cmd_list(db, args):
    sn = db.schem_map()
    if args.json:
        return outj([{"uuid": u, "name": n, "display": d}
                     for u, n, d in db.schematics()])
    out("== SCHEMATICS（板） ==")
    for uuid, name, disp in db.schematics():
        out(f"  {disp:12s} ({name})")
    out("\n== SHEETS（页） ==")
    for uuid, title, sch, dt in db.sheets():
        if dt != 1:
            continue
        d, n = sn.get(sch, ("?", "?"))
        out(f"  [sch={d:12s}] {title}")
    out("\n== 非原理图文档 ==")
    for uuid, title, sch, dt in db.sheets():
        if dt == 1:
            continue
        out(f"  [docType={dt}] {title}")


def cmd_boards(db, args):
    sn = db.schem_map()
    rows = []
    for uuid, title, sch, dt in db.sheets():
        if dt != 1:
            continue
        sheet = parse_sheet(db, title)
        if sheet is None:
            continue
        info = {}
        for k in ("@Board Name", "@Schematic Name", "@Page Name", "Version",
                  "Description", "@Page No"):
            if k in sheet["attrs"] and sheet["attrs"][k]:
                info[k] = sheet["attrs"][k]
        d, n = sn.get(sch, ("?", "?"))
        rows.append({"sheet": title, "schematic": d, "attrs": info})
        if not args.json:
            out(f"[{d:12s}] {title:16s} {json.dumps(info, ensure_ascii=False)}")
    if args.json:
        outj(rows)


def cmd_components(db, args):
    sn = db.schem_map()
    dev = db.device_map()
    rows = []
    for uuid, st, sch, dt in db.sheets():
        if dt != 1:
            continue
        if args.sheet and st != args.sheet:
            continue
        sheet = parse_sheet(db, st)
        if sheet is None:
            continue
        d, n = sn.get(sch, ("?", "?"))
        if not args.json:
            out(f"## {st} (sch={d})")
        for c in sorted(sheet["components"], key=lambda c: natkey(c.get("designator") or "")):
            if not c.get("designator"):
                continue
            fr = _fmt_comp(c, dev)
            if args.json:
                rows.append({"sheet": st, "schematic": d, **fr})
            else:
                sym = fr["symbol_uuid"] or fr["device_uuid"] or ""
                drec = dev.get(sym, ("", "", ""))
                out(f"{fr['designator']}\t{fr['title']}\t{drec[0]}\t{drec[1]}\t{drec[2]}")
    if args.json:
        outj(rows)


def resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp):
    """基于走线连通域的网络名解析。

    规则（修订版）：
      1) 同 WIRE 记录端点相接 = 同一连通域（物理网络）
      2) 0Ω 跳线 / SHORT 短接符 = 两脚连通域合并（脚本可识别的物理直连）
      3) 其他两脚无源器件（电阻/磁珠/LED...）**不自动合并**：每个引脚保留
         自己所在域的名字，器件本身保留为中间 hop，交给人/LLM 判断
      4) 芯片多引脚不参与"另一脚取网络"
    返回 ``{(designator, pin_key): net}``；重名引脚使用 ``name#number``。
    注意：comp_pins 键为 (des, cid) 时先按 des 合并（连通域只看坐标）。"""
    if comp_pins and not isinstance(next(iter(comp_pins)), str):
        merged = {}
        for (des, cid), plist in comp_pins.items():
            merged.setdefault(des, []).extend(plist)
        comp_pins = merged

    def pin_key(p):
        return p.get("key") or p.get("pin")
    # 并查集
    parent = {}
    # 立创EDA 格式保证引脚端点与 WIRE 端点精确重合（0.01 inch 网格）；
    # 坐标统一归一化消除浮点尾差（如 455.00000000000006），容差 2 作最后防御。
    def norm_pt(p):
        return (round(p[0], 1), round(p[1], 1))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # 1) WIRE 记录内部端点相接 => 连通域（归一化后 union，避免尾差断链）
    wire_pts = {}   # wire_id -> set(points)
    for wid, segs in wires:
        pts = set()
        for s_ in segs:
            if isinstance(s_, list) and len(s_) >= 4 and \
                    all(isinstance(v, (int, float)) for v in s_):
                pts.add(norm_pt((s_[0], s_[1])))
                pts.add(norm_pt((s_[2], s_[3])))
        if not pts:
            continue
        wire_pts[wid] = pts
        for p in pts:
            parent.setdefault(p, p)
        first = next(iter(pts))
        for p in pts:
            union(p, first)

    # 2) 引脚命中点并入连通域

    pin_hit = {}   # (des,pin) -> [命中端点...]（重名引脚(如 VDD×5)各保留命中点，不互相覆盖）
    endp_net = {}
    for n in sheet["nets"]:
        if n["net"]:
            for px, py in n["points"]:
                endp_net.setdefault(norm_pt((px, py)), n["net"])
    for des, plist in comp_pins.items():
        for p in plist:
            for (px, py), nm in endp_net.items():
                if abs(p["x"] - px) <= 2 and abs(p["y"] - py) <= 2:
                    pin_hit.setdefault((des, pin_key(p)), []).append((px, py))
                    parent.setdefault((px, py), (px, py))
                    break
    # 引脚未直接命中命名端点时，与最近 wire 端点相连（容差2，归一化后）
    all_wpts = set()
    for pts in wire_pts.values():
        for pt in pts:
            all_wpts.add(norm_pt(pt))
    for des, plist in comp_pins.items():
        for p in plist:
            key = (des, pin_key(p))
            if key in pin_hit:
                continue
            best = None
            for (wx, wy) in all_wpts:
                d2 = (p["x"] - wx) ** 2 + (p["y"] - wy) ** 2
                if d2 <= 4 and (best is None or d2 < best[0]):
                    best = (d2, (wx, wy))
            if best:
                pin_hit.setdefault(key, []).append(best[1])
                parent.setdefault(best[1], best[1])

    # 3) 0Ω 跳线 + Short Symbol(短接符 symbolType=22) 两脚物理直连合并
    jumpers = set()
    for c in sheet["components"]:
        if c.get("title") and "0000" in c["title"]:
            jumpers.add(c["designator"])
    for des in jumpers:
        plist = comp_pins.get(des, [])
        if len(plist) == 2:
            k0 = (des, pin_key(plist[0]))
            k1 = (des, pin_key(plist[1]))
            if k0 in pin_hit and k1 in pin_hit:
                union(pin_hit[k0][0], pin_hit[k1][0])
    # Short Symbol（无 title 的合成 SHORT 实例，sym_type=22）：两脚同网络
    for key, plist in list(comp_pins.items()):
        des = key if isinstance(key, str) else key[0]
        if len(plist) == 2 and any(p.get("sym_type") == 22 for p in plist):
            k0 = (des, pin_key(plist[0]))
            k1 = (des, pin_key(plist[1]))
            if k0 in pin_hit and k1 in pin_hit:
                union(pin_hit[k0][0], pin_hit[k1][0])

    # 4) 连通域 -> 域内引脚 + 已知网络名
    domain_of_pt = {}
    for p in parent:
        domain_of_pt[p] = find(p)
    dom_nets = {}   # domain -> set(net)
    for (des, pin), pts in pin_hit.items():
        for pt in pts:
            d = domain_of_pt[pt]
            nm = endp_net.get(pt)
            if nm:
                dom_nets.setdefault(d, set()).add(nm)
    # 引脚命中点自身所在域的已知网络（若命中点非命名端点）
    for (des, pin), pts in pin_hit.items():
        for pt in pts:
            d = domain_of_pt[pt]
            if d not in dom_nets:
                for n in sheet["nets"]:
                    if n["net"]:
                        for px, py in n["points"]:
                            np_ = norm_pt((px, py))
                            if np_ in parent and find(np_) == d:
                                dom_nets.setdefault(d, set()).add(n["net"])

    # 5) 网络名传播：两脚无源器件桥
    #    器件两脚分属两域，若一脚所在域有名，则另一域继承（仅限两脚器件）
    #    优先级：信号网络名 > 电源/地网络名（避免上拉电阻的 GND 掩盖信号名）
    #    电源/地判定复用模块级 POWER_NET_RE（trace 同源，避免两份正则漂移）
    # 5) 普通两脚无源器件不再传播网络名；两侧网络保持独立，器件作为中间 hop。

    # 6) 汇总（重名引脚多命中点：合并所有命中点的域网络）
    result = {}
    for (des, pin), pts in pin_hit.items():
        ns = set()
        for pt in pts:
            ns |= dom_nets.get(domain_of_pt[pt], set())
        result[(des, pin)] = ",".join(sorted(ns))
    return result


def collect_two_pin_bridges(db, sheet, comp_pins, pinmap, endp=None):
    """输出所有两脚中间器件，连通性分析不再吞掉这些器件。

    返回 ``[{designator, kind, direct, pin_a, number_a, net_a, pin_b,
    number_b, net_b, device}]``。
    ``kind``: short|jumper|passive；``direct`` 表示脚本可识别的物理直连
    （symbolType=22 SHORT，或器件 title 为 0000/0R 的 0Ω 跳线）。
    若提供 ``endp``（坐标->网络名），优先用该引脚自己的物理端点网络名，
    避免桥接后两侧都显示 alias 串。
    """
    rows = []
    if not comp_pins:
        return rows

    def _key(p):
        return p.get("key") or p.get("pin")

    def _direct_net(p):
        if not endp:
            return pinmap.get((des, _key(p)), "")
        ax, ay = p.get("x"), p.get("y")
        if (ax, ay) in endp:
            return endp[(ax, ay)] or ""
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                if (ax + ox, ay + oy) in endp and endp[(ax + ox, ay + oy)]:
                    return endp[(ax + ox, ay + oy)]
        return pinmap.get((des, _key(p)), "")

    dev_map = db.device_map() if hasattr(db, "device_map") else {}
    for key, plist in comp_pins.items():
        des = key if isinstance(key, str) else key[0]
        if len(plist) != 2:
            continue
        a, b = plist
        sym_types = {p.get("sym_type") for p in plist}
        title = ""
        for c in sheet.get("components", []):
            if c.get("designator") == des:
                title = c.get("title") or ""
                break
        is_short = 22 in sym_types
        is_zero = bool(title and re.search(r"0000|0R|0Ω|0RΩ", str(title), re.I))
        kind = "short" if is_short else ("jumper" if is_zero else "passive")
        net_a = _direct_net(a)
        net_b = _direct_net(b)
        device = ""
        for c in sheet.get("components", []):
            if c.get("designator") == des:
                uuid = c.get("device_uuid") or c.get("symbol_uuid") or ""
                d = dev_map.get(uuid)
                device = (d[0] if d else "") or title
                break
        rows.append({
            "designator": des,
            "kind": kind,
            "direct": is_short or is_zero,
            "device": device or title,
            "title": title,
            "pin_a": _key(a), "number_a": a.get("number"),
            "net_a": net_a, "pos_a": [a.get("x"), a.get("y")],
            "pin_b": _key(b), "number_b": b.get("number"),
            "net_b": net_b, "pos_b": [b.get("x"), b.get("y")],
        })
    rows.sort(key=lambda r: (not r["direct"], r["kind"], natkey(r["designator"])))
    return rows


def resolve_page(db, page_name, schematic=None):
    """按页名（+可选板名）解析页：解决同名页歧义。返回页标题或 None。"""
    target = schematic
    for uuid, title, sch, dt in db.sheets():
        if title == page_name:
            if target is None:
                return title
            d, n = db.schem_map().get(sch, ("?", "?"))
            if target.lower() in (d.lower(), n.lower()):
                return title
    return None


def _synth_designator(db, c):
    """无 title/designator 的实例（short 短接符等）用合成 designator 保留。
    symbol_type=22 短接符无 title 无位号，两脚桥接跨网络（如 H_RESET↔RST）。"""
    if c.get("designator"):
        return c["designator"]
    sym = symbol_of(db, c)
    sp = db.symbol_pins(sym) if sym else None
    if sp and sp.get("symbol_type") == 22:
        return f"SHORT{c['cid']}"
    return None


def _collect_pinmap_data(db, sheet, page_name):
    """提取 cmd_pinmap/trace 共用的引脚网络数据：
    返回 (comp_pins, wires, pt_wires, endp)。
    comp_pins 键为 (designator, cid)；wires 为 [(wire_id, segs)]；
    pt_wires 为 {(x,y): set(wire_id)}；endp 为 {(x,y): net}。"""
    endp = {}
    pt_wires = {}
    for n in sheet["nets"]:
        nm = n["net"]
        for px, py in n["points"]:
            e = endp.setdefault((px, py), None)
            if e is None and nm:
                endp[(px, py)] = nm
            pt_wires.setdefault((px, py), set())
    recs = db.sheet_records(page_name)
    wires = []
    if recs:
        net_of = {}
        for a in recs:
            if not isinstance(a, list) or len(a) < 2:
                continue
            if a[0] == 'ATTR' and len(a) >= 5 and a[3] in ('NET', 'Global Net Name'):
                net_of[a[2]] = a[4]
            elif a[0] == 'WIRE' and len(a) >= 3:
                wires.append((a[1], a[2]))
        for wid, segs in wires:
            nm = net_of.get(wid)
            for s_ in segs:
                for p in ((s_[0], s_[1]), (s_[2], s_[3])):
                    if nm and endp.get(p) is None:
                        endp[p] = nm
                    pt_wires.setdefault(p, set()).add(wid)
    comp_pins = {}
    for c in sheet["components"]:
        des = _synth_designator(db, c)
        if not des:
            continue
        sym = symbol_of(db, c)
        sp = db.symbol_pins(sym) if sym else None
        if not sp or not sp["pins"]:
            continue
        # symbol_type=22: Short 短接符；17: CBB 复用模块。CBB 实例没有
        # title，但其引脚必须参与连通域分析，否则 CBB 与母图之间的
        # 连接会被静默漏掉。
        if not c["title"] and sp.get("symbol_type") not in (17, 22):
            continue
        # Part 名不限于 ".1/.2" 数字后缀：支持完整 PART 名、字母名
        # （XC7A35T....B0/B14/GTP/POWER）以及大小写差异。
        title = c.get("title") or ""
        parts = sp["parts"]
        part = title if title in parts else None
        if part is None:
            m = re.search(r"\.(\d+)$", title)
            if m:
                candidate = title[:-len(m.group(0))] + "." + m.group(1)
                if candidate in parts:
                    part = candidate
        if part is None:
            for candidate in parts:
                if str(candidate).lower() == title.lower():
                    part = candidate
                    break
        if part is None and len(parts) == 1:
            part = parts[0]
        if part is None:
            # 最后一个兜底：title 的尾段（.后）能匹配某个 PART 名。
            for candidate in parts:
                if str(candidate).endswith(title) or title.endswith(str(candidate)):
                    part = candidate
                    break
        if part not in parts:
            continue
        key = (des, c["cid"])
        plist = []
        for p in sp["pins"]:
            if p["part"] != part:
                continue
            rx, ry = p["x"], p["y"]
            if c.get("mirror"):
                rx = -rx
            rot = (c.get("rot") or 0) % 360
            for _ in range(int(rot // 90)):
                rx, ry = -ry, rx
            ax, ay = c["x"] + rx, c["y"] + ry
            plist.append({
                "pin": p["name"], "number": p["number"],
                "key": p["name"],
                "x": ax, "y": ay,
                "pin_type": p.get("pin_type"),
                "sym_type": sp.get("symbol_type")})
        # 同一器件内重名引脚必须用 name#number 区分（SHORT 的 Pin1/Pin1、
        # ESD 保护件的 IN/IN、NC/NC），否则下游按 (designator, pin-name)
        # 键会错误合并两个物理网络。
        name_count = {}
        for p in plist:
            name_count[p["pin"]] = name_count.get(p["pin"], 0) + 1
        for p in plist:
            if name_count[p["pin"]] > 1:
                p["key"] = f"{p['pin']}#{p['number']}"
        comp_pins[key] = plist
    return comp_pins, wires, pt_wires, endp


def cmd_pinmap(db, args):
    """精确引脚网络表：对指定页，用 实例坐标+PIN相对坐标+旋转 精确匹配 WIRE
    端点网络名（100% 可靠，无几何近似）。每个元件输出 引脚名->网络名。
    对网络名为空的引脚，输出 same_wire 关联（同一 WIRE 记录端点上的其他
    器件引脚），用于识别串阻/耦合/晶体管间接连接（如 LED->R->+5V）。
    --designator 只输出指定元件；--schematic 指定板名解决同名页。"""
    page = resolve_page(db, args.page, args.schematic)
    if page is None:
        out(f"未找到页: {args.page}" + (f" (schematic={args.schematic})" if args.schematic else ""))
        return
    args.page = page
    sheet = parse_sheet(db, args.page)
    if sheet is None:
        out(f"未找到页: {args.page}")
        return
    comp_pins, wires, pt_wires, endp = _collect_pinmap_data(
        db, sheet, args.page)

    # 每个引脚 -> 最近 WIRE 端点（容差2）-> net + 同 wire 的其他引脚
    rows = []
    for c in sheet["components"]:
        des = _synth_designator(db, c)
        if not des:
            continue
        if args.designator and des != args.designator.upper():
            continue
        key = (des, c["cid"])
        if key not in comp_pins:
            continue
        pinmap = []
        for p in comp_pins[key]:
            ax, ay = p["x"], p["y"]
            net = None
            hit_pt = None
            hit_wires = set()
            for (wx, wy), wids in pt_wires.items():
                if abs(ax - wx) <= 2 and abs(ay - wy) <= 2:
                    if hit_pt is None:
                        hit_pt = (wx, wy)
                    hit_wires |= wids
                    if net is None and endp.get((wx, wy)):
                        net = endp[(wx, wy)]
            # 同物理连接点的其他器件引脚 + 同 WIRE 记录的其他端点引脚
            peers = []
            wire_peers = []
            if hit_pt:
                for (odes, ocid), plist in comp_pins.items():
                    if odes == des:
                        continue
                    for op in plist:
                        if abs(op["x"] - hit_pt[0]) <= 2 and \
                                abs(op["y"] - hit_pt[1]) <= 2:
                            peers.append(f"{odes}.{op.get('key') or op['pin']}")
            if hit_wires:
                wire_pts = set()
                for wid in hit_wires:
                    for w in wires:
                        if w[0] == wid:
                            for s_ in w[1]:
                                if isinstance(s_, list) and len(s_) >= 4 and \
                                        all(isinstance(v, (int, float)) for v in s_):
                                    wire_pts.add((round(s_[0], 1), round(s_[1], 1)))
                                    wire_pts.add((round(s_[2], 1), round(s_[3], 1)))
                for (odes, ocid), plist in comp_pins.items():
                    if odes == des:
                        continue
                    for op in plist:
                        if (round(op["x"], 1), round(op["y"], 1)) in wire_pts:
                            tag = f"{odes}.{op.get('key') or op['pin']}"
                            if tag not in peers:
                                wire_peers.append(tag)
            pinmap.append({
                "pin": p.get("key") or p["pin"], "number": p["number"],
                "net": net or "",
                "pin_type": p.get("pin_type"),
                "peers": sorted(set(peers)),
                "wire_peers": sorted(set(wire_peers))})
        pinmap.sort(key=lambda x: natkey(x["number"] or ""))
        sym_t = None
        if comp_pins.get((des, c["cid"])):
            sym_t = comp_pins[(des, c["cid"])][0].get("sym_type")
        rows.append({"designator": des, "symbol": c["title"],
                     "symbol_type": sym_t, "pins": pinmap})
    # 连通域网络名解析：为 net 为空的引脚推断网络名（走线拓扑，无启发式噪声）
    if not args.no_domain:
        dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
        for row in rows:
            for pm in row["pins"]:
                if not pm["net"]:
                    key = (row["designator"], pm["pin"])
                    n = dom.get(key, "")
                    if n:
                        pm["net"] = n
                        pm["net_inferred"] = True
    if not args.json:
        for row in rows:
            out(f"== {row['designator']} ({row['symbol']}) ==")
            for pm in row["pins"]:
                peer = f"  <- {','.join(pm['peers'])}" if pm["peers"] else ""
                wp = f"  [wire: {','.join(pm['wire_peers'])}]" if pm["wire_peers"] else ""
                tag = "*" if pm.get("net_inferred") else ""
                out(f"  {pm['pin']:12s} (#{pm['number']:>3})  {pm['net'] or '(未命名)'}{tag}{peer}{wp}")
    if args.json:
        outj(rows)


def cmd_nets(db, args):
    """页内网络连接：网络名 -> 归属元件（连通域精确方案，与 pinmap 同源）。"""
    page = resolve_page(db, args.sheet, getattr(args, "schematic", None))
    if page is None:
        out(f"未找到页: {args.sheet}")
        return
    args.sheet = page
    sheet = parse_sheet(db, args.sheet)
    if sheet is None:
        out(f"未找到页: {args.sheet}")
        return
    pinc = _collect_pinmap_data(db, sheet, args.sheet)
    if pinc is None:
        out(f"未找到页: {args.sheet}")
        return
    comp_pins, wires, pt_wires, endp = pinc
    dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
    # 网络 -> 元件（designator 去重合并）
    net_comps = {}
    for (des, pin), net in dom.items():
        if net:
            for tok in net.split(","):
                net_comps.setdefault(tok, set()).add(des)
    # 网络 -> 端点坐标
    net_pts = {}
    for n in sheet["nets"]:
        if n["net"]:
            for px, py in n["points"]:
                net_pts.setdefault(n["net"], set()).add((px, py))
    rows = []
    for net in sorted(net_comps):
        comps = ",".join(sorted(net_comps[net]))
        pts = " ".join(f"({x},{y})" for x, y in sorted(net_pts.get(net, []))[:8])
        rows.append({"net": net, "components": sorted(net_comps[net]),
                     "points": sorted(net_pts.get(net, []))})
        if not args.json:
            out(f"{net:20s} <- {comps:24s} {pts}")
    if args.json:
        outj(rows)


def cmd_pins(db, args):
    """引脚级网络表：designator.pin -> 网络（连通域精确方案，与 pinmap 同源）。
    输出设计符、引脚、网络、推断标记；网络为空时给出 wire 关联引脚。"""
    page = resolve_page(db, args.sheet, getattr(args, "schematic", None))
    if page is None:
        out(f"未找到页: {args.sheet}")
        return
    args.sheet = page
    sheet = parse_sheet(db, args.sheet)
    if sheet is None:
        out(f"未找到页: {args.sheet}")
        return
    pinc = _collect_pinmap_data(db, sheet, args.sheet)
    if pinc is None:
        out(f"未找到页: {args.sheet}")
        return
    comp_pins, wires, pt_wires, endp = pinc
    dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
    rows = []
    seen = set()
    for (des, pin), net in sorted(dom.items()):
        key = (des, pin, net)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"designator": des, "pin": pin, "net": net})
        if not args.json:
            out(f"{des:10s} {pin:12s} {net or '(未命名)'}")
    if args.json:
        outj(rows)


POWER_NET_RE = re.compile(r"^(GND|AGND|DGND|PGND|VCC|VDD|VSS|VBUS|D3V3|3V3|3\.3V|5V|\+3\.3V|\+5V|\+15V|-15V|15V)$",
                          re.I)


def cmd_trace(db_or_dbs, args):
    """链路追踪（BFS）：从指定设计符出发，沿网络展开所有相连元件。
    单工程：跨页跨板归并；多工程（--eprj 多次 + --link 连接器对）：
    跨工程沿连接器桥展开。--depth 限制跳数，--no-power 跳过电源网络。"""
    dbs = db_or_dbs if isinstance(db_or_dbs, list) else [db_or_dbs]
    if len(dbs) == 1:
        db = dbs[0]
        return _trace_one(db, args, 0, {})
    # 多工程：构建 网络->元件 索引（按工程隔离），--link 指定桥
    return _trace_multi(dbs, args)

def _trace_one(db, args, eprj_idx=0, link_map=None):
    """单工程链路追踪（原 cmd_trace 逻辑）。"""
    sn = db.schem_map()
    dev = db.device_map()
    net_index = {}   # net -> {sheet: set(designators)}
    des_locs = {}    # designator -> [(sheet, schematic)]
    for uuid, title, sch, dt in db.sheets():
        if dt != 1:
            continue
        sheet = parse_sheet(db, title)
        if sheet is None:
            continue
        # 复用 pinmap 的连通域引脚网络解析
        pinc = _collect_pinmap_data(db, sheet, title)
        if pinc is None:
            continue
        comp_pins, wires, pt_wires, endp = pinc
        dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
        # 引脚 -> 网络 反查：建 网络 -> 元件（designator 统一大写）
        pin_net_of = {}
        for (des, pin), net in dom.items():
            if net:
                for tok in net.split(","):
                    pin_net_of.setdefault(tok, set()).add(des.upper())
        for net, des_set in pin_net_of.items():
            e = net_index.setdefault(net, {})
            e.setdefault(title, set()).update(des_set)
        for c in sheet["components"]:
            if c.get("designator"):
                des_locs.setdefault(c["designator"].upper(),
                                    []).append((title, sch))

    start = args.designator.upper()
    if start not in des_locs:
        out(f"未找到 {args.designator}")
        return
    visited_des = {start}
    visited_net = set()
    frontier = [start]
    hops = {start: 0}
    edges = []   # (net, from_des, to_des)

    while frontier:
        cur = frontier.pop(0)
        if hops[cur] >= args.depth:
            continue
        cur_nets = set()
        for sheet_title, sch in des_locs.get(cur, []):
            for nm, e in net_index.items():
                if sheet_title in e and cur in e[sheet_title]:
                    cur_nets.add(nm)
        for nm in cur_nets:
            if nm in visited_net:
                continue
            if args.no_power and POWER_NET_RE.match(nm):
                continue
            visited_net.add(nm)
            for sheet_title, des_set in net_index[nm].items():
                for nxt in des_set:
                    if nxt.upper() in visited_des:
                        continue
                    visited_des.add(nxt.upper())
                    hops[nxt.upper()] = hops[cur] + 1
                    edges.append((nm, cur, nxt.upper()))
                    frontier.append(nxt.upper())

    rows = [{"designator": d,
             "hops": hops[d],
             "nets": [nm for nm, f, t in edges if t == d or f == d]}
            for d in sorted(visited_des, key=lambda x: (hops[x], x))]
    if args.json:
        outj({"start": start, "edges": [
            {"net": nm, "from": f, "to": t} for nm, f, t in edges],
            "designators": rows})
        return
    out(f"== {args.designator} 链路追踪 (BFS, 最大{args.depth}跳) ==")
    for nm, f, t in edges:
        out(f"  [{nm:22s}] {f:8s} -> {t}")
    out("== 到达的元件 ==")
    for r in rows:
        locs = ",".join(f"{s}({sn.get(sch, ('?','?'))[1]})"
                        for s, sch in des_locs.get(r["designator"], []))
        out(f"  跳{r['hops']}  {r['designator']:10s}  {locs}")



def _trace_multi(dbs, args):
    """多工程链路追踪：各工程独立建网络索引；--link 指定连接器对作为跨工程桥。
    --link 格式: 工程索引:设计符<->工程索引:设计符（如 0:H2<->1:H2）。
    未指定 --link 时仅提示，不做跨工程合并（网络名跨工程不自动匹配）。"""
    # 1) 各工程建索引
    per = []   # [{net_index, des_locs, sn}]
    for di, db in enumerate(dbs):
        net_index = {}
        des_locs = {}
        for uuid, title, sch, dt in db.sheets():
            if dt != 1:
                continue
            sheet = parse_sheet(db, title)
            if sheet is None:
                continue
            pinc = _collect_pinmap_data(db, sheet, title)
            if pinc is None:
                continue
            comp_pins, wires, pt_wires, endp = pinc
            dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
            pin_net_of = {}
            for (des, pin), net in dom.items():
                if net:
                    for tok in net.split(","):
                        pin_net_of.setdefault(tok, set()).add(des.upper())
            for net, des_set in pin_net_of.items():
                e = net_index.setdefault(net, {})
                e.setdefault(title, set()).update(des_set)
            for c in sheet["components"]:
                if c.get("designator"):
                    des_locs.setdefault(c["designator"].upper(), []).append((title, sch))
        per.append({"net_index": net_index, "des_locs": des_locs,
                    "sn": db.schem_map()})

    # 2) --link 解析连接器对（工程索引:设计符）
    bridges = []   # (di_a, des_a, di_b, des_b)
    if args.link:
        for spec in args.link:
            m = re.match(r"(\d+):([A-Za-z0-9_]+)\s*<->\s*(\d+):([A-Za-z0-9_]+)", spec)
            if not m:
                out(f"--link 格式无效: {spec}（应为 0:H2<->1:H2）")
                return
            di_a, des_a, di_b, des_b = int(m.group(1)), m.group(2).upper(), int(m.group(3)), m.group(4).upper()
            if di_a >= len(dbs) or di_b >= len(dbs):
                out(f"--link 工程索引越界: {spec}")
                return
            bridges.append((di_a, des_a, di_b, des_b))

    # 3) BFS：全局 des 集合（前缀工程索引避免跨工程误合并）
    def gkey(di, des):
        return (di, des)

    start = args.designator.upper()
    starts = []
    for di, p in enumerate(per):
        if start in p["des_locs"]:
            starts.append(di)
    if not starts:
        out(f"未找到 {args.designator}")
        return

    visited = {gkey(di, start) for di in starts}
    visited_net = set()
    frontier = [(gkey(di, start), 0) for di in starts]
    hops = {gkey(di, start): 0 for di in starts}
    edges = []   # (net, from, to)

    while frontier:
        (di, cur), hop = frontier.pop(0)
        if hop >= args.depth:
            continue
        p = per[di]
        cur_nets = set()
        for sheet_title, sch in p["des_locs"].get(cur, []):
            for nm, e in p["net_index"].items():
                if sheet_title in e and cur in e[sheet_title]:
                    cur_nets.add(nm)
        for nm in cur_nets:
            nk = (di, nm)
            if nk in visited_net:
                continue
            if args.no_power and POWER_NET_RE.match(nm):
                continue
            visited_net.add(nk)
            for sheet_title, des_set in p["net_index"][nm].items():
                for nxt in des_set:
                    k = gkey(di, nxt)
                    if k in visited:
                        continue
                    visited.add(k)
                    hops[k] = hop + 1
                    edges.append((f"工程{di}:{nm}", f"{cur}", f"{nxt}"))
                    frontier.append((k, hop + 1))
        # 跨工程桥（双向：当前侧可能是 des_a 或 des_b，--link 写法两种都支持）
        for (di_a, des_a, di_b, des_b) in bridges:
            if di == di_a and cur == des_a:
                src_i, dst_i = di_a, di_b
                src_des, dst_des = des_a, des_b
            elif di == di_b and cur == des_b:
                src_i, dst_i = di_b, di_a
                src_des, dst_des = des_b, des_a
            else:
                continue
            # 查源侧连接器所在网络 -> 桥到目标侧同网络
            b_net = set()
            for sheet_title, sch in per[src_i]["des_locs"].get(src_des, []):
                for nm, e in per[src_i]["net_index"].items():
                    if sheet_title in e and src_des in e[sheet_title]:
                        b_net.add(nm)
            for nm in b_net:
                # 连接器桥只导通同名网络（引脚对齐：TEMP_IN_SCLK<->TEMP_IN_SCLK）
                for sheet_title, sch in per[dst_i]["des_locs"].get(dst_des, []):
                    for nm2, e in per[dst_i]["net_index"].items():
                        if nm2 != nm:
                            continue
                        if sheet_title in e and dst_des in e[sheet_title]:
                            nk = (dst_i, nm2)
                            if nk in visited_net:
                                continue
                            if args.no_power and POWER_NET_RE.match(nm2):
                                continue
                            visited_net.add(nk)
                            for st2, ds2 in e.items():
                                for nxt in ds2:
                                    k = gkey(dst_i, nxt)
                                    if k in visited:
                                        continue
                                    visited.add(k)
                                    hops[k] = hop + 1
                                    edges.append((f"桥{nm}->{nm2}", f"工程{src_i}:{src_des}", f"{nxt}"))
                                    frontier.append((k, hop + 1))

    rows = [{"designator": d, "eprj": di, "hops": hops[(di, d)]}
            for (di, d) in sorted(visited, key=lambda x: (hops[x], x[1]))]
    if args.json:
        outj(rows)
        return
    out(f"== {args.designator} 链路追踪（多工程, 最大{args.depth}跳） ==")
    for nm, f, t in edges:
        out(f"  [{nm:26s}] {f:8s} -> {t}")
    out("== 到达的元件 ==")
    for r in rows:
        out(f"  工程{r['eprj']} 跳{r['hops']}  {r['designator']}")


def cmd_netlist(db, args):
    """跨页网络归并：网络名 -> 出现的页与归属元件（连通域精确方案）。"""
    sn = db.schem_map()
    agg = {}
    for uuid, title, sch, dt in db.sheets():
        if dt != 1:
            continue
        sheet = parse_sheet(db, title)
        if sheet is None:
            continue
        pinc = _collect_pinmap_data(db, sheet, title)
        if pinc is None:
            continue
        comp_pins, wires, pt_wires, endp = pinc
        dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
        for (des, pin), net in dom.items():
            if not net:
                continue
            for tok in net.split(","):
                e = agg.setdefault(tok, {"sheets": [], "components": []})
                if title not in e["sheets"]:
                    e["sheets"].append(title)
                if des not in e["components"]:
                    e["components"].append(des)
    rows = []
    for net in sorted(agg, key=lambda k: k or ""):
        e = agg[net]
        rows.append({"net": net, "sheets": e["sheets"],
                     "components": sorted([c or "" for c in e["components"]], key=natkey)})
        if not args.json:
            out(f"{str(net or '(未命名)'):24s}  {','.join(e['sheets']):28s}  {','.join(sorted([c or '' for c in e['components']], key=natkey))}")
    if args.json:
        outj(rows)


def cmd_find(db, args):
    """Designator 反查：定位元件所在页/板及网络。"""
    sn = db.schem_map()
    dev = db.device_map()
    des = args.designator.upper()
    hits = []
    for uuid, title, sch, dt in db.sheets():
        if dt != 1:
            continue
        sheet = parse_sheet(db, title)
        if sheet is None:
            continue
        pinc = None
        dom = {}
        if not args.raw:
            # 用 pinmap 连通域精确方案（替代旧 BBOX 近似，后者对经串阻/短接
            # 连接的引脚网络归属不全）
            pinc = _collect_pinmap_data(db, sheet, title)
            if pinc:
                comp_pins, wires, pt_wires, endp = pinc
                dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
        for c in sheet["components"]:
            if (c.get("designator") or "").upper() == des:
                d, n = sn.get(sch, ("?", "?"))
                fr = _fmt_comp(c, dev)
                nets = []
                if not args.raw and pinc:
                    for (dkey, pin), net in dom.items():
                        if dkey.upper() == des and net:
                            nets.append(net)
                hits.append({"sheet": title, "schematic": d, **fr, "nets": nets})
    if not hits:
        out(f"未找到 {des}")
        return
    if args.json:
        outj(hits)
        return
    for h in hits:
        out(f"{des}: {h['sheet']} (sch={h['schematic']})  {h['title']}  {h['device']}")
        if h.get("nets"):
            uniq = sorted({t for n in h["nets"] for t in n.split(",")})
            out(f"    nets: {','.join(uniq)}")


def cmd_netfind(db_or_dbs, args):
    """全局同网络查询（引脚级）：网络名 -> 所有页的 (器件, 引脚)。
    与立创EDA"网络高亮"等效——遍历全工程连通域解析，输出该网络的全部连接点。
    支持多工程（--eprj 多次）：每个工程独立查询，输出标注工程来源，不跨工程合并。
    --json 输出结构化。"""
    dbs = db_or_dbs if isinstance(db_or_dbs, list) else [db_or_dbs]
    rows_all = []
    for di, db in enumerate(dbs):
        rows = _netfind_one(db, args.net)
        if len(dbs) > 1:
            for r in rows:
                r["eprj"] = f"#{di}"
            rows_all.extend(rows)
        else:
            rows_all = rows
    if not rows_all:
        out(f"未找到网络: {args.net}")
        return
    if args.json:
        outj(rows_all)
        return
    n = len(rows_all)
    out(f"== 网络 {args.net} ({n} 个连接点" + (", 多工程" if len(dbs) > 1 else "") + ") ==")
    cur = None
    for r in rows_all:
        key = (r.get("eprj"), r["sheet"], r["schematic"])
        if key != cur:
            cur = key
            tag = f"工程{r['eprj']} " if r.get("eprj") else ""
            out(f"  [{tag}{r['sheet']} (sch={r['schematic']})]")
        out(f"    {r['designator']}.{r['pin']}")


def _netfind_one(db, net_name):
    """单工程网络查询，返回 rows。"""
    sn = db.schem_map()
    target = net_name.upper()
    found = {}
    for uuid, title, sch, dt in db.sheets():
        if dt != 1:
            continue
        sheet = parse_sheet(db, title)
        if sheet is None:
            continue
        pinc = _collect_pinmap_data(db, sheet, title)
        if pinc is None:
            continue
        comp_pins, wires, pt_wires, endp = pinc
        dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
        d, n = sn.get(sch, ("?", "?"))
        for (des, pin), net in dom.items():
            if net and target in [t.upper() for t in net.split(",")]:
                key = (title, d)
                found.setdefault(key, []).append((des, pin))
    rows = []
    for (sheet, d) in sorted(found):
        for des, pin in sorted(found[(sheet, d)], key=lambda x: (x[0], str(x[1]))):
            rows.append({"sheet": sheet, "schematic": d,
                         "designator": des, "pin": pin})
    return rows


def cmd_link_check(dbs, args):
    """多工程连接器对核对：对每对工程，找出网络名逐 pin 一致的连接器候选。"""
    if not isinstance(dbs, list) or len(dbs) < 2:
        out("link-check 需至少两个工程（--eprj 多次）")
        return
    results = []
    for i in range(len(dbs)):
        for j in range(i + 1, len(dbs)):
            pairs = _conn_pairs(dbs[i], dbs[j])
            for (des_a, des_b, common, diff, total) in pairs:
                results.append({
                    "eprj_a": i, "eprj_b": j,
                    "connector_a": des_a, "connector_b": des_b,
                    "pin_common": common, "pin_diff": diff, "pin_total": total,
                })
    if not results:
        out("未找到网络名逐 pin 一致的连接器对")
        return
    if args.json:
        outj(results)
        return
    out("== 连接器对候选（网络名逐 pin 一致） ==")
    for r in results:
        status = "一致" if r["pin_diff"] == 0 else f"有{r['pin_diff']}差异"
        out(f"  工程{r['eprj_a']} {r['connector_a']} <-> 工程{r['eprj_b']} {r['connector_b']}: "
            f"{r['pin_common']}/{r['pin_total']} pin 网络一致 ({status})")


def _conn_pairs(db_a, db_b):
    """两工程间连接器网络映射对比，返回候选 (des_a, des_b, common, diff, total)。"""
    def conn_nets(db):
        """收集全工程连接器（designator 以 H/CN/J 开头且多 pin）的网络映射。"""
        res = {}
        for uuid, title, sch, dt in db.sheets():
            if dt != 1:
                continue
            sheet = parse_sheet(db, title)
            if sheet is None:
                continue
            pinc = _collect_pinmap_data(db, sheet, title)
            if pinc is None:
                continue
            comp_pins, wires, pt_wires, endp = pinc
            dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
            for (des, pin), net in dom.items():
                # 连接器：H/J/P 开头或 CN 前缀；排除 C（电容）、R、U、L 等
                if des and (des[0] in ("H", "J", "P") or des.startswith("CN")) \
                        and len(pin) <= 3:
                    res.setdefault(des, {}).setdefault(pin, set()).add(net or "")
        return res

    na = conn_nets(db_a)
    nb = conn_nets(db_b)
    pairs = []
    for des_a, pins_a in na.items():
        for des_b, pins_b in nb.items():
            # 需同 pin 数（对插连接器 pin 数一致）
            if len(pins_a) != len(pins_b):
                continue
            common = 0
            diff = 0
            total = 0
            for pin in pins_a:
                if pin not in pins_b:
                    continue
                total += 1
                nets_a = pins_a[pin]
                nets_b = pins_b[pin]
                if nets_a == nets_b and nets_a != {""}:
                    common += 1
                else:
                    diff += 1
            if total >= len(pins_a) // 2:
                pairs.append((des_a, des_b, common, diff, total))
    return pairs

def cmd_search(db, args):
    sn = db.schem_map()
    try:
        pat = re.compile(args.pattern, re.I if not args.case else 0)
    except re.error as e:
        out(f"正则无效: {e}")
        return
    rows = []
    for uuid, title, sch, dt in db.sheets():
        if dt != 1:
            continue
        text = db.sheet_text(title)
        if not text:
            continue
        hits = set()
        for ln in text.splitlines():
            if pat.search(ln):
                hits.add(ln.strip()[:120])
        if hits:
            d, n = sn.get(sch, ("?", "?"))
            if args.json:
                rows.append({"sheet": title, "schematic": d, "hits": sorted(hits)})
            else:
                out(f"== {title} (sch={d}) ==")
                for h in sorted(hits):
                    out(f"  {h}")
    if args.json:
        outj(rows)


def cmd_bom(db, args):
    """按器件归并全工程物料；--board 按板过滤；--json 含结构化 value。
    --bom-only 只保留 Add into BOM=yes 的器件（排除框图符号等）。
    --board 匹配 @Board Name；若标题块未填，则回退匹配 schematic 的
    display_name/name（不区分大小写）。"""
    dev = db.device_map()
    sn = db.schem_map()
    bom = {}
    for uuid, title, sch, dt in db.sheets():
        if dt != 1:
            continue
        sheet = parse_sheet(db, title)
        if sheet is None:
            continue
        board = sheet["attrs"].get("@Board Name", "")
        if args.board:
            # 统一不区分大小写（@Board Name 与 schematic 名兜底一致）
            if board.lower() == args.board.lower():
                pass
            elif not board:
                # 标题块未填 @Board Name 时按 schematic 名兜底（不区分大小写）
                disp, name = sn.get(sch, ("", ""))
                if args.board.lower() != disp.lower() and \
                        args.board.lower() != name.lower():
                    continue
            else:
                continue
        for c in sheet["components"]:
            des = c.get("designator")
            if not des:
                continue
            key = c.get("symbol_uuid") or c.get("device_uuid") or ""
            e = bom.setdefault(key, {"title": "", "device": "", "desc": "",
                                     "desigs": set(), "sheets": set(),
                                     "boards": set(), "value": {},
                                     "supplier": "", "add_bom": ""})
            e["desigs"].add(des)
            e["sheets"].add(title)
            if board:
                e["boards"].add(board)
            if key in dev:
                t, d, ds = dev[key]
                e["title"] = t
                e["device"] = d
                e["desc"] = ds
                e["value"] = parse_value(ds)
            du = c.get("device_uuid")
            if du:
                da = db.device_attrs(du)
                if not e["supplier"]:
                    e["supplier"] = da.get("Supplier Part", "")
                if not e["add_bom"]:
                    e["add_bom"] = da.get("Add into BOM", "")
    rows = []
    for key in sorted(bom):
        e = bom[key]
        if args.bom_only and e["add_bom"] and e["add_bom"].lower() != "yes":
            continue
        desigs = ",".join(sorted(e["desigs"], key=natkey))
        rows.append({
            "designators": desigs,
            "device": e["device"],
            "description": e["desc"],
            "value": e["value"],
            "supplier_part": e["supplier"],
            "add_bom": e["add_bom"],
            "boards": sorted(e["boards"]),
            "sheets": sorted(e["sheets"]),
        })
        if not args.json:
            sup = f" [{e['supplier']}]" if e["supplier"] else ""
            out(f"{desigs:44s} {e['device']:24s} {e['desc'][:60]}  [{','.join(sorted(e['sheets']))}]{sup}")
    if args.json:
        outj(rows)


def cmd_datasheets(db, args):
    """从 attributes 表提取 Datasheet URL 清单。"""
    raw = list(db.cur.execute(
        "SELECT value, device_uuid FROM attributes WHERE key='Datasheet' AND value!=''"))
    name_map = db.device_map()
    rows = []
    for value, dev_uuid in raw:
        t, d, ds = name_map.get(dev_uuid, ("", "", ""))
        rows.append({"device": d or t or dev_uuid, "url": value})
    if args.json:
        outj(rows)
        return
    if not rows:
        out("attributes 表中无 Datasheet 记录")
    for r in rows:
        out(f"{r['device']:28s} {r['url']}")


def cmd_attrs(db, args):
    page = resolve_page(db, args.sheet, getattr(args, "schematic", None))
    if page is None:
        out(f"未找到页: {args.sheet}")
        return
    args.sheet = page
    sheet = parse_sheet(db, args.sheet)
    if sheet is None:
        out(f"未找到页: {args.sheet}")
        return
    seen = set()
    rows = []
    # 页标题块（e1）属性优先
    for name, val in sheet["attrs"].items():
        if val == "":
            continue
        rows.append({"name": name, "value": val, "component": "(页标题块)"})
        if not args.json:
            out(f"{name:24s} = {val}")
    for c in sheet["components"]:
        for name, val in c["attrs"].items():
            key = (name, val)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"name": name, "value": val, "component": c.get("designator") or c["cid"]})
            if not args.json:
                out(f"{name:24s} = {val}")
    if args.json:
        outj(rows)


def cmd_devmap(db, args):
    dev = db.device_map()
    rows = []
    for u in sorted(dev):
        t, d, ds = dev[u]
        rows.append({"uuid": u, "title": t, "display": d, "description": ds})
        if not args.json:
            out(f"{u[:8]}  {t:24s} {d:24s} {ds[:60]}")
    if args.json:
        outj(rows)


def cmd_raw(db, args):
    page = resolve_page(db, args.sheet, getattr(args, "schematic", None))
    if page is None:
        out(f"未找到页: {args.sheet}")
        return
    args.sheet = page
    text = db.sheet_text(args.sheet)
    if text is None:
        out(f"未找到页: {args.sheet}")
        return
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        out(f"written: {args.output}")
    else:
        out(text)


def main():
    # Windows 下固定 stdout 编码为 UTF-8（配合 PYTHONIOENCODING 或重定向到文件时中文不乱码）
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="立创EDA专业版 .eprj2 原理图读取工具")
    ap.add_argument("--eprj", action="append", default=None,
                    help="工程文件路径（.eprj2 SQLite 或 .epro ZIP），可多次(单工程或关联多工程)")
    ap.add_argument("--json", action="store_true",
                    help="结构化 JSON 输出（供脚本消费）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出板与页").set_defaults(fn=cmd_list)
    sub.add_parser("boards", help="列出每页的 @Board Name/@Page Name").set_defaults(fn=cmd_boards)

    p = sub.add_parser("components", help="列出页内元件(设计符/型号/值)")
    p.add_argument("sheet", nargs="?", default=None)
    p.set_defaults(fn=cmd_components)

    p = sub.add_parser("nets", help="页内网络连接(stub端点归属元件)")
    p.add_argument("sheet")
    p.add_argument("--schematic", default=None, help="指定板名解决同名页")
    p.set_defaults(fn=cmd_nets)

    p = sub.add_parser("pinmap", help="精确引脚网络表(实例坐标+PIN坐标精确匹配)")
    p.add_argument("page")
    p.add_argument("--designator", default=None, help="只输出指定元件")
    p.add_argument("--schematic", default=None, help="指定板名解决同名页")
    p.add_argument("--no-domain", action="store_true",
                   help="不做连通域网络名推断(仅原始网络名)")
    p.set_defaults(fn=cmd_pinmap)

    p = sub.add_parser("pins", help="引脚级网络表(designator→网络,连通域精确方案)")
    p.add_argument("sheet")
    p.add_argument("--schematic", default=None, help="指定板名解决同名页")
    p.set_defaults(fn=cmd_pins)

    sub.add_parser("netlist", help="跨页网络归并").set_defaults(fn=cmd_netlist)

    p = sub.add_parser("netfind", help="全局同网络查询(引脚级)：网络名->所有页连接点")
    p.add_argument("net")
    p.set_defaults(fn=cmd_netfind)

    p = sub.add_parser("trace", help="链路追踪：从设计符沿网络BFS展开相连元件")
    p.add_argument("designator")
    p.add_argument("--depth", type=int, default=5)
    p.add_argument("--no-power", action="store_true",
                   help="跳过电源/地网络(GND/AGND/VCC/3.3V等)")
    p.add_argument("--link", action="append", default=None,
                   help="跨工程连接器对，格式 0:H2<->1:H2 (工程索引:设计符)，可多次")
    p.set_defaults(fn=cmd_trace)

    p = sub.add_parser("link-check", help="多工程连接器对核对(网络逐pin一致候选)")
    p.set_defaults(fn=cmd_link_check)

    p = sub.add_parser("find", help="Designator 反查(元件所在页/板/网络)")
    p.add_argument("designator")
    p.add_argument("--raw", action="store_true",
                   help="raw 模式下不解析网络归属(更快)")
    p.set_defaults(fn=cmd_find)

    p = sub.add_parser("search", help="跨页正则搜索")
    p.add_argument("pattern")
    p.add_argument("--case", action="store_true")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("bom", help="按器件归并全工程物料清单")
    p.add_argument("--board", help="按板过滤(@Board Name 或 schematic 名)")
    p.add_argument("--bom-only", action="store_true",
                   help="仅保留 Add into BOM=yes 的器件")
    p.set_defaults(fn=cmd_bom)

    sub.add_parser("datasheets", help="从 attributes 表导出 Datasheet URL 清单"
                   ).set_defaults(fn=cmd_datasheets)

    p = sub.add_parser("attrs", help="导出页的全部属性(含@标题块)")
    p.add_argument("sheet")
    p.add_argument("--schematic", default=None, help="指定板名解决同名页")
    p.set_defaults(fn=cmd_attrs)

    sub.add_parser("devmap", help="导出 devices/components 表").set_defaults(fn=cmd_devmap)

    p = sub.add_parser("raw", help="输出页的原始 NDJSON")
    p.add_argument("sheet")
    p.add_argument("-o", "--output")
    p.add_argument("--schematic", default=None, help="指定板名解决同名页")
    p.set_defaults(fn=cmd_raw)

    args = ap.parse_args()
    if args.eprj:
        paths = args.eprj
    else:
        p0 = find_eprj(None)
        paths = [p0] if p0 else []
    if not paths:
        out("未找到 .eprj2，请用 --eprj 指定路径")
        sys.exit(1)
    def open_db(p):
        if str(p).lower().endswith(".epro"):
            out(f"[lceda_reader] 检测到 .epro ZIP 导出包，自动解包读取：{p}")
            out("[lceda_reader] 读取 project.json / SHEET/*.esch / SYMBOL/*.esym / DEVICE 数据 ...")
            return EproDB(p)
        return LcedaDB(p)

    try:
        dbs = [open_db(p) for p in paths]
    except Exception as e:
        out(f"无法打开工程: {e}")
        sys.exit(1)
    if len(dbs) == 1:
        args.fn(dbs[0], args)
    else:
        # 多工程：命令需支持多工程（netfind/link-check/trace/find/search 等）
        multi = getattr(args, 'fn', None)
        if multi in (cmd_netfind, cmd_link_check, cmd_trace, cmd_find, cmd_search):
            args.dbs = dbs
            multi(dbs, args)
        else:
            out(f"多工程模式仅支持 netfind/link-check/trace/find/search，当前命令不支持")
            sys.exit(1)


if __name__ == "__main__":
    main()
