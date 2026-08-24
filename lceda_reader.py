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
from abc import ABC, abstractmethod
from pathlib import Path


# ---------------------------------------------------------------- 基础层

class UnsupportedFormatError(Exception):
    """文件格式无法识别或暂不支持（message 面向用户给出可行路径）。"""


class SchemaBackend(ABC):
    """后端接口层（抽象基类）。

    约定：
    - ``sheets()`` 返回 (uuid, 标题, schematic_uuid, docType) 全量行
      （含非原理图文档），调用方自行过滤 docType==1；
    - ``sheet_records(uuid)`` 返回统一 V2 数组模型
      （COMPONENT/ATTR/WIRE[嵌套段]），格式差异在各自后端内归一化；
    - ``sheet_text``/``sheet_records`` 的实参一律为文档 uuid（同名页唯一键）；
    - 坐标统一为 V2 语义（Y 向下、0.01inch 或等效整数网格），格式差异
      （如 V3 的 Y 向上 mm 浮点）在后端内转换；
    - 缓存槽（_dmap_cache/_cbb_sym_map/_cbb_sig/_cbb_dom_cache）由基类
      初始化，通用函数可直接读写，禁止 getattr 动态贴属性。
    新增格式：继承本类实现全部 @abstractmethod，并在 detect_backend 登记
    内容特征即可，命令层零改动。"""

    FORMAT_NAME = "abstract"

    def __init__(self, path):
        self.path = Path(path)
        self._dmap_cache = None
        self._cbb_sym_map = None
        self._cbb_sig = None
        self._cbb_dom_cache = {}

    def project_name(self):
        """可读项目名：以文件名（去扩展名）为准——工程内 projects.name 为
        立创EDA默认名（New Project_日期），无实际意义。"""
        return self.path.stem

    def project_title(self):
        """工程内部名称（用户命名）；无意义/缺失返回 None。
        旧版 .eprj2 的 projects.name 为默认名，视为无名称；.epro 无该字段；
        新版 .eprj2/.epro2 有真实工程名。"""
        try:
            row = self.cur.execute("SELECT name FROM projects").fetchone()
            n = row[0] if row else None
            if n and not re.match(r"^New Project_\d{4}-\d{2}-\d{2}", n):
                return n
        except Exception:
            pass
        return None

    def texts_of(self, doc_key):
        """页内文本注释（TEXT 记录）。"""
        sh = self.parse_sheet_public(doc_key)
        return sh["texts"] if sh else []

    def parse_sheet_public(self, doc_key):
        return parse_sheet(self, doc_key)

    def decompress(self, ds):
        """dataStr 解码（ZIP 系后端恒等实现，SQLite 系覆盖）。"""
        return ds

    def cbb_symbol_board_map(self):
        """CBB 黑盒精确映射 {键: 模板板名}；键与该格式实例 Symbol 属性值
        同构（V2=uuid，V3=uuid/标题）。无原生映射的后端返回 {}，
        _expand_cbb 将回退 同目录.eprj2 blockSymbols > 端口集匹配。"""
        return {}

    PCB_SUPPORT = False

    def pcb_docs(self):
        """[(uuid, title)] 工程 PCB 文档列表；不支持的后端返回 []。"""
        return []

    def pcb_inventory(self):
        """解析全部 PCB 文档（V2 数组模型）。
        返回 [{"uuid","title","comps","nets","pads"}]：
          comps: [{"cid","uid","designator","device","footprint",
                   "layer","x","y","rot"}]
            uid = COMPONENT 内联属性 "Unique ID"（ggeN）——SCH↔PCB 全局
            唯一映射键（实测交集 100%）；32 位 hex 是 Device/Footprint
            uuid，不跨文档共享，勿混用。
          nets: [网络名]，pads: [{"comp","pin","net"}] 焊盘网络归属。
        仅旧版 .eprj2（SQLite documents.docType=3）支持。"""
        if not self.PCB_SUPPORT:
            raise UnsupportedFormatError(
                f"{self.FORMAT_NAME} 暂不支持 PCB 解析"
                "（当前仅旧版 .eprj2 SQLite 支持）")
        result = []
        for u, title in self.pcb_docs():
            recs = self.sheet_records(u, doc_type=3)
            if recs is None:
                continue
            inv = {"uuid": u, "title": title,
                   "comps": [], "nets": [], "pads": []}
            comps = {}
            for a in recs:
                if not isinstance(a, list) or len(a) < 2:
                    continue
                k = a[0]
                if k == "COMPONENT":
                    cid = str(a[1])
                    inline = a[7] if len(a) > 7 and isinstance(a[7], dict) \
                        else {}
                    # 官方布局(PCB文档格式 §10.1)：[id,分组(2),层(3),
                    # X(4),Y(5),旋转(6),自定义属性(7),锁定(8)]
                    comps[cid] = {
                        "cid": cid,
                        "uid": str(inline.get("Unique ID") or ""),
                        "designator": "", "device": "", "footprint": "",
                        "group": str(a[2]) if len(a) > 2 else "",
                        "layer": a[3] if len(a) > 3 else 0,
                        "x": a[4] if len(a) > 4 else 0,
                        "y": a[5] if len(a) > 5 else 0,
                        "rot": a[6] if len(a) > 6 else 0,
                    }
                elif k == "ATTR" and len(a) >= 9:
                    # PCB ATTR 布局（与 SCH 不同）：
                    # [type,id,?,parent,?,x,y,key,value,...]
                    pid, key = str(a[3]), str(a[7])
                    val = "" if a[8] is None else str(a[8])
                    c = comps.get(pid)
                    if c is not None:
                        if key == "Designator":
                            c["designator"] = val
                        elif key == "Device":
                            c["device"] = val
                        elif key == "Footprint":
                            c["footprint"] = val
                elif k == "NET" and len(a) >= 2 and a[1]:
                    inv["nets"].append(str(a[1]))
                elif k == "PAD_NET" and len(a) >= 5:
                    inv["pads"].append({"comp": str(a[1]), "pin": str(a[2]),
                                        "net": str(a[3])})
            for c in comps.values():
                if c["designator"] or c["uid"]:
                    inv["comps"].append(c)
            inv["comps"].sort(
                key=lambda c: natkey(c["designator"] or c["cid"]))
            inv["nets"] = sorted(set(inv["nets"]))
            result.append(inv)
        return result

    def symbol_records(self, symbol_uuid):
        """符号文档原始记录数组（V2 图形原语 POLY/RECT/CIRCLE/ARC/PIN/TEXT
        + LINESTYLE/FONTSTYLE 样式表），供渲染器使用；无原始图形的后端
        返回 None（渲染器退化为 bbox+引脚桩）。坐标为符号相对坐标，
        HEAD.originX/originY 偏移由渲染器统一处理。"""
        return None

    @abstractmethod
    def schematics(self):
        """[(uuid, name, display_name)] 板级列表。"""

    @abstractmethod
    def schem_map(self):
        """{schematic_uuid: (display, name)}"""

    @abstractmethod
    def sheets(self, doc_type=1):
        """[(uuid, 标题, schematic_uuid, docType)] 全文档行。"""

    @abstractmethod
    def sheet_text(self, doc_key, doc_type=1):
        """单页原始文本（uuid 优先）；无此页返回 None。"""

    @abstractmethod
    def sheet_records(self, doc_key, doc_type=1):
        """单页 V2 数组记录；无此页返回 None。"""

    @abstractmethod
    def device_map(self):
        """{uuid: (title, 型号, 描述)}，uuid 含 Device 与 Symbol 两空间。"""

    @abstractmethod
    def device_attrs(self, device_uuid):
        """{key: value} 器件级属性。"""

    @abstractmethod
    def symbol_of_device(self, device_uuid):
        """Device uuid -> Symbol uuid（无桥接机制的后端返回 None）。"""

    @abstractmethod
    def symbol_pins(self, symbol_uuid):
        """符号引脚表 {pins:[{id,name,number,x,y,rot,part,...}], bbox,
        parts, symbol_type}；坐标为符号相对坐标。"""

    @abstractmethod
    def datasheet_rows(self):
        """[{"device": 名, "url": Datasheet URL}]"""

    @abstractmethod
    def hierarchy(self):
        """工程内层级（立创EDA 工程面板语义）：
        {"project": 工程名,
         "boards": [{"uuid", "title",
                     "schematics": [{"uuid", "title",
                                     "pages": [{uuid,title}]}],
                     "pcbs": [{"uuid", "title"}]}],
         "free": {"schematics": [...], "pages": [...], "pcbs": [...]}}
        free = 未归属任何板的原理图/页/PCB；旧版 .eprj2 无板层数据时全部
        归 free（如实呈现，不虚构板）。"""

    @abstractmethod
    def hierarchy(self):
        """工程内层级（立创EDA 工程面板语义）：
        {"project": 工程名,
         "boards": [{"uuid", "title",
                     "schematics": [{"uuid", "title", "pages": [{uuid,title}]}],
                     "pcbs": [{"uuid", "title"}]}],
         "free": {"schematics": [...], "pages": [...], "pcbs": [...]}}
        free = 未归属任何板的原理图/页/PCB（旧版 .eprj2 无板层时全部归 free）。"""

def out(s=""):
    print(s)


def outj(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def _multi_json(dbs, rows):
    """多工程 json 顶层结构：projects 给出 索引->项目名/文件 映射，
    rows 为命令结果（行内 eprj 字段与索引对应），供消费方区分数据来源。"""
    return {
        "projects": [{"eprj": i, "project": db.project_name(), "file": str(db.path)}
                     for i, db in enumerate(dbs)],
        "rows": rows,
    }


def find_eprj(path=None):
    """定位工程文件（通用，不绑定任何工程目录结构）：
    1) 显式 --eprj 优先；
    2) 否则搜索当前工作目录及其父目录的 *.eprj2——命中多个时列出并要求
       显式指定（避免 glob 顺序不确定导致静默读错工程）；
    3) 无 .eprj2 时退化为 *.epro 同样逻辑。"""
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
    for pattern in ("*.eprj2", "*.epro2", "*.epro"):
        hits = []
        for base in bases:
            hits.extend(glob.glob(os.path.join(base, pattern)))
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            out("发现多个工程文件，请用 --eprj 显式指定其一：")
            for h in sorted(set(hits)):
                out(f"  {h}")
            sys.exit(1)
    return None


def natkey(s):
    s = s or ""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


# dom 网络集合的内部分隔符（UNICODE 分隔符，正常网络名不会包含）。
# 历史值可能为逗号拼接，net_tokens 同时兼容。
NET_SEP = "\u241f"


def net_tokens(v):
    """dom 网络字段 -> 网络名列表（兼容 NET_SEP 与历史逗号拼接）。"""
    v = str(v or "")
    if NET_SEP in v:
        return [t for t in v.split(NET_SEP) if t]
    return [t for t in v.split(",") if t]


def net_disp(v):
    """显示/JSON 输出：内部分隔符转逗号（保持既有消费方兼容）。"""
    return str(v or "").replace(NET_SEP, ", ")


class LcedaDB(SchemaBackend):
    """立创EDA 专业版 .eprj2（V2.2 SQLite，旧版保存格式）后端。"""

    FORMAT_NAME = "立创EDA .eprj2（V2.2 SQLite）"

    def __init__(self, path):
        super().__init__(path)
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

    PCB_SUPPORT = True

    def pcb_docs(self):
        return [(u, t) for u, t in self.cur.execute(
            "SELECT uuid, display_title FROM documents WHERE docType=3")]

    @staticmethod
    def decompress(ds):
        """dataStr 解码。两种形态：'base64' 前缀 + base64(gzip(NDJSON))；
        或直接明文 NDJSON（官方示例工程实测）。"""
        if not ds:
            return ""
        if isinstance(ds, str) and ds.startswith("base64"):
            try:
                data = base64.b64decode(ds[6:])
            except Exception:
                return ""
            try:
                return gzip.decompress(data).decode("utf-8")
            except Exception:
                return data.decode("utf-8", errors="replace")
        return ds

    def sheet_text(self, doc_key, doc_type=1):
        """取一页原始文本。doc_key 优先按 document uuid 精确查（同名页唯一）；
        查不到则回退按 display_title（兼容旧调用/旧工程）。"""
        key = (doc_type, doc_key)
        if key in self._text_cache:
            return self._text_cache[key]
        row = self.cur.execute(
            "SELECT dataStr FROM documents WHERE uuid=?", (doc_key,)).fetchone()
        if row is None:
            row = self.cur.execute(
                "SELECT dataStr FROM documents WHERE docType=? AND display_title=?",
                (doc_type, doc_key)).fetchone()
        text = self.decompress(row[0]) if row else None
        self._text_cache[key] = text
        return text

    def sheet_records(self, doc_key, doc_type=1):
        """取一页解析后的记录数组。doc_key 同 sheet_text（uuid 优先，title 回退）。
        契约：doc_type=1 只服务 docType=1 页——PCB(docType=3) 等文档
        返回 None（防误当 SCH 解析；PCB 走 pcb_inventory/doc_type=3）。"""
        key = (doc_type, doc_key, "recs")
        if key in self._text_cache:
            return self._text_cache[key]
        row = self.cur.execute(
            "SELECT docType, dataStr FROM documents WHERE uuid=?",
            (doc_key,)).fetchone()
        if row is None:
            row = self.cur.execute(
                "SELECT docType, dataStr FROM documents "
                "WHERE docType=? AND display_title=?",
                (doc_type, doc_key)).fetchone()
        if row is None:
            self._text_cache[key] = None
            return None
        if doc_type == 1 and row[0] != 1:
            # 类型不匹配（如 PCB uuid 误入）：明确 None
            self._text_cache[key] = None
            return None
        text = self.decompress(row[1])
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
        if self._dmap_cache is not None:
            return self._dmap_cache
        m = {}
        for r in self.cur.execute(
                "SELECT uuid, title, display_title, description FROM devices"):
            m[r[0]] = (r[1], r[2] or "", r[3] or "")
        for r in self.cur.execute(
                "SELECT uuid, title, display_title, description FROM components"):
            if r[0] not in m:
                m[r[0]] = (r[1], r[2] or "", r[3] or "")
        self._dmap_cache = m
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

    def datasheet_rows(self):
        raw = list(self.cur.execute(
            "SELECT value, device_uuid FROM attributes "
            "WHERE key='Datasheet' AND value!=''"))
        name_map = self.device_map()
        return [{"device": name_map.get(du, ("", "", ""))[0] or
                 name_map.get(du, ("", "", ""))[1] or du, "url": v}
                for v, du in raw]

    def hierarchy(self):
        """旧版 .eprj2 无板层数据（boards 表空、PCB 无关联字段）——
        如实呈现：全部原理图（含页）与 PCB 归入 free。"""
        pages_by_sch = {}
        sch_order = []
        seen = set()
        sn = self.schem_map()
        for u, t, s, dt in self.sheets():
            if s not in seen:
                seen.add(s)
                disp = sn.get(s, (s, s))
                sch_order.append({"uuid": s,
                                  "title": disp[0] or disp[1] or s,
                                  "pages": []})
            if dt == 1:
                pages_by_sch.setdefault(s, []).append(
                    {"uuid": u, "title": t})
        for ent in sch_order:
            ent["pages"] = pages_by_sch.get(ent["uuid"], [])
        pcbs = [{"uuid": u, "title": (t or u)}
                for u, t in self.cur.execute(
                    "SELECT uuid, display_title FROM documents "
                    "WHERE docType=3")]
        return {"project": self.project_name(),
        "project_title": self.project_title(), "boards": [],
                "free": {"schematics": sch_order, "pages": [],
                         "pcbs": pcbs}}

    def symbol_records(self, symbol_uuid):
        row = self.cur.execute(
            "SELECT dataStr FROM components WHERE uuid=?", (symbol_uuid,)
        ).fetchone()
        if not row:
            return None
        text = self.decompress(row[0])
        arrs = []
        for ln in text.splitlines():
            try:
                a = json.loads(ln)
            except Exception:
                continue
            if isinstance(a, list):
                arrs.append(a)
        return arrs

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
            p["name"] = names.get(pid) or numbers.get(pid) or "1"
            p["number"] = numbers.get(pid)
            p["pin_type"] = pin_types.get(pid)
        return {"pins": list(pins.values()), "bbox": bbox, "parts": sorted(
            {p["part"] for p in pins.values()}),
            "symbol_type": symbol_type}


class EproDB(SchemaBackend):
    """立创EDA ``.epro``（V2 ZIP 导出）后端。

    Implements the same duck-typed interface as :class:`LcedaDB` so the CLI
    commands (list/boards/components/nets/pinmap/pins/netfind/trace/...) can
    transparently read a ZIP export as well as the SQLite ``.eprj2`` format.
    """

    FORMAT_NAME = "立创EDA .epro（V2 ZIP 导出）"

    def __init__(self, path):
        super().__init__(path)
        self.zip = zipfile.ZipFile(self.path)
        self.obj = json.loads(self.zip.read("project.json"))
        self._devices = self.obj.get("devices", {})
        self._symbols = self.obj.get("symbols", {})
        self._boards = self.obj.get("boards", {})
        self._schematics = self.obj.get("schematics", {})
        self._names = set(self.zip.namelist())
        self._page_index = {}      # unique_title -> (schematic uuid, page id)
        self._records_cache = {}
        self._symbol_pin_cache = {}
        self._build_page_index()

    def _build_page_index(self):
        for board_name, board in self._boards.items():
            sch_uuid = board.get("schematic")
            if not sch_uuid:
                continue
            sch = self._schematics.get(sch_uuid, {})
            for page in sch.get("sheets", []):
                page_name = page.get("display_title") or page.get("name") or str(page.get("id"))
                key = f"{board_name}::{page_name}"
                self._page_index[key] = (sch_uuid, int(page["id"]))
                pu = page.get("uuid")
                if pu:
                    self._page_index.setdefault(pu, (sch_uuid, int(page["id"])))
        # CBB module schematics are also reachable through their own namespace.
        for sch_uuid, sch in self._schematics.items():
            sch_name = sch.get("name", sch_uuid)
            for page in sch.get("sheets", []):
                page_name = page.get("display_title") or page.get("name") or str(page.get("id"))
                key = f"CBBMOD::{sch_name}::{page_name}"
                self._page_index[key] = (sch_uuid, int(page["id"]))
                pu = page.get("uuid")
                if pu:
                    self._page_index.setdefault(pu, (sch_uuid, int(page["id"])))

    # -- lceda_reader-compatible API ----------------------------------------
    def schematics(self):
        return [(name, name, name) for name in self._boards]

    def schem_map(self):
        return {name: (name, name) for name in self._boards}

    def sheets(self, doc_type=1):
        rows = []
        for board_name, board in self._boards.items():
            sch_uuid = board.get("schematic")
            sch = self._schematics.get(sch_uuid, {})
            for page in sch.get("sheets", []):
                title = f"{board_name}::{page.get('display_title') or page.get('name') or page['id']}"
                rows.append((page.get("uuid"), title, board_name, 1))
        return rows

    def sheet_text(self, doc_key, doc_type=1):
        """取一页原始文本。doc_key 优先按 document uuid 精确查（同名页唯一）；
        查不到则回退按 "板名::页名" 复合标题查。doc_type=3 时读
        PCB/<uuid>.epcb（uuid 或 project.json pcbs 的文件名均可）。"""
        ck = ("text", doc_type, doc_key)
        if ck in self._records_cache:
            return self._records_cache[ck]
        text = None
        if doc_type == 3:
            pu = doc_key if f"PCB/{doc_key}.epcb" in self._names else None
            if pu is None:
                for u, t in self.obj.get("pcbs", {}).items():
                    if t == doc_key:
                        pu = u
                        break
            fname = f"PCB/{pu}.epcb" if pu else None
            if fname in self._names:
                text = self.zip.read(fname).decode("utf-8", errors="replace")
            self._records_cache[ck] = text
            return text
        key = self._page_index.get(doc_key)
        if key is None:
            self._records_cache[ck] = None
            return None
        sch_uuid, page_id = key
        fname = f"SHEET/{sch_uuid}/{page_id}.esch"
        if fname not in self._names:
            self._records_cache[ck] = None
            return None
        text = self.zip.read(fname).decode("utf-8", errors="replace")
        self._records_cache[ck] = text
        return text

    def sheet_records(self, doc_key, doc_type=1):
        """取一页解析后的记录数组。doc_key 同 sheet_text（uuid 优先，复合标题回退）。
        .epro 的 COMPONENT a[2] 是符号 uuid 引用（非 V2 的标题字符串），
        这里归一化为空串，实例名由 parse_sheet 从 Name 属性兜底。"""
        ck = (doc_key, doc_type)
        if ck in self._records_cache:
            cached = self._records_cache[ck]
            if isinstance(cached, list):
                return cached
        text = self.sheet_text(doc_key, doc_type)
        if text is None:
            return None
        records = []
        for line in text.splitlines():
            try:
                a = json.loads(line)
            except Exception:
                continue
            if isinstance(a, list) and len(a) > 2 and a[0] == "COMPONENT":
                a = list(a)
                a[2] = ""
            records.append(a)
        self._records_cache[ck] = records
        return records

    PCB_SUPPORT = True

    def pcb_docs(self):
        """project.json pcbs: {uuid: 文件名(.brd)}；文件名即用户可见标题。"""
        return [(u, t or u) for u, t in self.obj.get("pcbs", {}).items()]

    def symbol_records(self, symbol_uuid):
        if not symbol_uuid:
            return None
        fname = f"SYMBOL/{symbol_uuid}.esym"
        if fname not in self._names:
            return None
        text = self.zip.read(fname).decode("utf-8", errors="replace")
        arrs = []
        for line in text.splitlines():
            try:
                a = json.loads(line)
            except Exception:
                continue
            if isinstance(a, list):
                arrs.append(a)
        return arrs

    def device_map(self):
        if self._dmap_cache is not None:
            return self._dmap_cache
        out = {}
        for uuid, dev in self._devices.items():
            if not isinstance(dev, dict):
                continue
            attrs = dev.get("attributes") or {}
            # display 位（型号列）优先取 MPN 类属性，Supplier Part 仅作兜底
            disp = ""
            for k in ("Manufacturer Part", "Manufacturer Part Number",
                      "MPN", "Part Number", "Supplier Part"):
                if attrs.get(k):
                    disp = attrs[k]
                    break
            out[uuid] = (dev.get("title") or "", disp,
                         attrs.get("Description") or dev.get("description") or "")
        for uuid, sym in self._symbols.items():
            if not isinstance(sym, dict) or uuid in out:
                continue
            out[uuid] = (sym.get("title") or "", "", "")
            self._dmap_cache = out
        return out

    def cbb_symbol_board_map(self):
        """CBB 黑盒精确映射（.epro 单文件即可，无需组合文件）：
        project.json.symbols[黑盒uuid].title == 模板板名（立创EDA 导入时的
        还原机制）。键 = 实例 Symbol 属性值（uuid），值 = 板名。"""
        if self._cbb_sym_map is None:
            m = {}
            for u, sym in self._symbols.items():
                if not isinstance(sym, dict):
                    continue
                t = sym.get("title") or ""
                if sym.get("docType") == 17 or (t and t in self._boards):
                    m[u] = t
            self._cbb_sym_map = m
        return self._cbb_sym_map

    def datasheet_rows(self):
        rows = []
        for uuid, dev in self._devices.items():
            if not isinstance(dev, dict):
                continue
            url = (dev.get("attributes") or {}).get("Datasheet")
            if url:
                d = self.device_map().get(uuid, ("", "", ""))
                rows.append({"device": d[1] or d[0] or uuid, "url": url})
        return rows

    def project_title(self):
        """V2 导出：project.json 无 title 字段（.epro 不含内部工程名），
        只能靠文件名——返回 None。"""
        return None

    def hierarchy(self):
        """板 → {原理图(页), PCB}；.epro 数据完备（boards 含 schematic+pcb），
        无游离实体时 free 为空。"""
        pcb_title = {}
        for u, p in (self.obj.get("pcbs") or {}).items():
            pcb_title[u] = (p.get("title") or p.get("name") or u
                            if isinstance(p, dict) else str(p))
        sch_title = {u: (s.get("name") or u)
                     for u, s in self._schematics.items()}
        # 页按 板 聚合（sheets() 行 = (page_uuid, "板::页", 板名, 1)）
        pages_by_board = {}
        for pu, title, bt, _dt in self.sheets():
            pages_by_board.setdefault(bt, []).append(
                {"uuid": pu, "title": title.split("::", 1)[-1]})
        boards, used_sch, used_pcb = [], set(), set()
        for bname, b in self._boards.items():
            su = b.get("schematic")
            pu_ = b.get("pcb")
            used_sch.add(su)
            used_pcb.add(pu_)
            boards.append({
                "uuid": bname, "title": bname,
                "schematics": [{"uuid": su,
                                "title": sch_title.get(su, su or ""),
                                "pages": sorted(
                                    pages_by_board.get(bname, []),
                                    key=lambda x: natkey(x["title"]))}],
                "pcbs": ([{"uuid": pu_, "title": pcb_title.get(pu_, pu_)}]
                         if pu_ else [])})
        free_sch = [{"uuid": u, "title": sch_title.get(u, u),
                     "pages": sorted(pages_by_board.get(
                         sch_title.get(u, u), []),
                         key=lambda x: natkey(x["title"]))}
                    for u in self._schematics if u not in used_sch]
        free_pcb = [{"uuid": u, "title": pcb_title.get(u, u)}
                    for u in pcb_title if u not in used_pcb]
        return {"project": self.project_name(),
        "project_title": self.project_title(), "boards": boards,
                "free": {"schematics": free_sch, "pages": [],
                         "pcbs": free_pcb}}

    def device_attrs(self, device_uuid):
        dev = self._devices.get(device_uuid)
        if isinstance(dev, dict):
            return dict(dev.get("attributes") or {})
        return {}

    def symbol_of_device(self, device_uuid):
        if not device_uuid:
            return None
        dev = self._devices.get(device_uuid)
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
            p["name"] = names.get(pid) or numbers.get(pid) or "1"
            p["number"] = numbers.get(pid)
            p["pin_type"] = pin_types.get(pid)
        result = {"pins": list(pins.values()), "bbox": bbox,
                  "parts": sorted({p["part"] for p in pins.values()}),
                  "symbol_type": symbol_type}
        self._symbol_pin_cache[symbol_uuid] = result
        return result


class Epro2DB(SchemaBackend):
    """立创EDA ``.epro2``（V3 导出，project2.json + *.epru 增量日志）后端。

    epru 行格式 ``{header}||{body}|``：DOCHEAD 开启文档（docType BOARD/SCH/
    SCH_PAGE/SYMBOL/DEVICE/FOOTPRINT/PCB/INSTANCE/CONFIG），同 uuid 多段按
    ticket 最终一致合并。本后端把 V3 记录转换为 V2 数组模型供既有解析层
    复用：COMPONENT(x/y/rotation/isMirror)+ATTR(parentId,key,value)+
    WIRE(LINE.lineGroup 聚合为嵌套段)；坐标统一转换为 V2 语义（减 CANVAS
    原点 + Y 取反）。
    V3 特性：实例 ATTR ``Symbol``=符号文档 uuid（兼容按标题解析）；引脚名/
    号为 ATTR 键 ``Pin Name``/``Pin Number``；符号类型 = META.docType
    （17=CBB/18=电源/19=NetPort/22=Short/25=OffPage）；CBB 黑盒 title 即
    模板板名，source 指外部工程。"""

    FORMAT_NAME = "立创EDA .epro2（V3 ZIP 导出）"

    def __init__(self, path):
        super().__init__(path)
        self.zip = zipfile.ZipFile(self.path)
        eprus = [n for n in self.zip.namelist() if n.endswith(".epru")]
        if not eprus:
            raise ValueError(f"{path} 内无 .epru 日志")
        self.epru_name = eprus[0]
        try:
            self.pj2 = json.loads(self.zip.read("project2.json"))
        except Exception:
            self.pj2 = {}
        self._lines = None
        self._docs = {}          # uuid -> {"docType","segs":[(s,e,ticket)]}
        self._meta = {}          # uuid -> 最新 META body
        self._boards = []        # (uuid, title, sort)
        self._schs = {}          # uuid -> {"title","board"}
        self._pages = {}         # uuid -> {"title","schematic","zIndex"}
        self._rec_cache = {}
        self._text_cache = {}
        self._sym_cache = {}
        self._index()

    # -- 索引 -------------------------------------------------------------
    def _lines_of(self):
        if self._lines is None:
            data = self.zip.read(self.epru_name).decode("utf-8",
                                                        errors="replace")
            self._lines = data.split("\n")
        return self._lines

    @staticmethod
    def _jl(s):
        try:
            return json.loads(s)
        except Exception:
            return None

    def _index(self):
        lines = self._lines_of()
        cur = None
        for i, ln in enumerate(lines):
            if '"DOCHEAD"' not in ln[:30] and '"META"' not in ln[:16]:
                continue
            head, _, body = ln.partition("||")
            h = self._jl(head)
            if not h:
                continue
            t = h.get("type")
            b = self._jl(body.rstrip("|")) if t in ("DOCHEAD", "META") else None
            if t == "DOCHEAD" and b:
                u = b.get("uuid")
                if cur:
                    # 先闭合上一段（同 uuid 重开时避免旧段未闭合
                    # 吞掉文件尾部全部行）
                    self._docs[cur[0]]["segs"][-1] = \
                        (cur[1], i, cur[2])
                d = self._docs.get(u)
                if d is None:
                    d = self._docs[u] = {"docType": b.get("docType"),
                                         "segs": []}
                d["segs"].append((i, None, h.get("ticket", 0)))
                cur = (u, i, h.get("ticket", 0))
            elif t == "META" and b is not None and cur:
                old = self._meta.get(cur[0])
                if not old or h.get("ticket", 0) >= old.get("_t", 0):
                    b["_t"] = h.get("ticket", 0)
                    self._meta[cur[0]] = b
        if cur:
            self._docs[cur[0]]["segs"][-1] = (cur[1], len(lines), cur[2])
        # 结构树：BOARD / SCH(board) / SCH_PAGE(schematic)
        for u, d in self._docs.items():
            m = self._meta.get(u) or {}
            dt = d["docType"]
            if dt == "BOARD":
                self._boards.append((u, m.get("title") or u,
                                     m.get("zIndex") or 0))
            elif dt == "SCH":
                self._schs[u] = {"title": m.get("title") or u,
                                 "board": m.get("board")}
            elif dt == "SCH_PAGE":
                self._pages[u] = {"title": m.get("title") or u,
                                  "schematic": m.get("schematic") or m.get("schematic_uuid"),
                                  "zIndex": m.get("zIndex") or 0}
        self._boards.sort(key=lambda x: x[2])

    def _iter_doc_lines(self, uuid):
        """聚合某文档全部段，并按 V3 增量日志语义合并：同 (type,id) 记录
        以 (段序, ticket) 双键取最新——ticket 在各段内独立计数，不能全局
        比较；否则历史编辑轨迹叠加（新旧 LINE 全聚进同一 WIRE）或误覆盖。"""
        d = self._docs.get(uuid)
        if not d:
            return iter(())
        lines = self._lines_of()
        best = {}
        seq = 0
        for si, (s, e, _t) in enumerate(d["segs"]):
            for ln in lines[s:e]:
                head, _, _body = ln.partition("||")
                h = self._jl(head)
                if not h:
                    continue
                key = (h.get("type"), str(h.get("id")))
                rank = (si, h.get("ticket", 0))
                old = best.get(key)
                if old is None or rank >= old[0]:
                    seq += 1
                    best[key] = (rank, seq, ln)
        merged = [v[2] for v in sorted(best.values(), key=lambda x: x[1])]
        return iter(merged)

    # -- duck-typed API ----------------------------------------------------
    def schematics(self):
        return [(u, t, t) for u, t, _ in self._boards]

    def schem_map(self):
        return {t: (t, t) for _, t, _ in self._boards}

    def sheets(self, doc_type=1):
        sch_board = {u: s["board"] for u, s in self._schs.items()}
        board_title = {u: t for u, t, _ in self._boards}
        # CBB 模板等 SCH 无 board 归属：以 SCH 标题（去 .sch 后缀）匹配
        # 同名 BOARD，匹配不到则 SCH 标题自作为板名
        board_titles = {t for _, t, _ in self._boards}
        sch_fallback = {}
        for u, s in self._schs.items():
            if not s["board"]:
                t = re.sub(r"\.sch.*$", "", s["title"] or "")
                sch_fallback[u] = t if t in board_titles else (s["title"] or u)
        rows = []
        for pu, p in self._pages.items():
            su = p["schematic"]
            bt = board_title.get(sch_board.get(su)) \
                or sch_fallback.get(su) or "?"
            rows.append((pu, f"{bt}::{p['title']}", bt, 1))
        rows.sort(key=lambda r: r[1])
        return rows

    def sheet_text(self, doc_key, doc_type=1):
        recs = self.sheet_records(doc_key)
        if recs is None:
            return None
        return "\n".join(json.dumps(r, ensure_ascii=False) for r in recs)

    def sheet_records(self, doc_key, doc_type=1):
        """V3 记录 -> V2 数组模型（COMPONENT/ATTR/WIRE 顺序输出，
        WIRE 段由 LINE.lineGroup 聚合为嵌套 [[x1,y1,x2,y2],...]）。
        TEXT 行（设计注释）一并转换。doc_type=3 时解析 PCB 文档并转换为
        V2 PCB 布局模型（ATTR key/value 在 [7]/[8]，与 LcedaDB 一致）。"""
        ck = (doc_key, doc_type)
        if ck in self._rec_cache:
            return self._rec_cache[ck]
        if doc_key not in self._docs:
            return None
        # 契约：doc_type=1 只服务原理图页——PCB/INSTANCE 等文档走
        # 各自路径（doc_type=3 / symbol_records），防误当 SCH 解析
        if doc_type == 1 and self._docs[doc_key].get("docType") \
                not in ("SCH_PAGE", None):
            self._rec_cache[ck] = None
            return None
        if doc_type == 3:
            out = []
            for ln in self._iter_doc_lines(doc_key):
                head, _, body = ln.partition("||")
                h = self._jl(head)
                if not h:
                    continue
                b = self._jl(body.rstrip("|")) or {}
                t = h.get("type")
                if t == "COMPONENT":
                    attrs = b.get("attrs")
                    # 官方 PCB COMPONENT 布局(PCB文档格式 §10.1)：
                    # [id,分组(2),层(3),X(4),Y(5),旋转(6),属性(7),锁定(8)]
                    out.append(["COMPONENT", h.get("id"), 0,
                                b.get("layerId") or 0,
                                b.get("x") or 0, b.get("y") or 0,
                                b.get("angle") or 0,
                                attrs if isinstance(attrs, dict) else {},
                                0])
                elif t == "ATTR":
                    k, v = b.get("key"), b.get("value")
                    if k and v is not None:
                        out.append(["ATTR", h.get("id") or "", "",
                                    b.get("parentId") or "", "",
                                    None, None, str(k), str(v)])
                elif t == "NET":
                    try:
                        nm = json.loads(h.get("id") or "null")[1]
                    except Exception:
                        nm = None
                    if nm:
                        out.append(["NET", nm])
                elif t == "PAD_NET":
                    try:
                        cid, pin, pad = (json.loads(h.get("id"))or [None]*4)[1:4]
                    except Exception:
                        cid = pin = pad = None
                    out.append(["PAD_NET", cid, pin,
                                b.get("padNet") or "", pad])
            self._rec_cache[ck] = out
            return out
        comps, attrs, wires, texts = [], [], {}, []
        # 页 CANVAS 原点（V3 符号/页坐标需先减原点再翻转 Y）
        ox = oy = 0.0
        for ln in self._iter_doc_lines(doc_key):
            if '"CANVAS"' in ln[:18]:
                b = self._jl(ln.partition("||")[2].rstrip("|")) or {}
                ox = b.get("originX") or 0
                oy = b.get("originY") or 0
                break
        for ln in self._iter_doc_lines(doc_key):
            head, _, body = ln.partition("||")
            h = self._jl(head)
            if not h:
                continue
            b = self._jl(body.rstrip("|"))
            if b is None:
                continue
            t = h.get("type")
            if t == "COMPONENT":
                cid = h.get("id")
                # a[2](title 位)放 partId：V3 的 partId 即符号内 PART 名
                # （如 "OPA2189ID.2"），比 Name 属性更完备可靠。
                # V3 为 Y 向上坐标系：先减 CANVAS 原点，再统一 Y 取反翻转
                # 为 V2 的 Y 向下语义。
                comps.append(["COMPONENT", cid, b.get("partId") or "",
                              (b.get("x") or 0) - ox,
                              -((b.get("y") or 0) - oy),
                              b.get("rotation") or 0,
                              1 if b.get("isMirror") else 0, {}, 0])
                for k, v in (b.get("attrs") or {}).items():
                    if v:
                        attrs.append(["ATTR", "", cid, k, str(v)])
            elif t == "ATTR":
                pid = b.get("parentId") or ""
                k = b.get("key")
                v = b.get("value")
                if k == "NO_CONNECT" and pid:
                    # V3 的 NO_CONNECT parentId 为 "实例cid-引脚id"（横杠复合），
                    # 归一化为 V2 的直接拼接形式供 parse_sheet 匹配
                    pid = pid.replace("-", "")
                if k and v is not None:
                    attrs.append(["ATTR", h.get("id") or "", pid, k, str(v)])
            elif t == "WIRE":
                wid = h.get("id")
                wires.setdefault(wid, [])
            elif t == "LINE":
                g = b.get("lineGroup")
                if g:
                    wires.setdefault(g, []).append(
                        [(b.get("startX") or 0) - ox,
                         -((b.get("startY") or 0) - oy),
                         (b.get("endX") or 0) - ox,
                         -((b.get("endY") or 0) - oy)])
            elif t == "TEXT":
                v = b.get("value")
                if v:
                    texts.append(["TEXT", h.get("id") or "",
                                  (b.get("x") or 0) - ox,
                                  -((b.get("y") or 0) - oy),
                                  b.get("rotation") or 0, str(v)])
        recs = comps + attrs
        for wid, segs in wires.items():
            recs.append(["WIRE", wid,
                         [s for s in segs
                          if all(v is not None for v in s)]])
        recs.extend(texts)
        self._rec_cache[ck] = recs
        return recs

    PCB_SUPPORT = True

    def pcb_docs(self):
        return [(u, (self._meta.get(u) or {}).get("title") or u)
                for u, d in self._docs.items() if d.get("docType") == "PCB"]

    def device_map(self):
        """DEVICE 文档 META.attributes 为权威属性集；SYMBOL 文档兜底。"""
        if self._dmap_cache is not None:
            return self._dmap_cache
        out = {}
        for u, d in self._docs.items():
            if d["docType"] != "DEVICE":
                continue
            m = self._meta.get(u) or {}
            a = m.get("attributes") or {}
            disp = ""
            for k in ("Manufacturer Part", "Manufacturer Part Number",
                      "MPN", "Part Number", "Supplier Part"):
                if a.get(k):
                    disp = a[k]
                    break
            out[u] = (m.get("title") or "", disp,
                      a.get("Description") or m.get("description") or "")
        for u, d in self._docs.items():
            if d["docType"] == "SYMBOL" and u not in out:
                m = self._meta.get(u) or {}
                out[u] = (m.get("title") or "", "", "")
        # 实例 Device 值未命中 DEVICE 文档时（导出库不全），用页上实例
        # 自带属性（Manufacturer Part/LCSC Part Name/Description）合成条目
        have = set(out)
        inst_attrs = {}
        for u, d in self._docs.items():
            if d["docType"] != "SCH_PAGE":
                continue
            cur_dev = None
            ent = {}
            for ln in self._iter_doc_lines(u):
                if '"ATTR"' not in ln[:16]:
                    continue
                b = self._jl(ln.partition("||")[2].rstrip("|"))
                if not b:
                    continue
                k, v = b.get("key"), b.get("value")
                if k == "Device":
                    if cur_dev and ent:
                        inst_attrs.setdefault(cur_dev, ent)
                    cur_dev, ent = v, {}
                elif cur_dev is not None and k in (
                        "Manufacturer Part", "LCSC Part Name",
                        "Description", "Supplier Part"):
                    ent[k] = v
            if cur_dev and ent:
                inst_attrs.setdefault(cur_dev, ent)
        for du, ent in inst_attrs.items():
            if du and du not in have:
                disp = (ent.get("Manufacturer Part")
                        or ent.get("LCSC Part Name") or "")
                out[du] = ("", disp, ent.get("Description") or "")
        self._dmap_cache = out
        return out

    def device_attrs(self, device_uuid):
        m = self._meta.get(device_uuid)
        if m and isinstance(m.get("attributes"), dict):
            return dict(m["attributes"])
        return {}

    def symbol_of_device(self, device_uuid):
        """V3 桥接：DEVICE META.attributes['Symbol'] = 符号文档 uuid
        （部分实例缺 Symbol 属性时，靠此桥接解析引脚）。"""
        m = self._meta.get(device_uuid)
        if m:
            return (m.get("attributes") or {}).get("Symbol") or None
        return None

    def datasheet_rows(self):
        rows = []
        for u, d in self._docs.items():
            if d["docType"] != "DEVICE":
                continue
            m = self._meta.get(u) or {}
            url = (m.get("attributes") or {}).get("Datasheet")
            if url:
                dm = self.device_map().get(u, ("", "", ""))
                rows.append({"device": dm[1] or dm[0] or u, "url": url})
        return rows

    def project_title(self):
        """V3 导出：project2.json.title 为用户命名工程名。"""
        return self.pj2.get("title") or None

    def hierarchy(self):
        """板 → {原理图(页), PCB}；游离判定：SCH 无 board 且标题匹配不到
        同名 BOARD（CBB 模板按标题归板）；PCB META.board 为空 → 游离。"""
        board_uuid_title = {u: t for u, t, _ in self._boards}
        board_titles = set(board_uuid_title.values())
        sch_of_board = {}
        free_sch = []
        for u, s in self._schs.items():
            bt = board_uuid_title.get(s["board"])
            if not bt:
                t = re.sub(r"\.sch.*$", "", s["title"] or "")
                bt = t if t in board_titles else None
            entry = {"uuid": u, "title": s["title"] or u}
            if bt:
                sch_of_board.setdefault(bt, []).append(
                    (s.get("zIndex") or 0, entry))
            else:
                free_sch.append(entry)
        pages_by_sch = {}
        for pu, p in self._pages.items():
            pages_by_sch.setdefault(p["schematic"], []).append(
                {"uuid": pu, "title": p["title"]})
        pcb_meta = {u: (self._meta.get(u) or {})
                    for u, d in self._docs.items() if d["docType"] == "PCB"}
        boards = []
        claimed_pcb = set()
        for bu, bt, _z in self._boards:
            slst = []
            for _z, e in sorted(sch_of_board.get(bt, []),
                                key=lambda x: x[0]):
                e["pages"] = sorted(pages_by_sch.get(e["uuid"], []),
                                    key=lambda x: natkey(x["title"]))
                slst.append(e)
            plst = [{"uuid": u, "title": (m.get("title") or u)}
                    for u, m in sorted(pcb_meta.items())
                    if m.get("board") == bu]
            claimed_pcb.update(e["uuid"] for e in plst)
            boards.append({"uuid": bu, "title": bt,
                           "schematics": slst, "pcbs": plst})
        for e in free_sch:
            e["pages"] = sorted(pages_by_sch.get(e["uuid"], []),
                                key=lambda x: natkey(x["title"]))
        free_pcbs = [{"uuid": u, "title": (m.get("title") or u)}
                     for u, m in sorted(pcb_meta.items())
                     if u not in claimed_pcb]
        return {"project": self.project_name(),
        "project_title": self.project_title(), "boards": boards,
                "free": {"schematics": free_sch, "pages": [],
                         "pcbs": free_pcbs}}

    def symbol_pins(self, symbol_uuid):
        """SYMBOL 文档 -> 引脚表。键：ATTR 'Pin Name'/'Pin Number'/'Pin Type'
        （parentId=PIN id）；symbol_type 仅 CBB 黑盒可判（META docType=17）。
        symbol_uuid 实参兼容 文档uuid / 符号标题（V3 实例 Symbol 属性值为
        标题，同 title 多版本取最新 ticket 的文档）。"""
        if not symbol_uuid:
            return None
        if symbol_uuid in self._sym_cache:
            return self._sym_cache[symbol_uuid]
        result = {"pins": [], "bbox": None, "parts": [],
                  "symbol_type": None}
        d = self._docs.get(symbol_uuid)
        if d is None:
            # 标题 -> 最新文档 uuid 解析
            su = self._sym_uuid_by_title(symbol_uuid)
            d = self._docs.get(su) if su else None
            if d is not None:
                self._sym_cache[symbol_uuid] = self.symbol_pins(su)
                return self._sym_cache[symbol_uuid]
        meta = self._meta.get(symbol_uuid) or {}
        if d is None or d["docType"] != "SYMBOL":
            self._sym_cache[symbol_uuid] = result
            return result
        # V3 符号类型 = META.docType：17=CBB / 18=电源 / 19=NetPort /
        # 22=Short 短接符 / 25=Off-Page 跨页连接器（按 NetPort 语义处理）/
        # 2=普通器件符号
        mdt = meta.get("docType")
        if mdt in (17, 18, 19, 22):
            result["symbol_type"] = mdt
        elif mdt == 25:
            result["symbol_type"] = 19
        pins = {}
        names, numbers, ptypes = {}, {}, {}
        parts = []
        bbox = None
        # 符号 CANVAS 原点：V3 引脚坐标先减原点再翻转 Y（与页同规则）
        ox = oy = 0.0
        for ln in self._iter_doc_lines(symbol_uuid):
            if '"CANVAS"' in ln[:18]:
                b = self._jl(ln.partition("||")[2].rstrip("|")) or {}
                ox = b.get("originX") or 0
                oy = b.get("originY") or 0
                break
        for ln in self._iter_doc_lines(symbol_uuid):
            head, _, body = ln.partition("||")
            h = self._jl(head)
            if not h:
                continue
            b = self._jl(body.rstrip("|"))
            if b is None:
                continue
            t = h.get("type")
            if t == "PART":
                pid = h.get("id")
                parts.append(pid)
                bb = b.get("BBOX")
                if bb and len(bb) == 4 and bbox is None:
                    bbox = [min(bb[0], bb[2]), min(bb[1], bb[3]),
                            max(bb[0], bb[2]), max(bb[1], bb[3])]
            elif t == "PIN":
                pins[h.get("id")] = {
                    "id": h.get("id"),
                    "x": (b.get("x") or 0) - ox,
                    "y": -((b.get("y") or 0) - oy),
                    "rot": b.get("rotation") or 0,
                    "part": b.get("partId"), "name": None,
                    "number": None, "pin_type": None}
            elif t == "ATTR":
                pid = b.get("parentId")
                k = b.get("key")
                if pid in pins:
                    if k == "Pin Name":
                        names[pid] = b.get("value")
                    elif k == "Pin Number":
                        numbers[pid] = str(b.get("value"))
                    elif k == "Pin Type":
                        ptypes[pid] = b.get("value")
        for pid, p in pins.items():
            p["name"] = names.get(pid) or numbers.get(pid) or "1"
            p["number"] = numbers.get(pid)
            p["pin_type"] = ptypes.get(pid)
        result["pins"] = list(pins.values())
        result["parts"] = sorted(parts)
        result["bbox"] = bbox
        self._sym_cache[symbol_uuid] = result
        return result

    def _sym_uuid_by_title(self, title):
        """符号标题 -> 最新 SYMBOL 文档 uuid（懒索引，同 title 取 ticket 最大）。"""
        idx = getattr(self, "_sym_title_idx", None)
        if idx is None:
            idx = {}
            for u, d in self._docs.items():
                if d["docType"] != "SYMBOL":
                    continue
                m = self._meta.get(u) or {}
                t = m.get("title")
                if not t:
                    continue
                seg = d["segs"][-1][2] if d["segs"] else 0
                old = idx.get(t)
                if old is None or seg >= old[1]:
                    idx[t] = (u, seg)
            idx = {t: u for t, (u, _) in idx.items()}
            self._sym_title_idx = idx
        return idx.get(title)

    def cbb_instances(self):
        """V3 复用块实例唯一精确映射（INSTANCE 文档）：
        {(母图页uuid, 实例cid): {"src": 模板页uuid,
                                  "members": {模板元件cid: 母图位号}}}
        INSTANCE uuid 编码 = `<sch>_$<母图页>~<实例cid>_$<模板页>`；
        INSTANCE_ATTR.id = 模板页内元件 cid，值.Designator = 母图位号
        （实测 22/22 全中）。这是立创EDA 自身的展开对应关系，唯一无需推断。"""
        idx = getattr(self, "_cbb_inst_idx", None)
        if idx is None:
            idx = {}
            for u, d in self._docs.items():
                if d["docType"] != "INSTANCE":
                    continue
                parts = u.split("_$")
                if len(parts) < 3 or "~" not in parts[1]:
                    continue
                page = parts[1].split("~", 1)[0]
                inst_cid = parts[1].split("~", 1)[1]
                src = parts[2]
                members = {}
                for ln in self._iter_doc_lines(u):
                    if '"INSTANCE_ATTR"' not in ln[:24]:
                        continue
                    h = self._jl(ln.partition("||")[0])
                    b = self._jl(ln.partition("||")[2].rstrip("|"))
                    if h and b and b.get("Designator"):
                        members[h.get("id")] = b["Designator"]
                if src:
                    idx[(page, inst_cid)] = {"src": src, "members": members}
            self._cbb_inst_idx = idx
        return idx

    def cbb_symbol_board_map(self):
        """CBB 黑盒：SYMBOL META docType=17，title 即模板板名。
        实例 Symbol 属性值 = 符号文档 uuid（V3 实测），故同时提供
        uuid 键与标题键两种映射。"""
        if self._cbb_sym_map is None:
            m = {}
            for u, d in self._docs.items():
                if d["docType"] != "SYMBOL":
                    continue
                mt = self._meta.get(u) or {}
                if mt.get("docType") == 17 and mt.get("title"):
                    m[u] = mt["title"]
                    m.setdefault(mt["title"], mt["title"])
            self._cbb_sym_map = m
        return self._cbb_sym_map


# ---------------------------------------------------------------- 格式路由

def _sniff_zip_backend(path):
    """ZIP 容器内容特征 -> 后端类（Epro2DB/EproDB/None）。"""
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
    if any(n.endswith(".epru") for n in names) or "project2.json" in names:
        return Epro2DB
    if "project.json" in names:
        return EproDB
    return None


def _decrypt_new_eprj2(path):
    """新版加密 .eprj2 → 解密 → 打包临时 .epro2 → 返回路径。
    算法: AES-128-GCM(key=project_history_<branch>.key, iv=history_data.uuid)
          → gzip 解压 → V3 epru 明文。
    详见 docs/新版eprj2格式逆向与破解.md。"""
    import tempfile
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)

    # Step 1: 找分支历史表获取密钥
    branch_tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name LIKE 'project_history_%'")]
    key_map = {}
    for tbl in branch_tables:
        for row in conn.execute(f"SELECT uuid, key FROM [{tbl}]"):
            if row[1]:
                key_map[row[0]] = row[1]

    if not key_map:
        conn.close()
        raise UnsupportedFormatError(
            f"{path}: 新版格式但未找到解密密钥（无 project_history_* 表）")

    # Step 2: 解密全部 blob
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    all_text = []
    for buuid_full, bdata in conn.execute(
            "SELECT uuid, dataStr FROM history_data ORDER BY id"):
        if not bdata:
            continue
        buuid = buuid_full.split("-")[0]
        key_hex = key_map.get(buuid)
        if not key_hex:
            continue

        blob = base64.b64decode(bdata)
        iv = bytes.fromhex(buuid[:32])
        key = bytes.fromhex(key_hex)

        aesgcm = AESGCM(key)
        compressed = aesgcm.decrypt(iv, blob, None)
        plaintext = gzip.decompress(compressed).decode("utf-8")
        all_text.append(plaintext)

    # structure 树（明文 JSON）
    st_row = conn.execute(
        "SELECT structure FROM project_structures LIMIT 1").fetchone()
    conn.close()

    if not all_text:
        raise UnsupportedFormatError(f"{path}: history_data 无可解密内容")

    merged = "\n".join(all_text)

    # Step 3: 打包为临时 .epro2
    stem = Path(path).stem
    tmpdir = tempfile.mkdtemp(prefix="lceda_decrypt_")
    outpath = os.path.join(tmpdir, stem + "_decrypted.epro2")
    with zipfile.ZipFile(outpath, "w", zipfile.ZIP_DEFLATED) as zf:
        pj2 = {"title": stem}
        if st_row:
            try:
                st = json.loads(st_row[0])
                pj2["title"] = next(iter(st.get("boards", {})),
                                    {}).get("title", stem) \
                    if isinstance(st.get("boards", {}), dict) else stem
            except Exception:
                pass
        zf.writestr("project2.json", json.dumps(pj2, ensure_ascii=False))
        zf.writestr(stem + ".epru", merged)
    return outpath


def _sniff_sqlite_backend(path):
    """SQLite 内容特征 -> 后端类（LcedaDB/Epro2DB via 解密/None）。
    新版加密格式自动解密并返回 Epro2DB。"""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "documents" not in tables:
            return None
        n_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        if n_docs:
            return LcedaDB
        if "project_structures" in tables and "history_data" in tables:
            # 新版加密格式：解密后用 Epro2DB 读取
            return "DECRYPT_NEW"
        return None
    finally:
        conn.close()


def detect_backend(path):
    """格式路由：**内容特征优先**（ZIP magic / SQLite magic + 表结构），
    扩展名仅作参考——同扩展名不同存储（如新版/旧版 .eprj2）也能正确区分。
    返回后端类或字符串 "DECRYPT_NEW"（新版加密 .eprj2 需先解密）。
    无法识别/不支持时抛 UnsupportedFormatError。
    新增格式：实现 SchemaBackend 子类 + 在此登记内容特征。"""
    p = Path(path)
    if not p.is_file():
        raise UnsupportedFormatError(f"{p}: 文件不存在")
    with open(p, "rb") as f:
        magic = f.read(16)
    if magic[:4] == b"PK\x03\x04":
        cls = _sniff_zip_backend(p)
        if cls:
            return cls
        raise UnsupportedFormatError(
            f"{p}: ZIP 容器但不含立创EDA 工程特征"
            f"（需要 project.json 或 *.epru）")
    if magic == b"SQLite format 3\x00":
        cls = _sniff_sqlite_backend(p)
        if cls:
            return cls
        raise UnsupportedFormatError(
            f"{p}: SQLite 数据库但不含立创EDA 工程特征（documents 表）")
    raise UnsupportedFormatError(
        f"{p}: 无法识别内容特征（magic={magic[:4].hex()}）。支持格式："
        f".eprj2(V2.2 SQLite) / .epro(V2 ZIP) / .epro2(V3 ZIP)")


# ---------------------------------------------------------------- 解析层

def _norm_segs(segs):
    """走线段归一化：兼容两种格式 -> [(x1,y1,x2,y2),...]
    - V2 (.eprj2) 嵌套段：[[x1,y1,x2,y2], [x2,y2,x3,y3], ...]
    - .epro 平铺点链：[x1,y1,x2,y2,y3,y3...]（相邻点成段，可多条）
      实测 .epro 一条 WIRE 的 segs 为若干平铺数组，如
      [[1425,745,1390,745,1390,735,...], [1390,735,1425,735]]。"""
    out = []
    if not isinstance(segs, list):
        return out
    for s_ in segs:
        if not isinstance(s_, list) or len(s_) < 4 or \
                not all(isinstance(v, (int, float)) for v in s_):
            continue
        if len(s_) == 4:
            out.append((s_[0], s_[1], s_[2], s_[3]))
        elif len(s_) % 2 == 0:
            pts = [(s_[i], s_[i + 1]) for i in range(0, len(s_), 2)]
            for p1, p2 in zip(pts, pts[1:]):
                out.append((p1[0], p1[1], p2[0], p2[1]))
    return out


def _is_dnp(c):
    """器件未贴装判定（实例属性）：Add into BOM=no 或 Convert to PCB=no。
    典型场景：0Ω 跳线标不上BOM 表示 DNP——两脚物理不通，不得合并网络。"""
    a = c.get("attrs") or {}
    for k, v in a.items():
        kl = str(k).strip().lower()
        vl = str(v).strip().lower()
        if vl != "no":
            continue
        if kl in ("add into bom", "convert to pcb"):
            return True
    return False


def parse_sheet(db, doc_key):
    """把一张原理图页解析为结构化 dict。doc_key 为 document uuid（或兼容的
    复合标题），sheet_records 内部会优先按 uuid 精确查。"""
    recs = db.sheet_records(doc_key)
    if recs is None:
        return None
    sheet = {"title": doc_key, "components": [], "nets": [], "attrs": {},
             "no_connect": set(), "texts": []}
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
            if name == "NO_CONNECT" and str(val).strip().lower() in ("yes", "1", "true"):
                # parentId 为 compId+pinId 复合编号（如 e130e198 = 实例 e130 + PIN e198）
                sheet["no_connect"].add(cid)
            if cid in comps:
                comps[cid]["attrs"][name] = val
            if name in ("NET", "Global Net Name"):
                net_of[cid] = val
        elif kind == "WIRE" and len(a) >= 3:
            wires.append((a[1], a[2]))
        elif kind == "TEXT" and len(a) >= 6:
            # ["TEXT", id, x, y, rot, "文本", style, flags]——设计注释
            txt = str(a[5]).strip()
            if txt:
                sheet["texts"].append({"id": a[1], "x": a[2], "y": a[3],
                                       "rot": a[4], "text": txt})
    for c in comps.values():
        a = c["attrs"]
        if a.get("Designator") is not None:
            c["designator"] = a["Designator"]
        else:
            c["designator"] = None
        c["symbol_uuid"] = a.get("Symbol")
        c["device_uuid"] = a.get("Device")
        c["net"] = net_of.get(c["cid"]) or a.get("Name")
        # .epro 的 COMPONENT a[2] 是符号 uuid 引用（EproDB 已归一化为空），
        # 实例名在 Name 属性里——title 为空时以 Name 兜底
        if not c["title"]:
            c["title"] = str(a.get("Name") or "")
        c["dnp"] = _is_dnp(c)
        # 保留有 Symbol/Device 的实例（含 short 短接符/netport 等无 title 的）
        if c["title"] or c["designator"] or c["symbol_uuid"] or c["device_uuid"]:
            sheet["components"].append(c)
    # stub 网络：NET 挂在 WIRE 上；无名 wire 保留为 net=None stub
    for wid, segs in wires:
        net = net_of.get(wid) or None
        pts = set()
        for x1, y1, x2, y2 in _norm_segs(segs):
            pts.add((x1, y1))
            pts.add((x2, y2))
        sheet["nets"].append({"net": net, "points": sorted(pts)})
    # 页标题块：以含 "@" 属性（@Board Name 等）的组件判定；兜底 cid=="e1"
    # （立创EDA 标题块通常是页内首个组件 e1，但不依赖该约定）
    tb = None
    for c in comps.values():
        if any(str(k).startswith("@") for k in c["attrs"]):
            tb = c
            break
    if tb is None and "e1" in comps:
        tb = comps["e1"]
    sheet["attrs"] = tb["attrs"] if tb else {}
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
    # 器件信息优先按 Device uuid 查（devices 表是型号/描述真源）；
    # Symbol uuid 仅作无 Device 属性实例的兜底——同一符号可被多个器件复用，
    # 按 Symbol 查会错并不同器件（实测本工程 5 个符号对应多个器件）。
    d = dev.get(c.get("device_uuid") or c.get("symbol_uuid") or "",
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
    ep = getattr(args, "eprj_paths", None)
    out(f"== SCHEMATICS（板） [工程: {ep[0] if ep else ''}] ==")
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
    ep = getattr(args, "eprj_paths", None)
    ep_s = os.path.basename(ep[0]) if ep else ""
    rows = []
    for uuid, title, sch, dt in db.sheets():
        if dt != 1:
            continue
        sheet = parse_sheet(db, uuid)
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
            out(f"[{ep_s:20s}] [{d:12s}] {title:16s} {json.dumps(info, ensure_ascii=False)}")
    if args.json:
        outj(rows)


def cmd_components(db, args):
    sn = db.schem_map()
    dev = db.device_map()
    rows = []
    for uuid, st, sch, dt in db.sheets():
        if dt != 1:
            continue
        if args.sheet and st != args.sheet and not st.endswith("::" + args.sheet):
            continue
        sheet = parse_sheet(db, uuid)
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
                sym = fr["device_uuid"] or fr["symbol_uuid"] or ""
                drec = dev.get(sym, ("", "", ""))
                out(f"{fr['designator']}\t{fr['title']}\t{drec[0]}\t{drec[1]}\t{drec[2]}")
    if args.json:
        outj(rows)


# 0Ω 跳线判定（title 与 desc 双源，精确 token 匹配）：
# - "0R"/"0Ω"/"0ohm"：0 前不能是数字/小数点（排除 10R/50R0/10Ω），R 后不能是
#   字母数字（排除 "0710RL" 的 0R 后随 L、"50R0" 的 0R 后随 0）
# - "0000"：独立 token（阻值码/封装码，如 "0Ω (0000)"），排除 MPN 内嵌
#   （如 0603WAF0000T5E 的 0000 由 desc 阻值:0Ω 判定）
ZERO_VALUE_RE = re.compile(r"(?:^|[^0-9.])0(?:\.0)?(?:Ω|ohm|R(?![A-Za-z0-9]))",
                           re.I)
ZERO_CODE_RE = re.compile(r"(?:^|[^0-9A-Za-z])0000(?![0-9A-Za-z])", re.I)


def _is_zero_ohm(title, desc="", value=None):
    """0Ω 跳线判定。优先级：Value 属性（规范字段，实测 14/14 与
    description 正则一致且更稳）> title/description 文本正则（兜底，
    老工程/导出库缺 Value attr 时仍可用）。"""
    if value is not None and str(value).strip():
        v = str(value).strip()
        if re.fullmatch(r"0([.0]*)\s*(Ω|欧|R|ohm)?", v, re.I) or v == "0":
            return True
        if ZERO_VALUE_RE.search(v) or ZERO_CODE_RE.search(v):
            return True
        # Value 明确非 0（如 10kΩ）→ 不再看 title/desc，防误判
        if re.search(r"[1-9]", v):
            return False
    t = str(title or "")
    d = str(desc or "")
    return bool(ZERO_CODE_RE.search(t) or ZERO_VALUE_RE.search(t) or
                ZERO_VALUE_RE.search(d) or ZERO_CODE_RE.search(d))


def resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp,
                           _cbb_depth=0):
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
    seglist = []
    for wid, segs in wires:
        pts = set()
        for x1, y1, x2, y2 in _norm_segs(segs):
            p1 = norm_pt((x1, y1))
            p2 = norm_pt((x2, y2))
            pts.add(p1)
            pts.add(p2)
            if p1 != p2:
                seglist.append((p1, p2))
        if not pts:
            continue
        wire_pts[wid] = pts
        for p in pts:
            parent.setdefault(p, p)
        first = next(iter(pts))
        for p in pts:
            union(p, first)

    # 2) 引脚命中点并入连通域——精确拓扑匹配（实测全工程 2933 引脚命中全部
    #    为归一化后精确重合，容差从未需要；容差吸附反而可能把悬空引脚误连
    #    到邻近走线）。三级判定：
    #    a) 引脚坐标 == 某走线端点（命名或 stub）→ 并入该点所在域；
    #    b) 引脚落在某线段中间（T 型连接，无端点）→ 与该线段两端 union；
    #    c) 都不满足 → 真悬空，不归属任何网络。
    pin_hit = {}   # (des,pin) -> [命中端点...]（重名引脚(如 VDD×5)各保留命中点，不互相覆盖）
    endp_net = {}
    endp_all = set()
    for n in sheet["nets"]:
        for px, py in n["points"]:
            npt = norm_pt((px, py))
            endp_all.add(npt)
            if n["net"] and npt not in endp_net:
                endp_net[npt] = n["net"]
    # 拓扑闭合：所有已知端点均注册为域节点（含 port_nets 补充的合成点，
    # 防止悬空端口引脚命中合成点时 domain 缺失）
    for p in endp_all:
        parent.setdefault(p, p)

    def on_segment(px, py):
        for p1, p2 in seglist:
            x1, y1 = p1
            x2, y2 = p2
            cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
            if abs(cross) <= 0.75 and \
                    min(x1, x2) - 0.01 <= px <= max(x1, x2) + 0.01 and \
                    min(y1, y2) - 0.01 <= py <= max(y1, y2) + 0.01:
                return p1, p2
        return None

    for des, plist in comp_pins.items():
        for p in plist:
            if p.get("no_connect"):
                continue
            pt = norm_pt((p["x"], p["y"]))
            if pt in endp_all:
                pin_hit.setdefault((des, pin_key(p)), []).append(pt)
                continue
            seg = on_segment(*pt)
            if seg:
                parent.setdefault(pt, pt)
                union(pt, seg[0])
                union(pt, seg[1])
                pin_hit.setdefault((des, pin_key(p)), []).append(pt)

    # 3) 0Ω 跳线 + Short Symbol(短接符 symbolType=22) 两脚物理直连合并
    #    （0Ω 判定用 title+desc 精确 token，见 _is_zero_ohm）
    #    DNP（Add into BOM=no / Convert to PCB=no）器件未贴装，两脚物理不通，
    #    不合并——两侧网络保持独立，输出以 [DNP] 标记供审计确认。
    jumpers = set()
    try:
        dmap = db.device_map() if db is not None else {}
    except Exception:
        dmap = {}
    for c in sheet["components"]:
        if c.get("dnp"):
            continue
        du = c.get("device_uuid") or c.get("symbol_uuid") or ""
        desc = dmap.get(du, ("", "", ""))[2] if du else ""
        _v = (c.get("attrs") or {}).get("Value")
        if not _v and c.get("device_uuid"):
            try:
                _v = (db.device_attrs(c["device_uuid"]) or {}).get("Value")
            except Exception:
                _v = None
        if _is_zero_ohm(c.get("title"), desc, value=_v):
            jumpers.add(c.get("designator"))
    # 位号 -> DNP 映射：除真实 Designator 外，同时映射合成位号
    # （SHORT{cid}/PORT{cid}——短接符/NetFlag 无 Designator 属性，
    #   否则 DNP 短接符查不到会被错误合并）
    des2dnp = {}
    for c in sheet["components"]:
        d = bool(c.get("dnp"))
        des2dnp[c.get("designator")] = d
        des2dnp[f"SHORT{c['cid']}"] = d
        des2dnp[f"PORT{c['cid']}"] = d
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
        if des2dnp.get(des):
            continue
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
        result[(des, pin)] = NET_SEP.join(sorted(ns))
    # 7) CBB（复用块）展开：模板内部电路按端口映射进实例网络
    if _cbb_depth < 2:
        _expand_cbb(db, sheet, comp_pins, result, _cbb_depth)
    return result


# ---------------------------------------------------------------- CBB 展开

_CBB_MAP = {}   # --cbb-map 显式映射：实例位号 -> 模板页（uuid 或页名）


def _set_cbb_map(pairs):
    for p in pairs or []:
        if "=" in p:
            k, v = p.split("=", 1)
            _CBB_MAP[k.strip()] = v.strip()


def _cbb_sig(db):
    """懒缓存：每页 -> (端口名集合, 内容指纹, 页标题)。
    端口 = symbol_type 19 且无位号实例的 title；
    内容指纹 = (位号, title, 器件型号) 排序元组——用语义身份而非 uuid，
    使内容相同的副本页（如 _old 镜像，uuid 不同）归为等价。"""
    sig = db._cbb_sig
    if sig is None:
        dmap = db.device_map()
        sig = {}
        for uuid, title, sch, dt in db.sheets():
            if dt != 1:
                continue
            sh = parse_sheet(db, uuid)
            ports = set()
            fp = []
            for c in sh["components"]:
                sym = symbol_of(db, c)
                sp = db.symbol_pins(sym) if sym else None
                st = sp.get("symbol_type") if sp else None
                if st == 19 and not c.get("designator") and c.get("title"):
                    ports.add(c["title"])
                du = c.get("device_uuid") or c.get("symbol_uuid") or ""
                fp.append((c.get("designator") or "", c.get("title") or "",
                           dmap.get(du, ("", "", ""))[1] if du else ""))
            sig[uuid] = (frozenset(ports), tuple(sorted(fp)), title)
        db._cbb_sig = sig
    return sig


def _cbb_dom(db, tmpl_uuid):
    """模板页连通域（懒缓存，嵌套 CBB 限深展开）。"""
    cache = db._cbb_dom_cache
    if cache is None:
        cache = {}
        db._cbb_dom_cache = cache
    if tmpl_uuid not in cache:
        t_sheet = parse_sheet(db, tmpl_uuid)
        t_pinc = _collect_pinmap_data(db, t_sheet, tmpl_uuid)
        if t_pinc is None:
            cache[tmpl_uuid] = {}
        else:
            cp, ws, pw, ep = t_pinc
            cache[tmpl_uuid] = resolve_nets_by_domain(
                db, t_sheet, cp, ws, pw, ep, _cbb_depth=1)
    return cache[tmpl_uuid]


def _cbb_symbol_map(db):
    """懒构建：实例 Symbol uuid -> 模板板名。
    来源 = db 同目录下各 .eprj2 的 project_structures.structure.blockSymbols
    （立创EDA 复用块登记表：uuid=黑盒符号, title=本地模板板名, source=外部
    CBB 工程引用）。.epro 导出不含该结构，但同目录常留有来源 .eprj2；
    新格式 .eprj2 的 structure 为明文 JSON，无需解密文档内容。"""
    m = db._cbb_sym_map
    if m is not None:
        return m
    m = {}
    db._cbb_sym_map = m
    try:
        import glob as _glob
        d = str(Path(db.path).parent)
        for f in sorted(_glob.glob(os.path.join(d, "*.eprj2"))):
            try:
                conn = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
                row = conn.execute(
                    "SELECT structure FROM project_structures").fetchone()
                conn.close()
                if not row or not row[0]:
                    continue
                st = json.loads(row[0])
                n0 = len(m)
                for bs in (st.get("blockSymbols") or {}).values():
                    if isinstance(bs, dict) and bs.get("uuid") and \
                            bs.get("title"):
                        m[bs["uuid"]] = bs["title"]
                if len(m) > n0:
                    print(f"[lceda_reader] 从 {Path(f).name} structure 读取 "
                          f"CBB 块符号映射 {len(m) - n0} 条", file=sys.stderr)
            except Exception:
                continue
    except Exception:
        pass
    return m


def _resolve_cbb_target(db, sig, val):
    """--cbb-map / 符号映射值解析：支持 页uuid / 页显示标题 / 板名
    （取其首页）；标题比较不区分大小写。"""
    if val in sig:
        return val
    u = resolve_page(db, val)
    if u:
        return u
    lv = str(val).lower()
    for uuid, (_ports, _fp, title) in sig.items():
        lt = str(title).lower()
        if lt == lv or lt.startswith(lv + "::"):
            return uuid
    return None


def _expand_cbb(db, sheet, comp_pins, result, depth=0):
    """CBB（复用块，symbol_type=17）展开：模板页内部连通域按"端口名"映射
    进实例引脚所在网络。
    - 实例→模板匹配链（前三级为**唯一精确映射**，无需人工指定）：
      1) --cbb-map 显式指定；
      2) V3 INSTANCE 文档（Epro2DB）：uuid 编码 `<sch>_$<母图页>~<实例cid>_$
         <模板页>`，立创EDA 自身的展开对应关系；
      3) 后端原生符号映射（.epro symbols.title / .epro2 META docType=17 /
         同目录 .eprj2 blockSymbols）——符号标题与模板板名一一对应；
      4) 端口名集合匹配（仅兜底）：**仅唯一候选才自动采用**，多候选一律
         告警跳过（副本页内容可能不同，不做等价假设）。
    - 展开条目位号：**母图位号优先**（V3 INSTANCE_ATTR 提供模板元件cid→
      母图位号映射；分析母图按母图位号，分析模板页本身自然是模板位号），
      格式 "实例位号.成员位号"；无成员映射时回退模板位号。
    - net = 模板内部网络 ∪ 端口对应父网络（NET_SEP 并集）——netlist/trace/
      netfind 的同名归并据此贯通 CBB 内部电路。
    - 模板内部桥接多端口的域会把多个父网络经展开条目连通（正确语义）。"""
    if depth >= 2 or not comp_pins:
        return
    insts = {}
    for key, plist in comp_pins.items():
        des = key if isinstance(key, str) else key[0]
        for p in plist:
            if p.get("sym_type") == 17:
                insts.setdefault(des, set()).add(p.get("pin"))
    if not insts:
        return
    sig = _cbb_sig(db)
    self_uuid = sheet.get("title")
    # 实例位号 -> cid / Symbol uuid
    cid_of, sym_uuid_of = {}, {}
    for c in sheet.get("components", []):
        if c.get("designator"):
            cid_of[c["designator"]] = c.get("cid")
            sym_uuid_of[c["designator"]] = c.get("symbol_uuid")
    inst_map = db.cbb_instances() if hasattr(db, "cbb_instances") else {}
    for des, pin_names in sorted(insts.items()):
        if not pin_names:
            continue
        tmpl = None
        members = {}
        explicit = _CBB_MAP.get(des)
        if explicit:
            tmpl = _resolve_cbb_target(db, sig, explicit)
            if tmpl is None:
                wk = ("cbb_badmap", des, explicit)
                if wk not in _WARN_ONCE:
                    _WARN_ONCE.add(wk)
                    print(f"[lceda_reader] CBB {des}: --cbb-map 指定的页 "
                          f"{explicit!r} 不存在", file=sys.stderr)
                continue
        if tmpl is None:
            # ② V3 INSTANCE 文档：母图页+实例cid -> 模板页（唯一精确）
            info = inst_map.get((self_uuid, cid_of.get(des)))
            if info and info.get("src"):
                tmpl = info["src"]
                members = info.get("members") or {}
        if tmpl is None:
            # ③ 后端原生符号映射（.epro symbols.title / .epro2 docType=17 /
            #    同目录 .eprj2 structure.blockSymbols）
            su = sym_uuid_of.get(des)
            mapped = db.cbb_symbol_board_map().get(su or "") if su else None
            if mapped is None and su:
                mapped = _cbb_symbol_map(db).get(su)
            if mapped:
                tmpl = _resolve_cbb_target(db, sig, mapped)
        if tmpl is None:
            # ④ 端口名集合匹配（兜底）：仅唯一候选自动采用——副本页内容
            #    可能不同（指纹不含连线），不做等价/多数决假设
            cands = [u for u, v in sig.items()
                     if v[0] == pin_names and u != self_uuid]
            if len(cands) == 1:
                tmpl = cands[0]
            elif len(cands) > 1:
                names = sorted(sig[u][2] for u in cands)
                wk = ("cbb_ambig", des)
                if wk not in _WARN_ONCE:
                    _WARN_ONCE.add(wk)
                    print(f"[lceda_reader] CBB {des}: 端口匹配到多个候选模板 "
                          f"{names}，无法唯一确定，未展开；请用 --cbb-map "
                          f"{des}=<页名> 指定", file=sys.stderr)
            else:
                wk = ("cbb_nomatch", des, tuple(sorted(pin_names)))
                if wk not in _WARN_ONCE:
                    _WARN_ONCE.add(wk)
                    print(f"[lceda_reader] CBB {des}: 未找到端口集匹配的"
                          f"模板页，未展开", file=sys.stderr)
        if not tmpl:
            continue
        t_dom = _cbb_dom(db, tmpl)
        if not t_dom:
            continue
        t_sheet = parse_sheet(db, tmpl)
        # 模板 designator -> 元件 cid（供母图位号映射）
        t_des2cid = {c.get("designator"): c.get("cid")
                     for c in t_sheet["components"] if c.get("designator")}
        # 模板端口名 -> 内部网络 token 集（经 PORT 合成位号反查）。
        # 端口名取 Name 属性优先（V3 实例 title 位是 partId），title 兜底。
        port_titles = {}
        for c in t_sheet["components"]:
            if not c.get("designator") and c.get("title"):
                nm = (c.get("attrs") or {}).get("Name") or c.get("title")
                port_titles[f"PORT{c['cid']}"] = nm
        port_net = {}
        for (tdes, tpin), net in t_dom.items():
            t = port_titles.get(tdes)
            if t:
                for tok in net_tokens(net):
                    port_net.setdefault(t, set()).add(tok)
        # 实例引脚 -> 父网络 token 集
        plist = next((v for k, v in comp_pins.items()
                      if (k if isinstance(k, str) else k[0]) == des), [])
        pin_parent = {}
        for p in plist:
            if p.get("sym_type") != 17:
                continue
            k = p.get("key") or p.get("pin")
            toks = set(net_tokens(result.get((des, k))))
            if toks:
                pin_parent[p["pin"]] = toks
        # 展开：模板引脚所在域触及端口内部网络 -> 并入对应父网络。
        # 条目位号 = 实例位号.成员位号（母图位号优先，回退模板位号）
        for (tdes, tpin), net in t_dom.items():
            if tdes.startswith(("PORT", "SHORT")):
                continue
            toks = set(net_tokens(net))
            if not toks:
                continue
            hit = set()
            for pname, ptoks in port_net.items():
                if (toks & ptoks) and pname in pin_parent:
                    hit |= pin_parent[pname]
            if hit:
                mdes = members.get(t_des2cid.get(tdes) or "", tdes)
                result[(f"{des}.{mdes}", tpin)] = \
                    NET_SEP.join(sorted(toks | hit))


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

    def _direct_net(p, des):
        pt = (round(p.get("x", 0), 1), round(p.get("y", 0), 1))
        if endp and pt in endp:
            return endp[pt] or ""
        return pinmap.get((des, _key(p)), "")

    dev_map = db.device_map()
    for key, plist in comp_pins.items():
        des = key if isinstance(key, str) else key[0]
        if len(plist) != 2:
            continue
        a, b = plist
        sym_types = {p.get("sym_type") for p in plist}
        title = ""
        uuid = ""
        c_dnp = False
        for c in sheet.get("components", []):
            if c.get("designator") == des:
                title = c.get("title") or ""
                uuid = c.get("device_uuid") or c.get("symbol_uuid") or ""
                c_dnp = bool(c.get("dnp"))
                break
        d = dev_map.get(uuid) if uuid else None
        device = (d[0] if d else "") or title
        is_short = 22 in sym_types
        # 0Ω 判定：Value 属性（规范字段，实例→device）优先，title+desc 兜底
        _v = (c.get("attrs") or {}).get("Value")
        if not _v and c.get("device_uuid"):
            try:
                _v = (db.device_attrs(c["device_uuid"]) or {}).get("Value")
            except Exception:
                _v = None
        is_zero = _is_zero_ohm(title, d[2] if d else "", value=_v)
        # DNP（不上BOM/不上PCB）器件未贴装：direct 恒为 False（两脚不通）
        is_dnp = bool(c_dnp)
        kind = "short" if is_short else ("jumper" if is_zero else "passive")
        net_a = _direct_net(a, des)
        net_b = _direct_net(b, des)
        rows.append({
            "designator": des,
            "kind": kind,
            "direct": (is_short or is_zero) and not is_dnp,
            "dnp": is_dnp,
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
    """按页名（+可选板名）解析页：解决同名页歧义。返回文档 uuid 或 None。
    EproDB 的页标题是 "板名::页名" 复合格式，这里做兼容匹配。
    未指定 --schematic 且存在同名页时，取第一个匹配并向 stderr 告警。"""
    target = schematic
    matches = []
    for uuid, title, sch, dt in db.sheets():
        if title == page_name or title.endswith("::" + page_name):
            if target is None:
                matches.append((uuid, sch))
            else:
                d, n = db.schem_map().get(sch, ("?", "?"))
                if target.lower() in (d.lower(), n.lower()):
                    return uuid
    if matches:
        if len(matches) > 1:
            sn = db.schem_map()
            names = "/".join(sn.get(sch, ("?", "?"))[0] or "?"
                             for _, sch in matches)
            warn_key = ("ambig_page", page_name, names)
            if warn_key not in _WARN_ONCE:
                _WARN_ONCE.add(warn_key)
                print(f"[lceda_reader] 警告: 页名 {page_name!r} 在 {names} "
                      f"中重名，未指定 --schematic，取第一个匹配",
                      file=sys.stderr)
        return matches[0][0]
    return None


def _synth_designator(db, c):
    """无 title/designator 的实例用合成 designator 保留。
    symbol_type=22 短接符无 title 无位号，两脚桥接跨网络（如 H_RESET↔RST）；
    symbol_type=18 NetFlag / 19 NetPort 为网络命名符号（端口名=网络名）。"""
    if c.get("designator"):
        return c["designator"]
    sym = symbol_of(db, c)
    sp = db.symbol_pins(sym) if sym else None
    if sp and sp.get("symbol_type") == 22:
        return f"SHORT{c['cid']}"
    if sp and sp.get("symbol_type") in (18, 19):
        return f"PORT{c['cid']}"
    return None


_WARN_ONCE = set()   # 进程级一次性告警（非90°旋转等）


def _match_part(title, parts):
    """实例 title -> 符号 PART 名。Part 名不限于 ".1/.2" 数字后缀：支持
    完整 PART 名、字母名（XC7A35T....B0/B14/GTP/POWER）以及大小写差异。"""
    title = title or ""
    if title in parts:
        return title
    m = re.search(r"\.(\d+)$", title)
    if m:
        candidate = title[:-len(m.group(0))] + "." + m.group(1)
        if candidate in parts:
            return candidate
    for candidate in parts:
        if str(candidate).lower() == title.lower():
            return candidate
    if len(parts) == 1:
        return next(iter(parts))
    for candidate in parts:
        if str(candidate).endswith(title) or title.endswith(str(candidate)):
            return candidate
    return None


def _collect_pinmap_data(db, sheet, page_name):
    """提取 cmd_pinmap/trace 共用的引脚网络数据：
    返回 (comp_pins, wires, pt_wires, endp)。
    comp_pins 键为 (designator, cid)；wires 为 [(wire_id, segs)]；
    pt_wires 为 {(x,y): set(wire_id)}；endp 为 {(x,y): net}。"""
    def np_(p):
        return (round(p[0], 1), round(p[1], 1))

    endp = {}
    pt_wires = {}
    for n in sheet["nets"]:
        nm = n["net"]
        for px, py in n["points"]:
            k = np_((px, py))
            e = endp.setdefault(k, None)
            if e is None and nm:
                endp[k] = nm
            pt_wires.setdefault(k, set())
    recs = db.sheet_records(page_name)
    wires = []
    net_of = {}
    if recs:
        for a in recs:
            if not isinstance(a, list) or len(a) < 2:
                continue
            if a[0] == 'ATTR' and len(a) >= 5 and a[3] in ('NET', 'Global Net Name'):
                net_of[a[2]] = a[4]
            elif a[0] == 'WIRE' and len(a) >= 3:
                wires.append((a[1], a[2]))
        for wid, segs in wires:
            nm = net_of.get(wid)
            for x1, y1, x2, y2 in _norm_segs(segs):
                for p in (np_((x1, y1)), np_((x2, y2))):
                    if nm and endp.get(p) is None:
                        endp[p] = nm
                    pt_wires.setdefault(p, set()).add(wid)
    comp_pins = {}
    port_cids = set()   # symbol_type 18/19 实例 cid（端口命名只对这些实例生效）
    for c in sheet["components"]:
        des = _synth_designator(db, c)
        if not des:
            continue
        sym = symbol_of(db, c)
        sp = db.symbol_pins(sym) if sym else None
        if not sp or not sp["pins"]:
            continue
        if sp.get("symbol_type") in (18, 19):
            port_cids.add(c["cid"])
        # symbol_type=22: Short 短接符；17: CBB 复用模块；18/19: NetFlag/NetPort
        # 网络命名符号。CBB 实例没有 title，但其引脚必须参与连通域分析，否则
        # CBB 与母图之间的连接会被静默漏掉；NetFlag/NetPort 引脚参与连通域，
        # 网络名以 Global Net Name 补充（见下方端口命名）。
        if not c["title"] and sp.get("symbol_type") not in (17, 18, 19, 22):
            continue
        # Part 名匹配见 _match_part（多 PART 器件按 title 选子库）。
        part = _match_part(c.get("title") or "", sp["parts"])
        if part not in sp["parts"]:
            continue
        key = (des, c["cid"])
        plist = []
        rot360 = (c.get("rot") or 0) % 360
        if rot360 % 90:
            warn_key = ("odd_rot", page_name)
            if warn_key not in _WARN_ONCE:
                _WARN_ONCE.add(warn_key)
                print(f"[lceda_reader] 警告: 页 {page_name} 存在非90°倍数旋转 "
                      f"(rot={c.get('rot')})，引脚坐标按 {rot360}° 处理可能不准",
                      file=sys.stderr)
        for p in sp["pins"]:
            if p["part"] != part:
                continue
            rx, ry = p["x"], p["y"]
            if c.get("mirror"):
                rx = -rx
            for _ in range(int(rot360 // 90)):
                rx, ry = -ry, rx
            ax, ay = c["x"] + rx, c["y"] + ry
            plist.append({
                "pin": p["name"], "number": p["number"],
                "key": p["name"],
                "x": ax, "y": ay,
                "pin_type": p.get("pin_type"),
                "sym_type": sp.get("symbol_type"),
                "no_connect": (c["cid"] + (p.get("id") or "")) in sheet["no_connect"]})
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
    # NetFlag/NetPort 端口命名：Global Net Name 挂在 18/19 实例 cid 上，若其
    # 引脚命中端点无 wire 网络名，则以端口名补充（防御 wire 无 NET 仅靠端口
    # 命名的场景；补进 sheet["nets"] 使连通域解析与 pinmap 同时生效）。
    # 只认 18/19 实例——防止普通器件偶带 NET 属性时被误当端口命名。
    port_nets = {cid: nm for cid, nm in net_of.items()
                 if nm and cid in port_cids}
    if port_nets:
        have = set()
        for n in sheet["nets"]:
            have.update((round(px, 1), round(py, 1)) for px, py in n["points"])
        by_net = {}
        for (des, cid), plist in comp_pins.items():
            nm = port_nets.get(cid)
            if not nm:
                continue
            for p in plist:
                if p.get("no_connect"):
                    continue
                pt = (round(p["x"], 1), round(p["y"], 1))
                if pt in have or endp.get(pt) is not None:
                    continue
                by_net.setdefault(nm, set()).add(pt)
        for nm, pts in by_net.items():
            sheet["nets"].append({"net": nm, "points": sorted(pts)})
            for pt in pts:
                endp[pt] = nm
                pt_wires.setdefault(pt, set())
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
    sheet = parse_sheet(db, page)
    if sheet is None:
        out(f"未找到页: {args.page}")
        return
    comp_pins, wires, pt_wires, endp = _collect_pinmap_data(
        db, sheet, page)

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
            pt = (round(ax, 1), round(ay, 1))
            net = None
            hit_pt = None
            hit_wires = set()
            wids = pt_wires.get(pt)
            if wids:
                hit_pt = pt
                hit_wires |= wids
                net = endp.get(pt) or None
            # 同物理连接点的其他器件引脚 + 同 WIRE 记录的其他端点引脚
            peers = []
            wire_peers = []
            if hit_pt:
                for (odes, ocid), plist in comp_pins.items():
                    if odes == des:
                        continue
                    for op in plist:
                        if (round(op["x"], 1), round(op["y"], 1)) == hit_pt:
                            peers.append(f"{odes}.{op.get('key') or op['pin']}")
            if hit_wires:
                wire_pts = set()
                for wid in hit_wires:
                    for w in wires:
                        if w[0] == wid:
                            for x1, y1, x2, y2 in _norm_segs(w[1]):
                                wire_pts.add((round(x1, 1), round(y1, 1)))
                                wire_pts.add((round(x2, 1), round(y2, 1)))
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
                "net": net_disp(net),
                "nets": net_tokens(net),
                "not_connected": bool(p.get("no_connect")),
                "pin_type": p.get("pin_type"),
                "peers": sorted(set(peers)),
                "wire_peers": sorted(set(wire_peers))})
        pinmap.sort(key=lambda x: natkey(x["number"] or ""))
        sym_t = None
        if comp_pins.get((des, c["cid"])):
            sym_t = comp_pins[(des, c["cid"])][0].get("sym_type")
        rows.append({"designator": des, "symbol": c["title"],
                     "symbol_type": sym_t, "dnp": bool(c.get("dnp")),
                     "pins": pinmap})
    # 连通域网络名解析：为 net 为空的引脚推断网络名（走线拓扑，无启发式噪声）
    if not args.no_domain:
        dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
        for row in rows:
            for pm in row["pins"]:
                if pm["not_connected"]:
                    continue
                if not pm["net"]:
                    key = (row["designator"], pm["pin"])
                    n = dom.get(key, "")
                    if n:
                        pm["net"] = net_disp(n)
                        pm["nets"] = net_tokens(n)
                        pm["net_inferred"] = True
    if not args.json:
        for row in rows:
            dtag = " [DNP]" if row.get("dnp") else ""
            out(f"== {row['designator']} ({row['symbol']}){dtag} ==")
            for pm in row["pins"]:
                peer = f"  <- {','.join(pm['peers'])}" if pm["peers"] else ""
                wp = f"  [wire: {','.join(pm['wire_peers'])}]" if pm["wire_peers"] else ""
                tag = "*" if pm.get("net_inferred") else ""
                nc = " [X]" if pm["not_connected"] else ""
                out(f"  {pm['pin']:12s} (#{pm['number']:>3})  {net_disp(pm['net']) or '(未命名)'}{tag}{nc}{peer}{wp}")
    if args.json:
        outj(rows)


def cmd_tree(db, args):
    """工程层级树：工程 → 板 → {原理图(页), PCB} + 游离实体。
    对应立创EDA 工程面板语义；--json 输出 hierarchy 结构。
    工程内部名称（title）仅 .epro2/新版 .eprj2 提供，其余格式靠文件名。"""
    h = db.hierarchy()
    if args.json:
        h["file"] = str(db.path)
        outj(h)
        return
    pt = h.get("project_title")
    if pt and pt != h["project"]:
        out(f"工程: {pt}（文件: {h['project']}）")
    else:
        out(f"工程: {h['project']}（内部无独立工程名，以文件名为准）")
    for b in h["boards"]:
        out(f"├─ 板: {b['title']}")
        sl = b["schematics"]
        for i, s in enumerate(sl):
            pages = ", ".join(p["title"] for p in s["pages"])
            last_sch = (i == len(sl) - 1) and not b["pcbs"]
            pre = "│   └─ " if last_sch else "│   ├─ "
            out(f"{pre}原理图: {s['title']}（{len(s['pages'])} 页: {pages}）")
        for j, p in enumerate(b["pcbs"]):
            last = j == len(b["pcbs"]) - 1
            out(f"│   {'└─ ' if last else '├─ '}PCB: {p['title']}")
    fr = h["free"]
    items = ([("原理图", s["title"],
               f"（{len(s['pages'])} 页）" if s["pages"] else "")
              for s in fr["schematics"]]
             + [("PCB", p["title"], "") for p in fr["pcbs"]])
    if items:
        out("└─ 游离（未归属板）:")
        for kind, title, extra in items:
            out(f"    {kind}: {title}{extra}")


def cmd_texts(db, args):
    """页内文本注释（TEXT 记录）：设计意图/调试备注/网络说明。
    审查原理图时必须阅读——注释常含关键设计意图（如"OE接VCC或者悬空使能"）。
    --json 输出 [{id,x,y,rot,text}]。"""
    page = resolve_page(db, args.sheet, getattr(args, "schematic", None))
    if page is None:
        out(f"未找到页: {args.sheet}")
        return
    sheet = parse_sheet(db, page)
    if sheet is None:
        out(f"未找到页: {args.sheet}")
        return
    texts = sheet.get("texts", [])
    rows = [{"id": t["id"], "x": t["x"], "y": t["y"],
             "rot": t["rot"], "text": t["text"]} for t in texts]
    if args.json:
        outj(rows)
        return
    if not rows:
        out("(无文本注释)")
        return
    for t in rows:
        pos = f"({t['x']},{t['y']})"
        out(f"  {pos:16s} {t['text']}")


def cmd_nets(db, args):
    """页内网络连接：网络名 -> 归属元件（连通域精确方案，与 pinmap 同源）。"""
    page = resolve_page(db, args.sheet, getattr(args, "schematic", None))
    if page is None:
        out(f"未找到页: {args.sheet}")
        return
    sheet = parse_sheet(db, page)
    if sheet is None:
        out(f"未找到页: {args.sheet}")
        return
    pinc = _collect_pinmap_data(db, sheet, page)
    if pinc is None:
        out(f"未找到页: {args.sheet}")
        return
    comp_pins, wires, pt_wires, endp = pinc
    dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
    # 网络 -> 元件（designator 去重合并）
    net_comps = {}
    for (des, pin), net in dom.items():
        if net:
            for tok in net_tokens(net):
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
    sheet = parse_sheet(db, page)
    if sheet is None:
        out(f"未找到页: {args.sheet}")
        return
    pinc = _collect_pinmap_data(db, sheet, page)
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
        rows.append({"designator": des, "pin": pin, "net": net_disp(net)})
        if not args.json:
            out(f"{des:10s} {pin:12s} {net_disp(net) or '(未命名)'}")
    # NO_CONNECT 引脚：不参与连通域，单独列出（标记 X，net 恒为空）
    for (des, cid), plist in sorted(comp_pins.items()):
        for p in plist:
            if not p.get("no_connect"):
                continue
            key = (des, p.get("key") or p["pin"])
            if key in seen:
                continue
            seen.add(key)
            rows.append({"designator": des, "pin": p.get("key") or p["pin"],
                         "net": "", "not_connected": True})
            if not args.json:
                out(f"{des:10s} {p.get('key') or p['pin']:12s} [X] NO_CONNECT")
    if args.json:
        outj(rows)


def is_power_net(name):
    """电源/地网名判定（trace --no-power 用）。通用规则，不绑定具体工程：
    - 含 GND（AGND/DGND/PGND/GND_1...）；
    - 电源族前缀/全名：VCC/VDD/VSS/VBUS/VBAT/VPP/VREF 及其派生
      （AVDD/DVDD/VDDA/VCCA...）；
    - 数值电压式：5V/+3.3V/-15V/24V；
    - 拆分电压式：3V3/D3V3/1V8/+2V5。
    锚定全名匹配，不误伤 3V3_EN 之类使能信号。"""
    u = str(name).upper()
    if "GND" in u:
        return True
    if u in ("VCC", "VDD", "VSS", "VBUS", "VBAT", "VPP", "VREF") or \
            u.startswith(("VCC", "VDD", "VSS", "AVDD", "AVSS", "VDDA",
                          "VSSA", "VCCA", "VCCD", "VBUS", "VBAT")):
        return True
    if re.match(r"^[+-]?\d+(?:\.\d+)?V$", u):
        return True
    if re.match(r"^[+-]?D?\d+V\d+$", u):
        return True
    return False


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
        sheet = parse_sheet(db, uuid)
        if sheet is None:
            continue
        # 复用 pinmap 的连通域引脚网络解析
        pinc = _collect_pinmap_data(db, sheet, uuid)
        if pinc is None:
            continue
        comp_pins, wires, pt_wires, endp = pinc
        dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
        # 引脚 -> 网络 反查：建 网络 -> 元件（designator 统一大写）
        pin_net_of = {}
        for (des, pin), net in dom.items():
            if net:
                for tok in net_tokens(net):
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
        for nm in sorted(cur_nets):
            if nm in visited_net:
                continue
            if args.no_power and is_power_net(nm):
                continue
            visited_net.add(nm)
            for sheet_title, des_set in net_index[nm].items():
                for nxt in sorted(des_set):
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
            sheet = parse_sheet(db, uuid)
            if sheet is None:
                continue
            pinc = _collect_pinmap_data(db, sheet, uuid)
            if pinc is None:
                continue
            comp_pins, wires, pt_wires, endp = pinc
            dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
            pin_net_of = {}
            for (des, pin), net in dom.items():
                if net:
                    for tok in net_tokens(net):
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
        for nm in sorted(cur_nets):
            nk = (di, nm)
            if nk in visited_net:
                continue
            if args.no_power and is_power_net(nm):
                continue
            visited_net.add(nk)
            for sheet_title, des_set in p["net_index"][nm].items():
                for nxt in sorted(des_set):
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
                            if args.no_power and is_power_net(nm2):
                                continue
                            visited_net.add(nk)
                            for st2, ds2 in e.items():
                                for nxt in sorted(ds2):
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
        outj(_multi_json(dbs, rows))
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
        sheet = parse_sheet(db, uuid)
        if sheet is None:
            continue
        pinc = _collect_pinmap_data(db, sheet, uuid)
        if pinc is None:
            continue
        comp_pins, wires, pt_wires, endp = pinc
        dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
        for (des, pin), net in dom.items():
            if not net:
                continue
            for tok in net_tokens(net):
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


def cmd_find(db_or_dbs, args):
    """Designator 反查：定位元件所在页/板及网络。支持多工程（--eprj 多次），
    每条命中带 eprj 索引，json 顶层含 projects 映射。"""
    dbs = db_or_dbs if isinstance(db_or_dbs, list) else [db_or_dbs]
    multi = len(dbs) > 1
    des = args.designator.upper()
    hits = []
    for di, db in enumerate(dbs):
        sn = db.schem_map()
        dev = db.device_map()
        for uuid, title, sch, dt in db.sheets():
            if dt != 1:
                continue
            sheet = parse_sheet(db, uuid)
            if sheet is None:
                continue
            pinc = None
            dom = {}
            if not args.raw:
                # 用 pinmap 连通域精确方案（替代旧 BBOX 近似，后者对经串阻/短接
                # 连接的引脚网络归属不全）
                pinc = _collect_pinmap_data(db, sheet, uuid)
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
                    hits.append({"eprj": di, "sheet": title, "schematic": d,
                                 **fr, "nets": nets})
    if not hits:
        out(f"未找到 {des}")
        return
    if args.json:
        outj(_multi_json(dbs, hits) if multi else hits)
        return
    for h in hits:
        tag = f"工程{h['eprj']} " if multi else ""
        out(f"{tag}{des}: {h['sheet']} (sch={h['schematic']})  {h['title']}  {h['device']}")
        if h.get("nets"):
            uniq = sorted({t for n in h["nets"] for t in net_tokens(n)})
            out(f"    nets: {','.join(uniq)}")


def cmd_netfind(db_or_dbs, args):
    """全局同网络查询（引脚级）：网络名 -> 所有页的 (器件, 引脚)。
    与立创EDA"网络高亮"等效——遍历全工程连通域解析，输出该网络的全部连接点。
    支持多工程（--eprj 多次）：每个工程独立查询，输出标注工程来源，不跨工程合并。
    --json 输出结构化。"""
    dbs = db_or_dbs if isinstance(db_or_dbs, list) else [db_or_dbs]
    multi = len(dbs) > 1
    if args.json and multi:
        rows_all = []
        for di, db in enumerate(dbs):
            for r in _netfind_one(db, args.net):
                r["eprj"] = f"#{di}"
                rows_all.append(r)
        outj(_multi_json(dbs, rows_all))
        return
    rows_all = []
    for di, db in enumerate(dbs):
        rows = _netfind_one(db, args.net)
        if multi:
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
        sheet = parse_sheet(db, uuid)
        if sheet is None:
            continue
        pinc = _collect_pinmap_data(db, sheet, uuid)
        if pinc is None:
            continue
        comp_pins, wires, pt_wires, endp = pinc
        dom = resolve_nets_by_domain(db, sheet, comp_pins, wires, pt_wires, endp)
        d, n = sn.get(sch, ("?", "?"))
        for (des, pin), net in dom.items():
            if net and target in [t.upper() for t in net_tokens(net)]:
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
        outj(_multi_json(dbs, results))
        return
    out("== 连接器对候选（网络名逐 pin 一致） ==")
    for r in results:
        status = "一致" if r["pin_diff"] == 0 else f"有{r['pin_diff']}差异"
        out(f"  工程{r['eprj_a']} {r['connector_a']} <-> 工程{r['eprj_b']} {r['connector_b']}: "
            f"{r['pin_common']}/{r['pin_total']} pin 网络一致 ({status})")


def _conn_pairs(db_a, db_b):
    """两工程间连接器网络映射对比，返回候选 (des_a, des_b, common, diff, total)。"""
    def conn_nets(db):
        """收集全工程连接器的网络映射。候选判定（仅产候选，最终靠网络名
        逐 pin 一致度确认）：
        - 位号前缀 H/J/P/CN/CON/XS；或器件描述含连接器关键词
          （插针/排针/排母/端子/座/header/connector——覆盖 RF1/USBC1 等
          非常规前缀）；
        - 排除合成位号 PORT*/SHORT*（NetFlag/NetPort/短接符，非物理连接器，
          否则会灌入数万假候选对）；
        - 排除 NetFlag 风格引脚名（Pin1）。"""
        res = {}
        for uuid, title, sch, dt in db.sheets():
            if dt != 1:
                continue
            sheet = parse_sheet(db, uuid)
            if sheet is None:
                continue
            pinc = _collect_pinmap_data(db, sheet, uuid)
            if pinc is None:
                continue
            comp_pins, wires, pt_wires, endp = pinc
            dom = resolve_nets_by_domain(db, sheet, comp_pins, wires,
                                         pt_wires, endp)
            dmap = db.device_map()
            descs = {}
            for c in sheet["components"]:
                if c.get("designator"):
                    du = c.get("device_uuid") or ""
                    descs[c["designator"]] = \
                        dmap.get(du, ("", "", ""))[2] if du else ""
            for (des, pin), net in dom.items():
                if not des or des.startswith(("PORT", "SHORT")):
                    continue
                if str(pin).lower().startswith("pin"):
                    continue
                is_conn = des[0] in ("H", "J", "P") or \
                    des.startswith(("CN", "CON", "XS")) or \
                    re.search(r"连接器|插针|排针|排母|端子|座|header|connector",
                              descs.get(des, ""), re.I)
                if is_conn and len(pin) <= 3:
                    res.setdefault(des, {}).setdefault(pin, set()).update(net_tokens(net) or [''])
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

def cmd_search(db_or_dbs, args):
    """跨页正则搜索。支持多工程（--eprj 多次），json 顶层含 projects 映射。"""
    dbs = db_or_dbs if isinstance(db_or_dbs, list) else [db_or_dbs]
    multi = len(dbs) > 1
    try:
        pat = re.compile(args.pattern, re.I if not args.case else 0)
    except re.error as e:
        out(f"正则无效: {e}")
        return
    rows = []
    for di, db in enumerate(dbs):
        sn = db.schem_map()
        for uuid, title, sch, dt in db.sheets():
            if dt != 1:
                continue
            text = db.sheet_text(uuid)
            if not text:
                continue
            hits = set()
            for ln in text.splitlines():
                if pat.search(ln):
                    hits.add(ln.strip()[:200])
            if hits:
                d, n = sn.get(sch, ("?", "?"))
                if args.json:
                    rows.append({"eprj": di, "sheet": title, "schematic": d,
                                 "hits": sorted(hits)})
                else:
                    tag = f"[工程{di}] " if multi else ""
                    out(f"{tag}== {title} (sch={d}) ==")
                    for h in sorted(hits):
                        out(f"  {h}")
    if args.json:
        outj(_multi_json(dbs, rows) if multi else rows)


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
        sheet = parse_sheet(db, uuid)
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
            # BOM 按 Device uuid 归并（器件真源）；无 Device 属性时退化为
            # Symbol uuid。按 Symbol 归并会把共用符号的不同器件错并成一行。
            key = c.get("device_uuid") or c.get("symbol_uuid") or ""
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


_POLAR_ANODE = {"A", "ANODE", "+", "PA"}
_POLAR_CATH = {"K", "C", "CATHODE", "-", "−", "NK"}

# 规范位号 = 字母前缀+数字（R1/LED2/USBC1…）；纯数字/缺数字/含非常规
# 字符视为不规范（实测样例：涡流 DA输出页位号就叫 "2"）
_DESIG_STD = re.compile(r"^[A-Za-z]+\d+$")


def _polar_of(name):
    """引脚名 -> 极性归一（阳极/阴极/None）。
    归一表来源：符号库实测（LED=A/K 与 A/C、极性电容=+/−、
    TVS 阵列=功能名不可归一）；数字名（BAV70 1/2/3）文件内无极性。"""
    n = str(name or "").strip().upper()
    if n in _POLAR_ANODE:
        return "阳极"
    if n in _POLAR_CATH:
        return "阴极"
    return None


def cmd_polar(db, args):
    """极性器件清单（D/LED/TVS 位号 + 引脚名含极性对的器件）：
    每器件输出各引脚的极性归一（阳极/阴极）与所在网络；引脚名
    不可归一（数字/功能名）的标"需查手册"并附 Datasheet URL。"""
    dmap = db.device_map()
    ds_url = {}
    try:
        for r in db.datasheet_rows():
            if r.get("url"):
                ds_url[r.get("device") or ""] = r["url"]
    except Exception:
        pass

    rows = []
    schem_disp = db.schem_map()   # {sch_uuid: (display, name)}
    for u, t, s, dt in db.sheets():
        if dt != 1:
            continue
        sh = parse_sheet(db, u)
        if sh is None:
            continue
        # 页所属图（SKILL 汇报规范：必须说明所在图与页——重名副本页
        # 如 schematic1/schematic1_2 靠它区分，历史残留件才不会张冠李戴）
        sd = schem_disp.get(s, (s, s))
        sch_name = sd[0] or sd[1] or s
        pinc = _collect_pinmap_data(db, sh, u)
        if not pinc:
            continue
        cp, ws, pw, ep = pinc
        try:
            dom = resolve_nets_by_domain(db, sh, cp, ws, pw, ep)
        except Exception:
            dom = {}
        for c in sh["components"]:
            des = _synth_designator(db, c)
            if not des:
                continue
            plist = cp.get((des, c["cid"]))
            if not plist:
                continue
            pre = re.match(r"^[A-Z]+", des.upper())
            prefix = pre.group(0) if pre else ""
            pin_pol = [(_polar_of(p.get("pin")), p) for p in plist]
            hit_prefix = prefix in ("D", "LED", "TVS")
            hit_pins = any(pol for pol, _ in pin_pol)
            if not (hit_prefix or hit_pins):
                continue
            du = c.get("device_uuid") or ""
            dtitle, ddisp, ddesc = dmap.get(du, ("", "", ""))
            mpn = ddisp or dtitle or c.get("title") or ""
            pins_out = []
            for pol, p in pin_pol:
                net = dom.get((des, p["key"]))
                pins_out.append({
                    "pin": p.get("pin"), "number": p.get("number"),
                    "polarity": pol,
                    "net": net if net else "",
                    "no_connect": bool(p.get("no_connect"))})
            unresolved = any(pol is None for pol, _ in pin_pol)
            url = ds_url.get(mpn) or ds_url.get(dtitle) or ""
            rows.append({
                "designator": des, "page": t, "schematic": sch_name,
                "device": mpn, "title": c.get("title") or "",
                "matched_by": "prefix" if hit_prefix else "pin-names",
                "pins": pins_out,
                "polarity_resolved": not unresolved,
                "designator_std": bool(_DESIG_STD.match(des)),
                "datasheet": url})

    rows.sort(key=lambda r: (natkey(r["designator"]), r["page"]))
    if getattr(args, "json", False):
        outj({"count": len(rows), "items": rows})
        return
    n_ok = sum(1 for r in rows if r["polarity_resolved"])
    n_bad = sum(1 for r in rows if not r["designator_std"])
    out(f"极性器件: {len(rows)} 个（引脚极性可归一 {n_ok}，"
        f"需查手册 {len(rows) - n_ok}）"
        + (f"；⚠不规范位号 {n_bad} 个" if n_bad else ""))
    for r in rows:
        out(f"\n{r['designator']}  {r['device'][:32]}  "
            f"[{r['schematic']}::{r['page']}]"
            + ("" if r["polarity_resolved"] else "  ⚠需查手册")
            + ("" if r["designator_std"] else "  ⚠位号不规范(应为字母+数字)"))
        for p in r["pins"]:
            pol = p["polarity"] or "?"
            nc = " [X]" if p["no_connect"] else ""
            out(f"   {pol}  {p['pin']}(#{p['number']}) = {p['net'] or '(空)'}"
                f"{nc}")
        if not r["polarity_resolved"] and r["datasheet"]:
            out(f"   datasheet: {r['datasheet']}")


def cmd_pcbsch(db, args):
    """PCB↔SCH 器件核对：以 COMPONENT 内联 Unique ID(ggeN) 为全局键。
    输出：位号一致 / PCB 改名(反标清单) / 仅SCH(未布局) / 仅PCB(SCH无)。"""
    try:
        pcbs = db.pcb_inventory()
    except UnsupportedFormatError as e:
        out(f"PCB 解析不可用: {e}")
        sys.exit(1)

    # SCH 侧：uid -> {designator, page}（内联 Unique ID 优先，ATTR 兜底）
    sch_by_uid = {}
    for u, title, _schem, dt in db.sheets():
        if dt != 1:
            continue
        recs = db.sheet_records(u)
        if recs is None:
            continue
        tmp = {}
        for a in recs:
            if not isinstance(a, list):
                continue
            if a and a[0] == "COMPONENT" and len(a) >= 8 \
                    and isinstance(a[7], dict):
                v = a[7].get("Unique ID")
                if v:
                    tmp.setdefault(str(a[1]), {})["_iu"] = str(v)
            elif a and a[0] == "ATTR" and len(a) >= 5:
                pid, key = str(a[2]), str(a[3])
                val = "" if a[4] is None else str(a[4])
                d = tmp.setdefault(pid, {})
                if key == "Designator":
                    d["designator"] = val
                elif key == "Unique ID" and "_iu" not in d:
                    d["uid_attr"] = val
        for d in tmp.values():
            uid = d.get("_iu") or d.get("uid_attr")
            des = d.get("designator")
            if uid and des and uid not in sch_by_uid:
                sch_by_uid[uid] = {"designator": des, "page": title}

    report = []
    renamed_total = only_pcb_total = matched_total = 0
    # 板归属（有存储关联时标注；旧 .eprj2 boards 表空 → 启发式取主板）
    pcb_board = {}
    try:
        h = db.hierarchy()
        for b in h.get("boards", []):
            for p in b.get("pcbs", []):
                pcb_board[p["uuid"]] = b["title"]
    except Exception:
        pass
    for inv in pcbs:
        puids = {}
        rows = []
        for c in inv["comps"]:
            uid, des = c["uid"], c["designator"]
            if not uid:
                continue
            puids[uid] = des
            s = sch_by_uid.get(uid)
            if s is None:
                status, sdes, spage = "only_pcb", None, None
            elif s["designator"] == des:
                status, sdes, spage = "match", s["designator"], s["page"]
            else:
                status, sdes, spage = "renamed", s["designator"], s["page"]
            rows.append({"uid": uid, "pcb": des, "sch": sdes,
                         "page": spage, "status": status,
                         "device": c["device"] or c["footprint"]})
        m = sum(1 for r in rows if r["status"] == "match")
        r = sum(1 for r in rows if r["status"] == "renamed")
        op = sum(1 for r in rows if r["status"] == "only_pcb")
        os_ = [{"uid": uid, "sch": s["designator"], "page": s["page"]}
               for uid, s in sorted(sch_by_uid.items(), key=lambda kv: natkey(kv[1]["designator"]))
               if uid not in puids]
        matched_total += m
        renamed_total += r
        only_pcb_total += op
        report.append({"pcb": inv["title"],
                       "board": pcb_board.get(inv["uuid"]),
                       "comps": len(inv["comps"]),
                       "nets": len(inv["nets"]),
                       "pads": len(inv["pads"]),
                       "matched": m, "renamed": r,
                       "only_sch": os_, "only_pcb": op,
                       "rows": rows})

    if args.json:
        outj({"sch_comps": len(sch_by_uid), "pcbs": report})
        return

    out(f"SCH 器件(uid): {len(sch_by_uid)}")
    # 多 PCB 文档（历史快照/副本）时，仅匹配数最多的主板打印
    # 仅SCH明细，其余只报数量，避免同清单重复刷屏
    main_idx = max(range(len(report)),
                   key=lambda i: report[i]["matched"]) if report else None
    for idx, rep in enumerate(report):
        bt = f"（板: {rep['board']}）" if rep.get("board") else ""
        out(f"\n== PCB「{rep['pcb']}」{bt}: 元件 {rep['comps']} 网络 "
            f"{rep['nets']} 焊盘 {rep['pads']}")
        out(f"   一致 {rep['matched']} | 改名 {rep['renamed']} | "
            f"仅PCB {rep['only_pcb']} | 仅SCH {len(rep['only_sch'])}")
        if rep["renamed"]:
            out("   PCB 反标清单 (SCH → PCB):")
            for row in rep["rows"]:
                if row["status"] == "renamed":
                    out(f"     {row['sch']:10s} → {row['pcb']:10s}"
                        f"  [{row['device'][:28]}]")
        if rep["only_sch"] and idx == main_idx:
            out(f"   仅SCH有/未布局到PCB ({len(rep['only_sch'])} 个):")
            for e in rep["only_sch"]:
                out(f"     {e['sch']:10s} [{e['page']}]")
        op_rows = [row for row in rep["rows"] if row["status"] == "only_pcb"]
        if op_rows:
            out(f"   仅PCB有/SCH中无 ({len(op_rows)} 个):")
            for row in op_rows:
                out(f"     {row['pcb']:10s} [{row['device'][:28]}]")
    if not pcbs:
        out("工程内无 PCB 文档")


# ---------------------------------------------------------------- 渲染

def _svg_esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _xf(x, y, ox, oy, rot, mirror):
    """符号相对坐标 -> 页面绝对坐标。与 _collect_pinmap_data 的引脚变换
    完全一致：先镜像 x，再按 rot 度数旋转（90° 步进等价 (x,y)->(-y,x)），
    最后平移到实例原点。"""
    if mirror:
        x = -x
    r = math.radians(rot or 0)
    c, s = math.cos(r), math.sin(r)
    return ox + x * c - y * s, oy + x * s + y * c


def _arc_pts(x1, y1, x2, y2, x3, y3, n=24):
    """三点圆弧（起点/弧上点/终点）-> 折线采样。LCEDA ARC 三点均在圆上，
    参数化折线规避 SVG sweep/large-arc 歧义；共线退化返回 None。"""
    d = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        return None
    s1 = x1 * x1 + y1 * y1
    s2 = x2 * x2 + y2 * y2
    s3 = x3 * x3 + y3 * y3
    ux = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / d
    uy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a0 = math.atan2(y1 - uy, x1 - ux)
    am = math.atan2(y2 - uy, x2 - ux)
    ae = math.atan2(y3 - uy, x3 - ux)

    def norm(t):
        while t < 0:
            t += 2 * math.pi
        while t >= 2 * math.pi:
            t -= 2 * math.pi
        return t

    dm = norm(am - a0)
    de = norm(ae - a0)
    total = dm if dm <= de else -(2 * math.pi - de)
    return [(ux + r * math.cos(a0 + total * i / n),
             uy + r * math.sin(a0 + total * i / n)) for i in range(n + 1)]


_RENDER_CFG_DEFAULTS = {
    # 全部参数的外置真源是工具目录 render_config.json（web 渲染可直接
    # fetch）；此处仅是 json 缺失时的兜底。依据标注见 json _note。
    # [实测] measure_theme.py：位号/值蓝=#000080、导线=#008800、
    # 结点=#cc0000、NC=#33cc33、符号红=#a00000（LINESTYLE 存储色）
    # [实测] measure_sizes2.py：线宽1/结点r2/NC臂3.5/默认字号10（单位）
    # [自创] dnp/fallback_box 标记为审查增强，EDA 无此显示
    "colors": {"wire": "#008800", "junction": "#cc0000",
               "nc": "#33cc33",
               "designator_fallback": "#000080",
               "value_fallback": "#000080",
               "text": "#000000", "label": "#000000",
               "dnp": "#cc00cc", "fallback": "#c0a000",
               "fallback_fill": "#fffbe6"},
    "sizes": {"default_font": 10.0, "line_width": 1.0,
              "junction_r": 2.0, "nc_arm": 3.5,
              "nc_width_factor": 1.2, "dnp_width_factor": 2.0,
              "designator_gap": 3.0, "value_gap": 10.0},
    "dash": {"1": "6 3", "2": "1 3", "3": "6 3 1 3"},
    "junction_min_wires": 3,
    "fonts": {"default_family": "Consolas, monospace"},
    "dnp": {"dasharray": "40,24", "label": "[DNP]"},
    "fallback_box": {"dasharray": "24,16"},
    "show": {"net_labels": True, "texts": True,
             "pin_names": True, "pin_numbers": False,
             "dnp": True, "nc": True, "fallback_box": True},
    "limits": {"max_labels": 500},
}


def _render_cfg(args):
    """渲染配置：默认值 <- 工具目录 render_config.json（存在则自动加载，
    类比 EDA 自身配置）<- --config 显式文件 <- 命令行开关。"""
    import copy
    cfg = copy.deepcopy(_RENDER_CFG_DEFAULTS)

    def merge(dst, src):
        for k, v in (src or {}).items():
            if str(k).startswith("_"):
                continue   # _note 等注释键不入配置
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                merge(dst[k], v)
            else:
                dst[k] = v

    paths = []
    auto = Path(__file__).with_name("render_config.json")
    if auto.exists():
        paths.append(auto)
    p = getattr(args, "config", None)
    if p:
        paths.append(Path(p))
    for pp in paths:
        try:
            merge(cfg, json.loads(pp.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[lceda_reader] 渲染配置 {pp} 解析失败({e})，忽略",
                  file=sys.stderr)
    if getattr(args, "no_labels", False):
        cfg["show"]["net_labels"] = False
    if getattr(args, "no_texts", False):
        cfg["show"]["texts"] = False
    if getattr(args, "pin_numbers", False):
        cfg["show"]["pin_numbers"] = True
    return cfg


def _font_of(fs_map, sid, cfg):
    """FONTSTYLE 引用 -> {size,color,bold,italic,halign,valign}。
    官方布局(原理图文档格式.pdf §2.1.1)：
    [id,颜色(2),背景色(3),字体名(4),大小(5),斜体(6),加粗(7),下划线(8),
     删除线(9),垂直对齐(10):0顶/1中/2底,水平对齐(11):0左/1中/2右]"""
    st = fs_map.get(sid) or {}
    return {
        "size": st.get("size") or cfg["sizes"]["default_font"],
        "color": st.get("color") or "#000000",
        "bold": bool(st.get("bold")),
        "italic": bool(st.get("italic")),
        "halign": st.get("halign"),
        "valign": st.get("valign"),
    }


def _parse_fs(a):
    """FONTSTYLE 记录 -> dict（字段语义见 _font_of，实测空值多=继承默认）。"""

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return {"color": a[2] if len(a) > 2 and a[2] else None,
            "family": a[4] if len(a) > 4 else None,
            "size": num(a[5]) if len(a) > 5 else None,
            "italic": a[6] if len(a) > 6 else None,
            "bold": a[7] if len(a) > 7 else None,
            "valign": num(a[10]) if len(a) > 10 else None,
            "halign": num(a[11]) if len(a) > 11 else None}


def cmd_render(db, args):
    """原理图页 -> SVG。
    坐标系（实证 2026-08-23）：文件为 **Y 向上**——EDA 中标题栏在图纸右下、
    直出 SVG（Y 向下）会整页上下镜像跑到右上；故渲染统一 Y 取反、
    rotate 角度取负。引脚桩方向 (cos rot, sin rot)*len 指向体内
    （DAC8562 符号全引脚实测，见 probes/dbg_pin_dir.py）。
    字体/文字位置取自工程存储：FONTSTYLE 样式表 + 实例 ATTR 显示坐标
    （官方规则 §2.3：未显示过的属性 X/Y 为 null），不做发明式排版。
    实例属性布局（§2.3）：[id,parent,key,value,showKey(5),showValue(6),
    X(7),Y(8),rot(9),styleId(10),locked(11)]。"""
    cfg = _render_cfg(args)
    page = resolve_page(db, args.sheet, getattr(args, "schematic", None))
    if page is None:
        out(f"未找到页: {args.sheet}")
        sys.exit(1)
    sh = parse_sheet(db, page)
    if sh is None:
        out(f"未找到页: {args.sheet}")
        sys.exit(1)
    recs = db.sheet_records(page) or []

    page_fs = {}
    for a in recs:
        if isinstance(a, list) and a and a[0] == "FONTSTYLE" and len(a) > 1:
            page_fs[a[1]] = _parse_fs(a)

    sym_cache = {}

    def get_sym(sym_uuid):
        """(原始记录, symbol_pins, 符号内 FS/LS 样式表)。"""
        if sym_uuid not in sym_cache:
            prims = db.symbol_records(sym_uuid) if sym_uuid else None
            sp = db.symbol_pins(sym_uuid) if sym_uuid else None
            sfs, sls = {}, {}
            for a in (prims or []):
                if not (isinstance(a, list) and a):
                    continue
                if a[0] == "FONTSTYLE" and len(a) > 1:
                    sfs[a[1]] = _parse_fs(a)
                elif a[0] == "LINESTYLE" and len(a) >= 6:
                    w = a[5]
                    try:
                        w = float(w) if w is not None else None
                    except (TypeError, ValueError):
                        w = None
                    sls[a[1]] = {"color": a[2] or "#000000",
                                 "dash": a[3], "fill": a[4], "width": w}
            sym_cache[sym_uuid] = (prims, sp, sfs, sls)
        return sym_cache[sym_uuid]

    bbox_all = [None, None, None, None]

    def grow(x, y):
        # bbox 与发射坐标同空间（SVG 的 Y 已翻转）
        y = -y
        b = bbox_all
        b[0] = x if b[0] is None else min(b[0], x)
        b[1] = y if b[1] is None else min(b[1], y)
        b[2] = x if b[2] is None else max(b[2], x)
        b[3] = y if b[3] is None else max(b[3], y)

    elems = []
    lw = cfg["sizes"]["line_width"]
    DASH = {float(k): v for k, v in cfg.get("dash", {}).items()}

    def ls_attrs(st):
        color = st.get("color", "#000000")
        dash = DASH.get(st.get("dash"))
        da = f' stroke-dasharray="{dash}"' if dash else ""
        fill = st.get("fill")
        fill_attr = fill if (isinstance(fill, str) and fill != "") \
            else "none"
        return color, da, fill_attr

    def txt(x, y, s, f, anchor=None, rot=None, fill=None):
        ha = f.get("halign")
        if anchor is None:
            anchor = {0.0: "start", 1.0: "middle",
                      2.0: "end"}.get(ha, "middle")
        va = {0.0: "text-before-edge", 1.0: "central",
              2.0: "auto"}.get(f.get("valign"), "")
        vb = f' dominant-baseline="{va}"' if va else ""
        if rot:
            rot = rot % 360
            if rot == 180:
                # EDA 行为（实测参考图）：180° 文本自动翻正保持可读，
                # 90/270 保留竖排
                rot = 0
        tr = f' transform="rotate({-rot:.0f} {x:.1f} {-y:.1f})"' \
            if rot else ""
        fw = ' font-weight="bold"' if f.get("bold") else ""
        fs_ = ' font-style="italic"' if f.get("italic") else ""
        fam = (f' font-family="{_svg_esc(f["family"])}"'
               if f.get("family") else "")
        return (f'<text x="{x:.1f}" y="{-y:.1f}" '
                f'font-size="{f["size"]:.0f}"{fw}{fs_}{fam} '
                f'fill="{fill or f["color"]}" text-anchor="{anchor}"'
                f'{vb}{tr}>{_svg_esc(s)}</text>')

    # ── 导线 / 结点 / 页文本 / 网络名（存储显示位）──
    net_of, wires = {}, []
    texts = []
    net_disp = []   # NET ATTR 自带显示位（官方同属性机制：X/Y=null=未显示）
    for a in recs:
        if not isinstance(a, list) or len(a) < 2:
            continue
        k = a[0]
        if k == "ATTR" and len(a) >= 11 and \
                a[3] in ("NET", "Global Net Name"):
            if a[4] and a[7] is not None and a[8] is not None:
                rotv = 0.0
                try:
                    rotv = float(a[9] or 0)
                except (TypeError, ValueError):
                    rotv = 0.0
                net_disp.append((float(a[7]), float(a[8]), rotv,
                                 str(a[4]), a[10]))
        elif k == "WIRE" and len(a) >= 3:
            wires.append((a[1], a[2]))
            if len(a) >= 5:
                pass
        elif k == "TEXT" and len(a) >= 7 and str(a[5]).strip():
            f = _font_of(page_fs, a[6], cfg)
            f["color"] = page_fs.get(a[6], {}).get("color") \
                or cfg["colors"]["text"]
            texts.append((a[2], a[3], a[4], str(a[5]), f))
    seg_count = {}
    for wid, segs in wires:
        for seg in _norm_segs(segs):
            x1, y1, x2, y2 = seg
            elems.append(
                f'<line x1="{x1:.1f}" y1="{-y1:.1f}" '
                f'x2="{x2:.1f}" y2="{-y2:.1f}" '
                f'stroke="{cfg["colors"]["wire"]}" stroke-width="{lw}"/>')
            grow(x1, y1)
            grow(x2, y2)
            for p in ((x1, y1), (x2, y2)):
                pt = (round(p[0], 1), round(p[1], 1))
                seg_count[pt] = seg_count.get(pt, 0) + 1

    # ── 实例属性显示信息（X/Y 非 null 才有显示位置）──
    attr_disp = {}
    for a in recs:
        if (isinstance(a, list) and a and a[0] == "ATTR" and len(a) >= 11
                and a[2] is not None):
            try:
                xr = None if a[7] is None else float(a[7])
                yr = None if a[8] is None else float(a[8])
            except (TypeError, ValueError):
                continue
            if xr is None or yr is None:
                continue
            rotv = None
            try:
                rotv = float(a[9]) if a[9] is not None else None
            except (TypeError, ValueError):
                rotv = None
            attr_disp[(str(a[2]), str(a[3]))] = {
                "x": xr, "y": yr, "rot": rotv, "sid": a[10],
                "show_key": a[5] in (1, True),
                "show_val": a[6] in (1, True)}

    # ── 元件 ──
    dmap = db.device_map()
    n_nograph = 0
    for c in sh["components"]:
        cx, cy = c["x"], c["y"]
        rot360 = int(c.get("rot") or 0) % 360
        mir = bool(c.get("mirror"))
        sym = symbol_of(db, c)
        prims, sp, sfs, sls = get_sym(sym)
        parts = (sp or {}).get("parts") or []
        part = _match_part(c.get("title"), parts) if parts else None

        draw_prims = []
        cur = None
        have_part_sec = False
        origin = [0.0, 0.0]
        pin_label_attrs = []
        # 符号模板内"已显示"的属性（X/Y 非 null）＝显示位置来源；
        # 实例同 Key 属性提供值覆盖（官方 §3.3：同名属性覆盖）。
        # 标题栏即此机制：模板存键与位置，实例只存值(X/Y=null)。
        sym_attr_disp = {}
        sym_attr_vals = {}   # 模板全部 ATTR key->value（公式兜底）
        for a in (prims or []):
            if not isinstance(a, list) or not a:
                continue
            k = a[0]
            if k == "HEAD" and len(a) > 1 and isinstance(a[1], dict):
                origin = [float(a[1].get("originX") or 0),
                          float(a[1].get("originY") or 0)]
            elif k == "PART":
                cur = a[1]
                have_part_sec = True
            elif k in ("POLY", "RECT", "CIRCLE", "ARC", "PIN", "TEXT"):
                if not have_part_sec or part is None or cur == part:
                    draw_prims.append((k, a))
            elif k == "ATTR" and len(a) >= 11 and \
                    a[3] not in ("NAME", "NUMBER"):
                if have_part_sec and part is not None and cur != part:
                    continue
                if a[3] not in sym_attr_vals:
                    sym_attr_vals[str(a[3])] = \
                        "" if a[4] is None else str(a[4])
                if a[7] is not None and a[8] is not None:
                    try:
                        sym_attr_disp[str(a[3])] = {
                            "x": float(a[7]), "y": float(a[8]),
                            "rot": float(a[9] or 0), "sid": a[10],
                            "show_key": a[5] in (1, True),
                            "show_val": a[6] in (1, True),
                            "tmpl": "" if a[4] is None else str(a[4])}
                    except (TypeError, ValueError):
                        pass
            elif k == "ATTR" and len(a) >= 12 and \
                    a[3] in ("NAME", "NUMBER"):
                if not have_part_sec or part is None or cur == part:
                    pin_label_attrs.append(a)

        def T(x, y):
            # 官方变换序（§3.3.2）：旋转 -> 镜像 -> 平移；
            # Y 翻转在 txt()/发射处统一做，此处保持文件坐标
            r = math.radians(rot360 or 0)
            cc, ss = math.cos(r), math.sin(r)
            rx_ = x * cc - y * ss
            ry_ = x * ss + y * cc
            if mir:
                rx_ = -rx_
            return cx + rx_, cy + ry_

        drew_graph = False
        comp_bbox = [None, None, None, None]

        def cgrow(x, y):
            b = comp_bbox
            b[0] = x if b[0] is None else min(b[0], x)
            b[1] = y if b[1] is None else min(b[1], y)
            b[2] = x if b[2] is None else max(b[2], x)
            b[3] = y if b[3] is None else max(b[3], y)

        for k, a in draw_prims:
            try:
                if k == "POLY" and len(a) >= 3 and isinstance(a[2], list):
                    pts = a[2]
                    xy = [T(pts[i], pts[i + 1])
                          for i in range(0, len(pts) - 1, 2)]
                    st = sls.get(a[-2], {}) if len(a) >= 5 else {}
                    closed = bool(a[3]) if len(a) > 3 else False
                    color, da, fillc = ls_attrs(st)
                    pstr = " ".join(
                        f"{px:.1f},{-py:.1f}" for px, py in xy)
                    tag = "polygon" if closed else "polyline"
                    if tag == "polyline":
                        pstr += f" {xy[0][0]:.1f},{-xy[0][1]:.1f}"
                    elems.append(
                        f'<{tag} points="{pstr}" fill="{fillc}" '
                        f'stroke="{color}" '
                        f'stroke-width="{st.get("width") or lw}"{da}/>')
                    for px, py in xy:
                        cgrow(px, py)
                    drew_graph = True
                elif k == "RECT" and len(a) >= 6:
                    rx1, ry1 = T(a[2], a[3])
                    rx2, ry2 = T(a[4], a[5])
                    st = sls.get(a[-2], {}) if len(a) >= 5 else {}
                    color, da, fillc = ls_attrs(st)
                    rrot = 0.0
                    if len(a) > 8 and a[8]:
                        try:
                            rrot = float(a[8])
                        except (TypeError, ValueError):
                            rrot = 0.0
                    rndx = 0.0
                    if len(a) > 6 and a[6]:
                        try:
                            rndx = float(a[6])
                        except (TypeError, ValueError):
                            rndx = 0.0
                    tr = (f' transform="rotate({-rrot:.0f} '
                          f'{rx1:.1f} {-ry1:.1f})"') if rrot % 360 else ""
                    elems.append(
                        f'<rect x="{min(rx1,rx2):.1f}" '
                        f'y="{-max(ry1,ry2):.1f}" '
                        f'width="{abs(rx2-rx1):.1f}" '
                        f'height="{abs(ry2-ry1):.1f}" rx="{rndx:.1f}" '
                        f'fill="{fillc}" stroke="{color}" '
                        f'stroke-width="{st.get("width") or lw}"{da}{tr}/>')
                    cgrow(rx1, ry1)
                    cgrow(rx2, ry2)
                    drew_graph = True
                elif k == "CIRCLE" and len(a) >= 5:
                    ccx, ccy = T(a[2], a[3])
                    r = float(a[4])
                    st = sls.get(a[-2], {}) if len(a) >= 5 else {}
                    color, da, fillc = ls_attrs(st)
                    elems.append(
                        f'<circle cx="{ccx:.1f}" cy="{-ccy:.1f}" '
                        f'r="{r:.1f}" fill="{fillc}" stroke="{color}" '
                        f'stroke-width="{st.get("width") or lw}"{da}/>')
                    cgrow(ccx - r, ccy - r)
                    cgrow(ccx + r, ccy + r)
                    drew_graph = True
                elif k == "ARC" and len(a) >= 9:
                    xy = _arc_pts(a[2], a[3], a[4], a[5], a[6], a[7])
                    if xy:
                        txy = [T(px, py) for px, py in xy]
                        pstr = " ".join(
                            f"{px:.1f},{-py:.1f}" for px, py in txy)
                        st = sls.get(a[-2], {}) if len(a) >= 5 else {}
                        color, da, _fc = ls_attrs(st)
                        elems.append(
                            f'<polyline points="{pstr}" fill="none" '
                            f'stroke="{color}" '
                            f'stroke-width="{st.get("width") or lw}"{da}/>')
                        for px, py in txy:
                            cgrow(px, py)
                        drew_graph = True
                elif k == "TEXT" and len(a) >= 7 and str(a[5]).strip():
                    tx_, ty_ = T(a[2], a[3])
                    f = _font_of(sfs, a[6], cfg)
                    trot = 0.0
                    try:
                        trot = float(a[4] or 0)
                    except (TypeError, ValueError):
                        trot = 0.0
                    elems.append(txt(tx_, ty_, str(a[5]), f,
                                     rot=trot if trot % 360 else None))
                    cgrow(tx_, ty_)
                    drew_graph = True
                elif k == "PIN" and sp and len(a) >= 8:
                    plen = 20.0
                    try:
                        plen = float(a[6]) if a[6] else 20.0
                    except (TypeError, ValueError):
                        plen = 20.0
                    prot = 0.0
                    try:
                        prot = float(a[7] or 0)
                    except (TypeError, ValueError):
                        prot = 0.0
                    for pp in sp["pins"]:
                        if pp["id"] != a[1]:
                            continue
                        ex, ey = T(pp["x"], pp["y"])
                        bx, by = T(pp["x"] + math.cos(math.radians(prot))
                                   * plen,
                                   pp["y"] + math.sin(math.radians(prot))
                                   * plen)
                        elems.append(
                            f'<line x1="{ex:.1f}" y1="{-ey:.1f}" '
                            f'x2="{bx:.1f}" y2="{-by:.1f}" '
                            f'stroke="#000000" stroke-width="{lw}"/>')
                        cgrow(ex, ey)
                        cgrow(bx, by)
                        if cfg["show"]["nc"] and \
                                (c["cid"] + (pp.get("id") or "")) \
                                in sh["no_connect"]:
                            s_ = cfg["sizes"].get("nc_arm", lw * 3.5)
                            nc = cfg["colors"]["nc"]
                            nw_ = cfg["sizes"].get("nc_width_factor", 1.2)
                            elems.append(
                                f'<line x1="{ex-s_:.1f}" y1="{-(ey-s_):.1f}'
                                f'" x2="{ex+s_:.1f}" y2="{-(ey+s_):.1f}" '
                                f'stroke="{nc}" stroke-width="{lw*nw_}"/>'
                                f'<line x1="{ex-s_:.1f}" y1="{-(ey+s_):.1f}'
                                f'" x2="{ex+s_:.1f}" y2="{-(ey-s_):.1f}" '
                                f'stroke="{nc}" stroke-width="{lw*nw_}"/>')
                        break
            except Exception:
                continue

        # 符号内 NAME/NUMBER 文本（官方规则：未显示过则 X/Y=null）
        want_lbl = ("NAME" if cfg["show"]["pin_names"] else "") + \
                   ("NUMBER" if cfg["show"]["pin_numbers"] else "")
        for a in pin_label_attrs:
            try:
                if a[3] not in want_lbl:
                    continue
                if a[7] is None or a[8] is None or not str(a[4]):
                    continue
                lx_, ly_ = T(float(a[7]), float(a[8]))
                prot = 0.0
                try:
                    prot = float(a[9] or 0)
                except (TypeError, ValueError):
                    prot = 0.0
                f = _font_of(sfs, a[10], cfg)
                elems.append(txt(lx_, ly_, str(a[4]), f,
                                 rot=prot if prot % 360 else None))
                cgrow(lx_, ly_)
            except Exception:
                continue

        if not drew_graph:
            n_nograph += 1
            pin_pts = []
            if sp:
                for pp in sp["pins"]:
                    if parts and pp.get("part") != part:
                        continue
                    pin_pts.append(T(pp["x"], pp["y"]))
            if pin_pts:
                xs = [p[0] for p in pin_pts]
                ys = [p[1] for p in pin_pts]
                comp_bbox = [min(xs), min(ys), max(xs), max(ys)]
            else:
                comp_bbox = [cx - 80, cy - 80, cx + 80, cy + 80]
            if cfg["show"]["fallback_box"]:
                fb = cfg["colors"]["fallback"]
                elems.append(
                    f'<rect x="{comp_bbox[0]:.0f}" '
                    f'y="{-comp_bbox[3]:.0f}" '
                    f'width="{comp_bbox[2]-comp_bbox[0]:.0f}" '
                    f'height="{comp_bbox[3]-comp_bbox[1]:.0f}" '
                    f'fill="{cfg["colors"]["fallback_fill"]}" '
                    f'stroke="{fb}" stroke-width="{lw}" '
                    f'stroke-dasharray='
                    f'"{cfg.get("fallback_box", {}).get("dasharray", "24,16")}"/>')

        # 实例属性绘制 = 符号模板显示位 ∪ 实例显示位，值按同名覆盖：
        # 位置优先级：实例 attr_disp > 模板 sym_attr_disp；
        # 文本 = showKey/showValue 决定画键/值（值取实例优先，模板兜底）
        des = c.get("designator")
        dev_desc = dmap.get(c.get("device_uuid") or "", ("", "", ""))[2]
        inst_val = c["attrs"].get("Value")
        val = inst_val or parse_value(dev_desc).get("value") or ""
        pend_des = bool(des)
        pend_val = bool(val)

        dev_attrs = {}
        if c.get("device_uuid"):
            try:
                dev_attrs = db.device_attrs(c["device_uuid"]) or {}
            except Exception:
                dev_attrs = {}

        def resolve(text_v):
            """属性公式（官方 Name='={Value}' 实证 32 例）：
            ={Key} 整体引用 / {Key} 内联引用；解析链 实例attrs->
            device attrs->符号模板值；解析失败保留字面。"""
            if not isinstance(text_v, str) or "{" not in text_v:
                return text_v

            def lookup(k):
                v = c["attrs"].get(k)
                if v is None or str(v) == "":
                    v = dev_attrs.get(k)
                if v is None or str(v) == "":
                    v = sym_attr_vals.get(k)
                return None if v is None else str(v)

            m = re.fullmatch(r"=\{([^{}]+)\}", text_v)
            if m:
                v = lookup(m.group(1))
                return v if v is not None else text_v
            return re.sub(r"\{([^{}]+)\}",
                          lambda mm: lookup(mm.group(1))
                          if lookup(mm.group(1)) is not None
                          else mm.group(0), text_v)

        def draw_one(key, text_v, pos, sid, sk, sv, rot, local=False):
            text_v = resolve(text_v)
            if text_v is None or str(text_v) == "":
                return False
            parts_txt = []
            if sk:
                parts_txt.append(str(key))
            if sv:
                parts_txt.append(str(text_v))
            if not parts_txt:
                return False
            # 样式 ID 每文档独立：模板属性(local)用符号 sfs 表，
            # 实例属性用页 page_fs 表——混用会取到错误字号/颜色
            fs_tab = sfs if local else page_fs
            f = _font_of(fs_tab, sid, cfg)
            f["color"] = fs_tab.get(sid, {}).get("color") or "#000000"
            label = (str(key) + "=" + parts_txt[1]) \
                if (sk and sv and len(parts_txt) > 1) else parts_txt[0]
            px_, py_ = (pos["x"], pos["y"])
            if local:
                # 模板显示位是符号局部坐标，必须过实例变换
                px_, py_ = T(pos["x"], pos["y"])
                rot = (rot or 0) + rot360
            elems.append(txt(px_, py_, label, f,
                             rot=rot if rot % 360 else None))
            grow(px_, py_)
            return True

        merged_keys = set(sym_attr_disp.keys()) | set(c["attrs"].keys())
        merged_keys.add("Designator")
        for key in sorted(merged_keys):
            inst_info = attr_disp.get((c["cid"], str(key)))
            tmpl = sym_attr_disp.get(str(key))
            text_v = c["attrs"].get(key)
            if key == "Designator":
                text_v = des
            elif key == "Value" and text_v is None:
                text_v = val
            if key == "Symbol" or key == "Device":
                # uuid 绑定属性不作为文本画（模板里通常也未显示）
                continue
            if inst_info is not None:
                ok = draw_one(key, text_v, inst_info,
                              inst_info["sid"], inst_info["show_key"],
                              inst_info["show_val"],
                              inst_info["rot"] or 0, local=False)
            elif tmpl is not None:
                v = text_v if text_v not in (None, "") else tmpl["tmpl"]
                ok = draw_one(key, v, tmpl, tmpl["sid"],
                              tmpl["show_key"], tmpl["show_val"],
                              tmpl["rot"], local=True)
            else:
                continue
            if ok:
                if key == "Designator":
                    pend_des = False
                if key == "Value":
                    pend_val = False
        if comp_bbox[0] is not None and (pend_des or pend_val):
            mx = (comp_bbox[0] + comp_bbox[2]) / 2
            df = {"size": cfg["sizes"]["default_font"],
                  "color": cfg["colors"]["designator_fallback"],
                  "bold": True, "italic": False, "halign": 1.0,
                  "valign": 2.0}
            if pend_des:
                elems.append(txt(mx, comp_bbox[1] - lw * 2, des, df))
                grow(comp_bbox[0], comp_bbox[1] - lw * 6)
                grow(comp_bbox[2], comp_bbox[1])
            if pend_val:
                vf = {"size": cfg["sizes"]["default_font"],
                      "color": cfg["colors"]["value_fallback"],
                      "bold": False, "italic": False,
                      "halign": 1.0, "valign": 0.0}
                elems.append(txt(mx, comp_bbox[3] + lw * 8, val, vf))
                grow(comp_bbox[0], comp_bbox[3] + lw * 10)
                grow(comp_bbox[2], comp_bbox[3])
        if cfg["show"]["dnp"] and c.get("dnp") \
                and comp_bbox[0] is not None:
            dc = cfg["colors"]["dnp"]
            elems.append(
                f'<rect x="{comp_bbox[0]:.0f}" y="{-comp_bbox[3]:.0f}" '
                f'width="{comp_bbox[2]-comp_bbox[0]:.0f}" '
                f'height="{comp_bbox[3]-comp_bbox[1]:.0f}" fill="none" '
                f'stroke="{dc}" '
                f'stroke-width="{lw*cfg["sizes"].get("dnp_width_factor", 2)}" '
                f'stroke-dasharray="'
                f'{cfg.get("dnp", {}).get("dasharray", "40,24")}"/>')
            elems.append(txt(comp_bbox[0], comp_bbox[3] + lw * 20,
                             cfg.get("dnp", {}).get("label", "[DNP]"),
                             {"size": cfg["sizes"]["default_font"],
                              "color": dc, "bold": True, "italic": False}))
        for x, y in ((comp_bbox[0], comp_bbox[1]),
                     (comp_bbox[2], comp_bbox[3])):
            if x is not None:
                grow(x, y)

    # ── 结点 / 网络名（按存储位置）/ 页文本 ──
    jr = cfg["sizes"].get("junction_r", lw * 2)
    jmin = cfg.get("junction_min_wires", 3)
    for (px, py), n in seg_count.items():
        if n >= jmin:
            elems.insert(0,
                         f'<circle cx="{px:.0f}" cy="{-py:.0f}" '
                         f'r="{jr:.0f}" '
                         f'fill="{cfg["colors"]["junction"]}"/>')
    if cfg["show"]["net_labels"]:
        for nx, ny, nrot, nm, sid in net_disp[:cfg["limits"]["max_labels"]]:
            f = _font_of(page_fs, sid, cfg)
            elems.append(txt(nx, ny, nm, f,
                             rot=nrot if nrot % 360 else None))
            grow(nx, ny)
    if cfg["show"]["texts"]:
        for tx, ty, trot, s, f in texts:
            elems.append(txt(tx, ty, s, f,
                             rot=trot if trot % 360 else None))
            grow(tx, ty)

    # ── 组装 SVG ──
    m = 300
    if bbox_all[0] is None:
        out("页面无几何内容")
        sys.exit(1)
    vx0, vy0 = bbox_all[0] - m, bbox_all[1] - m
    vw = (bbox_all[2] - bbox_all[0]) + 2 * m
    vh = (bbox_all[3] - bbox_all[1]) + 2 * m
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vx0:.0f} {vy0:.0f} {vw:.0f} {vh:.0f}" '
        f'font-family="{cfg.get("fonts", {}).get("default_family", "Consolas, monospace")}">\n'
        f'<rect x="{vx0:.0f}" y="{vy0:.0f}" width="{vw:.0f}" '
        f'height="{vh:.0f}" fill="#ffffff"/>\n'
        + "\n".join(elems) + "\n</svg>\n")

    o = getattr(args, "output", None)
    disp = sh["title"]
    for u_, t_, s_, dt_ in db.sheets():
        if u_ == page:
            disp = t_ or disp
            break
    if not o:
        safe = re.sub(r'[\\/:*?"<>|]+', "_",
                      f"{db.project_name()}_{disp}")[:80]
        o = f"{safe}.svg"
    with open(o, "w", encoding="utf-8") as f:
        f.write(svg)
    out(f"[render] 页「{disp}」: 元件 {len(sh['components'])} "
        f"(无图形退化 {n_nograph}), 导线 {len(wires)}, "
        f"网络标签 {len(net_disp)}")
    out(f"[render] 输出: {o} ({len(svg)//1024} KB)")


def cmd_datasheets(db, args):
    """提取 Datasheet URL 清单（经后端方法，LcedaDB/EproDB 均支持）。"""
    rows = db.datasheet_rows()
    if args.json:
        outj(rows)
        return
    if not rows:
        out("无 Datasheet 记录")
    for r in rows:
        out(f"{r['device']:28s} {r['url']}")


def cmd_attrs(db, args):
    page = resolve_page(db, args.sheet, getattr(args, "schematic", None))
    if page is None:
        out(f"未找到页: {args.sheet}")
        return
    sheet = parse_sheet(db, page)
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
    text = db.sheet_text(page)
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
    ap.add_argument("--cbb-map", action="append", default=None,
                    help="CBB 实例位号=模板页名（如 CBB1=_CBB_LDO_TPS7A3001_2LAYER），"
                         "端口自动匹配歧义时显式指定，可多次")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出板与页").set_defaults(fn=cmd_list)
    sub.add_parser("boards", help="列出每页的 @Board Name/@Page Name").set_defaults(fn=cmd_boards)

    p = sub.add_parser("tree", help="工程层级树: 板→原理图(页)/PCB + 游离实体")
    p.set_defaults(fn=cmd_tree)

    p = sub.add_parser("components", help="列出页内元件(设计符/型号/值)")
    p.add_argument("sheet", nargs="?", default=None)
    p.set_defaults(fn=cmd_components)

    p = sub.add_parser("texts", help="页内文本注释(设计意图/调试备注)")
    p.add_argument("sheet")
    p.add_argument("--schematic", default=None, help="指定板名解决同名页")
    p.set_defaults(fn=cmd_texts)

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

    sub.add_parser("pcbsch", help="PCB↔SCH 器件核对(Unique ID 映射: 反标/漏布局)").set_defaults(fn=cmd_pcbsch)

    p = sub.add_parser("polar", help="极性器件清单(D/LED/TVS: 阳极/阴极网络归一, 未归一附 datasheet)")
    p.set_defaults(fn=cmd_polar)

    p = sub.add_parser("render", help="原理图页渲染为 SVG(字体/文字位置取自工程存储)")
    p.add_argument("sheet")
    p.add_argument("--schematic", default=None, help="指定板名解决同名页")
    p.add_argument("-o", "--output", default=None, help="输出 SVG 路径(默认自动命名)")
    p.add_argument("--config", default=None,
                   help="渲染配置 JSON(颜色/字号/显示项)；缺省自动加载工具目录"
                        " render_config.json")
    p.add_argument("--no-labels", action="store_true", help="不画网络名标签")
    p.add_argument("--no-texts", action="store_true",
                   help="不画页内文本注释(大段说明会遮挡审查)")
    p.add_argument("--pin-numbers", action="store_true",
                   help="画引脚名/号(默认关，减少视觉噪声)")
    p.set_defaults(fn=cmd_render)

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
    _set_cbb_map(args.cbb_map)
    if args.eprj:
        paths = args.eprj
    else:
        p0 = find_eprj(None)
        paths = [p0] if p0 else []
    if not paths:
        out("未找到 .eprj2，请用 --eprj 指定路径")
        sys.exit(1)
    def open_db(p):
        result = detect_backend(p)
        if result == "DECRYPT_NEW":
            # 新版加密 .eprj2：解密 → 临时 .epro2 → Epro2DB
            print(f"[lceda_reader] 检测到新版加密 .eprj2，正在解密...", file=sys.stderr)
            decrypted_path = _decrypt_new_eprj2(p)
            print(f"[lceda_reader] 解密完成 → {decrypted_path}",
                  file=sys.stderr)
            return Epro2DB(decrypted_path)
        print(f"[lceda_reader] 格式: {result.FORMAT_NAME} | 文件: {p}",
              file=sys.stderr)
        return result(p)

    try:
        dbs = [open_db(p) for p in paths]
    except UnsupportedFormatError as e:
        out(f"不支持的工程格式: {e}")
        sys.exit(1)
    except Exception as e:
        out(f"无法打开工程: {e}")
        sys.exit(1)
    args.eprj_paths = paths
    if len(dbs) == 1:
        args.fn(dbs[0], args)
    else:
        # 多工程：命令需支持多工程（netfind/link-check/trace/find/search 等）
        multi = getattr(args, 'fn', None)
        if multi in (cmd_netfind, cmd_link_check, cmd_trace, cmd_find, cmd_search):
            args.dbs = dbs
            if not args.json:
                for i, p in enumerate(paths):
                    out(f"工程{i} = {p}")
            multi(dbs, args)
        else:
            out(f"多工程模式仅支持 netfind/link-check/trace/find/search，当前命令不支持")
            sys.exit(1)


if __name__ == "__main__":
    main()
