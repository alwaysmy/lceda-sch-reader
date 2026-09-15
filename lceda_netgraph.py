"""净图原语：元件角色分类 + 受引导遍历（"从端子向内走到驱动级"）。

## 用途

回答"某个端子（连接器针脚）上游是哪一级驱动、中间串了什么、旁边挂了什么
钳位件"。是审查规则 R1/R2/R4 与 SPICE 导出的共用底座——不是某条规则的私有。

## 为什么不能直接用 BFS

实测（V2 信号板，见 docs/电气规则层建议-2026-09-15.md）：对运放做朴素
BFS 会从其它引脚**涌进电源网**（+13.6V/−3.9V 成员一大片），既定位不到
钳位件也找不到端子。必须做**受引导遍历**：只在"无源串联件"（R/L/磁珠/
PTC/保险丝）与（可选的）模拟开关上跨越，**绝不穿过电源/地网**。

## 实测拓扑（V2 探头温通道，作为实现对照）

    端子 DSUB4.2 ──net U_TEMP_SENSOR──(跨页网络端口)── F1(PTC)
      └ net{F1.1, D7.A, D8.2, L3.2}   ← 钳位件 D8(TVS) 在此（1 跳）
           └ L3(磁珠) → L4(磁珠) → U15(模拟开关) → R67(22Ω)
                └ U16.OUT   ← 驱动级（运放）

钳位件离端子只有 1 跳（PTC 板内侧），**驱动级要多跳并跨过开关**——因此
两条检索分开：``find_clamps`` 稳健，``find_drivers`` 允许跨开关但降置信度。

## 依据

元件角色判据来自真实工程实测（符号引脚名 + 器件属性），见
``probes/verify_netgraph.py`` 的对照用例；不臆造字段（仓库"参数依据纪律"）。
"""

from __future__ import annotations

import re

try:
    from lceda_attrs import Attrs
except ImportError:                                   # 作为脚本直跑
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lceda_attrs import Attrs


# ---------------------------------------------------------------- 角色

R_DRIVER = "driver"          # 运放/比较器（有 OUT + IN±）
R_CLAMP = "clamp"            # TVS/ESD/齐纳（有 VBR）
R_SERIES = "series"          # 无源串联件 R/L/磁珠/PTC/保险丝
R_SWITCH = "switch"          # 模拟开关/多路复用
R_CONNECTOR = "connector"    # 连接器/端子
R_POWER = "power_source"     # 稳压器/电荷泵/电源模块
R_PASSIVE = "passive"        # 电容等
R_IC = "ic"                  # 其它有源芯片
R_OTHER = "other"

_CONNECTOR_PREFIX = ("J", "CN", "TB", "DSUB", "DB", "CON", "X", "P")
_SERIES_PREFIX = ("R", "L", "FB", "F", "FL", "RB", "TH", "RT")
_SWITCH_HINT = ("ADG", "TS5", "MAX4", "CD40", "DG4", "SN74", "NLAS", "SGM")
_POWER_HINT = ("AMS1117", "LM2596", "LM1117", "TPS", "MP2", "ADM660", "78L",
               "LM317", "LDO", "SGM", "RT9")


def _des_prefix(des):
    m = re.match(r"^[A-Za-z]+", str(des or ""))
    return m.group(0).upper() if m else ""


def _has_out_pin(pin_names):
    """是否有输出引脚。兼容多通道运放的 "OUT A"/"OUTA"/"OUT1" 写法。"""
    for n in pin_names:
        u = str(n).upper().replace(" ", "")
        if u == "OUT" or u.startswith("OUT"):
            return True
    return False


def _has_in_pair(pin_names):
    """是否有反相/同相输入对。兼容 "IN+"/"IN-"/"INP"/"INN"、
    "IN A+"/"IN A-"/"INB+"/"IN1-"/"VIN+"/"VIN-" 等多通道/多前缀写法。"""
    ups = {str(n).upper().replace(" ", "") for n in pin_names}
    if {"IN+", "IN-"} <= ups or {"INP", "INN"} <= ups:
        return True
    if "+" in ups and "-" in ups:
        return True
    # 规范化：把 "IN A+" 这类归一为 (IN,A,+) —— 存在同基名同通道的 +/- 对
    norm = {}
    for u in ups:
        m = re.match(r"^(.*?)([+-])$", u)
        if m:
            norm.setdefault(m.group(1), set()).add(m.group(2))
    return any(signs == {"+", "-"} for signs in norm.values())


class Part:
    """一个实例的分类视图。"""

    __slots__ = ("des", "title", "attrs", "pin_names", "pins", "page", "cid",
                 "role", "role_reason")

    def __init__(self, des, cid, title, desc, pin_names, pins, page):
        self.des = des
        self.cid = cid
        self.title = title or ""
        self.attrs = Attrs(desc)
        self.pin_names = [str(n) for n in pin_names if n is not None]
        self.pins = pins                 # [(pin_name, number, key)]
        self.page = page
        self.role, self.role_reason = classify(self)

    @property
    def is_two_pin(self):
        return len(self.pins) <= 2

    def pin_numbers(self):
        return [p[1] for p in self.pins]

    def __repr__(self):
        return f"<Part {self.des} {self.role} {self.title[:18]}>"


def classify(part):
    """判定元件角色，返回 (role, 依据说明)。置信度不明的一律降级到 R_IC/R_OTHER。"""
    des = part.des
    pre = _des_prefix(des)
    t = part.title.upper()
    a = part.attrs

    # 钳位件：有击穿电压属性 = 明确（TVS/ESD/齐纳通用判据）
    if a.has("VBR"):
        return R_CLAMP, "attrs:VBR"
    if pre in ("TVS", "DZ") or pre == "ESD":
        return R_CLAMP, f"设计符前缀 {pre}"

    # 驱动级：符号引脚名有 OUT + 输入对（实测 OPA171 为 OUT/IN+/IN-/V+/V-）
    if _has_out_pin(part.pin_names) and _has_in_pair(part.pin_names):
        return R_DRIVER, "符号引脚含 OUT 与 IN±"

    # 连接器：属性优先，其次设计符前缀
    if a.has("连接器类型") or a.has("公母") or "连接器" in part.attrs.get("类型", ""):
        return R_CONNECTOR, "attrs:连接器类型"
    # 前缀 J/CN/... 但需多脚（避免把 J 当连接器错判单脚跳线）
    if pre in ("J", "CN", "TB", "DSUB", "DB", "CON") and not part.is_two_pin:
        return R_CONNECTOR, f"设计符前缀 {pre}"
    # 多脚 X/P（排针/排母）
    if pre in ("X", "P") and len(part.pins) >= 3:
        return R_CONNECTOR, f"设计符前缀 {pre}(≥3脚)"

    # 电源器件：有"输出类型/输出极性/输出电压"且非运放
    if a.has("VOUT") and (a.has("输出类型") or a.has("输出极性")
                          or any(h in t for h in _POWER_HINT)):
        return R_POWER, "attrs:输出电压+输出类型"
    if any(h in t for h in _POWER_HINT) and len(part.pins) >= 3:
        return R_POWER, f"型号含电源族 {t[:12]}"

    # 模拟开关：导通电阻属性（实测 ADG1419 有 导通电阻(Ron@VCC)）
    if a.has("RON") and len(part.pins) >= 4:
        return R_SWITCH, "attrs:导通电阻(Ron)"
    if any(h in t for h in _SWITCH_HINT):
        return R_SWITCH, f"型号含开关族 {t[:12]}"

    # 串联无源件（两脚 R/L/磁珠/PTC/保险丝）
    if pre in _SERIES_PREFIX and part.is_two_pin:
        return R_SERIES, f"两脚 {pre}"

    # 电容
    if pre in ("C", "CBB", "CTC") and part.is_two_pin:
        return R_PASSIVE, f"两脚 {pre}"

    # 普通二极管/LED（有极性但无 VBR）——不是钳位件
    if pre in ("D", "LED", "ZD"):
        return R_OTHER, f"二极管 {pre}（无 VBR，非钳位件）"

    if len(part.pins) >= 3:
        return R_IC, "多脚有源件"
    return R_OTHER, "未识别"


# ---------------------------------------------------------------- 净图

class NetGraph:
    """跨页净图：网络 ↔ 引脚 ↔ 元件角色。

    构建复用 lceda_reader 的既有解析（parse_sheet / _collect_pinmap_data /
    resolve_nets_by_domain），不在本模块重复坐标与连通域逻辑（代码原则 2）。
    """

    def __init__(self):
        self.parts = {}        # des -> Part
        self.net_pins = {}     # net_key -> set((des, pin_key))
        self.pin_net = {}      # (des, pin_key) -> net_key
        self.dom = {}          # (des, pin_key) -> raw net field
        self.net_name = {}     # net_key -> 可读网络名（无名则空串）
        self.group_name = {}   # 匿名组键 -> 名称（通常无）
        self._lr = None

    # -- 构建 --------------------------------------------------------------

    @classmethod
    def build(cls, db, lr, pages=None):
        """从 reader 后端构建净图。

        db:  reader 后端；lr: lceda_reader 模块（提供解析函数）。
        pages: 限定页标题/ uuid 集合；None=全部原理图页。

        网络键（net_key）：**优先用网络名**（跨页端口同名即同网络，这是
        跨页信号能走通的关键）；网络名为空时用连通域标识（``(x, y)`` 根点），
        保证未命名信号也能被遍历。同一页内域标识唯一，故不与命名网冲突。
        """
        g = cls()
        g._lr = lr
        dmap = db.device_map()
        for uuid, title, sch, dt in db.sheets():
            if dt != 1:
                continue
            if pages is not None and title not in pages and uuid not in pages:
                continue
            sheet = lr.parse_sheet(db, uuid)
            if sheet is None:
                continue
            pinc = lr._collect_pinmap_data(db, sheet, uuid)
            if not pinc:
                continue
            comp_pins, wires, pt_wires, endp = pinc
            domain_out = {}
            try:
                dom = lr.resolve_nets_by_domain(db, sheet, comp_pins,
                                                wires, pt_wires, endp,
                                                domain_out=domain_out)
            except TypeError:            # 旧版 reader 无 domain_out 出参
                dom = lr.resolve_nets_by_domain(db, sheet, comp_pins,
                                                wires, pt_wires, endp)
            except Exception:
                dom = {}

            def _pt(p):
                if p.get("x") is None or p.get("y") is None:
                    return None
                return (round(p["x"], 1), round(p["y"], 1))

            # sheet["nets"] 的每个 net 组是 EDA 认定的**一个连通域**（无名也是），
            # 把同组的所有点映射到统一组键。用于兜底：引脚落在组内任一点即属
            # 该组——覆盖"引脚对引脚直接对接"（无导线，如 U16.IN- ↔ R66.2，
            # 两点坐标不同但在同一 net 组）这一 pin_hit 不覆盖的情形。
            pt_group = {}
            for gi, n in enumerate(sheet["nets"]):
                gkey = f"@grp{gi}"
                for px, py in n["points"]:
                    pt_group[(round(px, 1), round(py, 1))] = gkey
                nm = n.get("net")
                if nm:
                    g.group_name.setdefault(gkey, nm)
                    g.net_name.setdefault(gkey, nm)

            # 引脚 -> 网络键。
            # 优先级：命名网络 > 导线端点命中(domain_out) > net 组键。
            for (des, cid), plist in comp_pins.items():
                du = des.upper()
                for p in plist:
                    pk = p.get("key") or p.get("pin")
                    if (du, pk) in g.pin_net:
                        continue
                    net = dom.get((des, pk), "")
                    key = None
                    if net:
                        toks = lr.net_tokens(net)
                        key = toks[0] if toks else None
                    if key is None:
                        key = domain_out.get((des, pk))
                    if key is None:
                        p0 = _pt(p)
                        if p0 and p0 in pt_group:
                            key = pt_group[p0]
                    if key is None:
                        continue
                    g.dom.setdefault((du, pk), net)
                    g.pin_net[(du, pk)] = key
                    g.net_name.setdefault(
                        key, (lr.net_tokens(net)[0] if net else ""))
                    g.net_pins.setdefault(key, set()).add((du, pk))
            # 设计符 -> 引脚名（符号定义）——先建 parts，供后续分类与查询
            for (des, cid), plist in comp_pins.items():
                c = next((x for x in sheet["components"]
                          if x["cid"] == cid), None)
                if c is None:
                    continue
                sym = lr.symbol_of(db, c)
                sp = db.symbol_pins(sym) if sym else None
                pin_names = [p.get("name") for p in (sp["pins"] if sp else [])]
                pins = [(p.get("pin"), p.get("number"),
                         p.get("key") or p.get("pin")) for p in plist]
                dev = dmap.get(c.get("device_uuid") or "", ("", "", ""))
                desc = dev[2] if len(dev) > 2 else ""
                g.parts[des.upper()] = Part(
                    des, cid, c.get("title") or (dev[1] if dev else ""),
                    desc, pin_names, pins, title)
        return g

    # -- 查询 --------------------------------------------------------------

    def part(self, des):
        return self.parts.get(str(des).upper())

    def other_pins(self, des, pin_key):
        """两脚件/多脚件的"同件其它引脚"。"""
        p = self.part(des)
        if not p:
            return []
        return [pk for (_n, _num, pk) in p.pins if pk != pin_key]

    def walk(self, start_net, max_hops=8, cross_switches=True,
             cross_series=True, exclude=None):
        """受引导遍历：从 start_net 出发，只跨串联件/开关，**不穿电源网**。

        返回 ``{net_key: hop}``（含起点，hop=0）。电源/地网不入结果——
        这是与朴素 BFS 的关键差别（实测朴素 BFS 会涌进 +13.6V 等大网）。

        ``exclude``：不进入且不跨越的网络键集合。用于"从输出端看反馈网络"
        时**排除求和节点**——否则遍历会绕回输入侧，使 Rf/Rin 无法区分
        （实测 V2 信号板：不排除求和节点时，Rf 候选会把 Rin 一起圈进来）。
        """
        lr = self._lr
        is_power = lr.is_power_net if lr else (lambda n: "GND" in str(n).upper())
        excl = set(exclude or ())
        seen = {start_net: 0}
        frontier = [start_net]
        hop = 0
        while frontier and hop < max_hops:
            hop += 1
            nxt = []
            for net in frontier:
                for (des, pk) in list(self.net_pins.get(net, ())):
                    p = self.part(des)
                    if not p:
                        continue
                    cross = (cross_series and p.role == R_SERIES) or \
                            (cross_switches and p.role == R_SWITCH)
                    if not cross:
                        continue
                    for other in self.other_pins(des, pk):
                        onet = self.pin_net.get((des.upper(), other))
                        if not onet or onet in seen or onet in excl:
                            continue
                        name = self.net_name.get(onet) or ""
                        if name and is_power(name):
                            continue
                        seen[onet] = hop
                        nxt.append(onet)
            frontier = nxt
        return seen

    def find_clamps(self, start_net, max_hops=8):
        """端子附近的钳位件：[{des, part, pin, net, other_net, hops}]。

        只报**落在遍历到的网络里**的钳位件，并给出其"另一端"网络
        （应接 GND 或电源轨，用于判断是钳位路径而非串联路径）。
        """
        hops = self.walk(start_net, max_hops=max_hops)
        out = []
        for net, h in hops.items():
            for (des, pk) in list(self.net_pins.get(net, ())):
                p = self.part(des)
                if not p or p.role != R_CLAMP:
                    continue
                others = self.other_pins(des, pk)
                other_net = self.pin_net.get((des.upper(), others[0])) \
                    if others else None
                out.append({"des": p.des, "part": p, "pin": pk, "net": net,
                            "other_net": other_net, "hops": h})
        out.sort(key=lambda r: r["hops"])
        return out

    def find_drivers(self, start_net, max_hops=8):
        """端子上游的驱动级：[{des, part, out_pin, out_net, hops}]。"""
        hops = self.walk(start_net, max_hops=max_hops)
        out = []
        for net, h in hops.items():
            for (des, pk) in list(self.net_pins.get(net, ())):
                p = self.part(des)
                if not p or p.role != R_DRIVER:
                    continue
                for (nm, _num, key) in p.pins:
                    if str(nm).upper() == "OUT":
                        out.append({"des": p.des, "part": p, "out_pin": key,
                                    "out_net": self.pin_net.get(
                                        (p.des.upper(), key)),
                                    "hops": h})
        out.sort(key=lambda r: r["hops"])
        return out

    # -- 驱动级传递函数（保守） -------------------------------------------

    def pin_named(self, des, *names):
        """取指定引脚名的 (key, net)。names 大小写不敏感，含别名。

        兼容多通道后缀：查 "OUT" 时也接受 "OUT A"/"OUTA"/"OUT1"
        （精确匹配优先，避免多通道件取错通道）。
        """
        p = self.part(des)
        if not p:
            return None
        want = {n.upper() for n in names}
        exact, fuzzy = [], []
        for (nm, _num, key) in p.pins:
            u = str(nm).upper()
            u_ns = u.replace(" ", "")
            if u in want:
                exact.append((key, self.pin_net.get((p.des.upper(), key))))
                continue
            base = re.match(r"^([A-Z]+)", u_ns)
            if base and base.group(1) in want:
                fuzzy.append((key, self.pin_net.get((p.des.upper(), key))))
        if exact:
            return exact[0]
        if fuzzy:
            return fuzzy[0]
        return None

    def channel_pins(self, des):
        """把引脚按"通道后缀"分组，便于多通道运放整体解析。

        返回 ``{"": {base: key}, "A": {base: key}, ...}``——base 为去掉通道
        后缀的引脚名（OUT/IN+/IN-/V+/V-）。单通道件全部落在 ``""`` 组。
        多通道运放（实测 OPA2350: OUT A/OUT B/IN A±/IN B±）按通道拆分后，
        每个通道可独立算传递函数。
        """
        p = self.part(des)
        if not p:
            return {}
        chans = {}
        for (nm, _num, key) in p.pins:
            u = str(nm).upper().replace(" ", "")
            # 供电脚（可能带通道/前缀，如 V+/VDD/VSSA）归公共组
            if re.match(r"^(V[+-]|VDD|VSS|GND|VCC|VS[+-])$", u):
                chans.setdefault("", {})[u] = key
                continue
            # 通道后缀：IN A- / INA- / IN1- / OUT A / OUTA / OUT1 / INP/INN
            m = re.match(r"^(IN|OUT)([A-D]|[1-4])?([+-]?)$", u)
            if not m:
                m = re.match(r"^(INP|INN)([A-D]|[1-4])?$", u)
                if m:
                    base = {"INP": "IN+", "INN": "IN-"}[m.group(1)]
                    chans.setdefault(m.group(2) or "", {})[base] = key
                    continue
                chans.setdefault("", {})[u] = key
                continue
            kind, suf, sign = m.group(1), (m.group(2) or ""), m.group(3)
            if kind == "IN" and not sign:
                chans.setdefault("", {})[u] = key      # 无符号的 IN（如 IN）
                continue
            base = ("IN" + sign) if kind == "IN" else "OUT"
            chans.setdefault(suf, {})[base] = key
        return chans

    def driver_transfer(self, des, max_hops=6):
        """保守估计运放级的输出包络：``Vout = offset - gain*Vin``。

        仅支持**最常见的反相/同相两电阻反馈**（含"参考经电阻注入求和节点"
        的变体，即 V2 信号板的实测形态）。识别不确定时返回
        ``confidence='low'`` 并说明原因，交由人工确认——符合工具既有的
        "分级置信度"原则，不做通用拓扑识别。

        返回 dict:
          gain       Rf/Rin（≥0）
          offset     Vin=0 时的输出（反相级的上端，用于与钳位件比较）
          inverting  是否反相
          vref       参考电压（V）
          rf/rin     反馈/输入电阻（Ω）
          confidence 'high' | 'low'
          notes      [str]
        """
        notes = []
        res = {"des": des, "gain": None, "offset": None, "inverting": None,
               "vref": None, "rf": None, "rin": None,
               "confidence": "low", "notes": notes}
        p = self.part(des)
        if not p or p.role != R_DRIVER:
            notes.append("非驱动级")
            return res

        # 逐通道解析（多通道运放如 OPA2350：OUT A/OUT B/IN A±/IN B±）。
        # 取第一个 confidence=high 的通道；否则取第一个有输出的通道并带回
        # 各自的 notes 串，说明为什么不可算。
        chans = self.channel_pins(des)
        picks = []
        for suf, d in chans.items():
            if {"OUT", "IN+", "IN-"} <= set(d):
                picks.append((suf, d))
        if not picks:
            notes.append("缺少 OUT/IN± 引脚")
            return res
        if len(picks) > 1:
            notes.append(f"多通道运放，逐通道尝试：{', '.join(s for s,_ in picks)}")

        first = None
        for suf, d in picks:
            sub = self._transfer_for(des, d, max_hops, suf)
            if sub["confidence"] == "high":
                if first is not None and first.get("notes"):
                    sub["notes"] = first["notes"] + sub["notes"]
                return sub
            if first is None:
                first = sub
        return first

    def _transfer_for(self, des, chan, max_hops, suffix=""):
        """单通道传递函数（chan = {OUT/IN+/IN-/V±: pin_key}）。"""
        notes = []
        res = {"des": des, "gain": None, "offset": None, "inverting": None,
               "vref": None, "rf": None, "rin": None,
               "confidence": "low", "notes": notes, "channel": suffix}
        tag = f"通道{suffix}：" if suffix else ""
        inn_net = self.pin_net.get((des.upper(), chan["IN-"]))
        inp_net = self.pin_net.get((des.upper(), chan["IN+"]))
        out_net = self.pin_net.get((des.upper(), chan["OUT"]))
        if not (inn_net and inp_net and out_net):
            notes.append(tag + "通道引脚未全部连接")
            return res

        # 参考：优先解析同相端网络名里的电压（实测 "+1.96V-REF"）
        vref = _voltage_from_netname(inp_net)
        if vref is None:
            notes.append(tag + f"同相端网络 {inp_net!r} 未含可解析电压，"
                              f"参考电平需人工确认")
        res["vref"] = vref

        # 求和节点：IN- 经电阻到达的节点（运放输入无电流，V(求和)=V(IN-)=Vref）
        # 实测 V2 形态：IN- ─R66─ nx ─┬─ R63 ─ OUT
        #                              ├─ R65 ─ 输入(DAx)
        #                              └─ C85 ─ GND
        sum_net = None
        for (des2, pk) in list(self.net_pins.get(inn_net, ())):
            pp = self.part(des2)
            if pp and pp.role == R_SERIES and pp.is_two_pin:
                for o in self.other_pins(des2, pk):
                    onet = self.pin_net.get((pp.des.upper(), o))
                    if onet:
                        sum_net = onet
                        break
        if sum_net is None:
            notes.append(tag + "IN- 未经电阻连到求和节点（非电阻反馈形态）")
            return res

        # Rf：反馈电阻。**不假设它直接连 OUT**——实测 V2 信号板运放输出
        # 经 R67(22Ω) 到开关前节点 nsw，反馈 R63 接在 nsw 上（文档的 V_sw）。
        # 判据：一端落在"从 OUT 排除求和节点后的可达集"、另一端落在求和节点。
        out_reach = self.walk(out_net, max_hops=max_hops, exclude={sum_net})
        out_reach[out_net] = 0

        def _other_net(part, pin_key):
            for o in self.other_pins(part.des, pin_key):
                return self.pin_net.get((part.des.upper(), o))
            return None

        rf = None
        for net in out_reach:
            for (des2, pk) in list(self.net_pins.get(net, ())):
                pp = self.part(des2)
                if not (pp and pp.role == R_SERIES and pp.is_two_pin):
                    continue
                if _other_net(pp, pk) == sum_net:
                    rf = pp
                    break
            if rf:
                break

        # Rin：挂在求和节点、通向**外部输入**的串联件。
        # 排除：Rf；通向 OUT 侧可达集的；通向驱动级自身输入引脚网的
        # （实测 V2 的 R66=3.9k 是 IN- 隔离电阻，因运放输入无电流而不影响
        #  直流增益——文档公式里不出现，不应被当成 Rin）。
        drv_input_nets = {inn_net, inp_net} - {None}
        rin = None
        unknown_series = []
        for (des2, pk) in list(self.net_pins.get(sum_net, ())):
            pp = self.part(des2)
            if not (pp and pp.role == R_SERIES and pp.is_two_pin):
                continue
            if rf and pp.des.upper() == rf.des.upper():
                continue
            onet = _other_net(pp, pk)
            if not onet or onet == sum_net:
                continue
            if onet in out_reach or onet in drv_input_nets:
                continue                      # OUT 侧 / IN- 隔离
            # T 型检测：候选输入件的另一端**还挂着别的串联件**，说明输入
            # 不是直接进来，而是经 T 型/两级网络（实测 U19：求和节点 -R75-
            # 中间节点 -R74- 输入，另有 R76；简单两电阻模型会算出错误增益）。
            further = [q for q in self.net_pins.get(onet, ())
                       if (self.part(q[0]) and self.part(q[0]).role == R_SERIES
                           and self.part(q[0]).is_two_pin
                           and q[0].upper() != pp.des.upper()
                           and _other_net(self.part(q[0]), q[1]) != sum_net)]
            if further:
                unknown_series.append((pp.des, onet))
                continue
            if rin is None:
                rin = pp
            else:
                unknown_series.append((pp.des, onet))
        if unknown_series:
            notes.append(
                tag + "求和节点存在未建模的串联支路（疑似 T 型/多路输入网络）："
                + ", ".join(f"{d}→{n}" for d, n in unknown_series)
                + "；两电阻模型不适用，需人工确认")
            return res
        if rf is None or rin is None:
            notes.append(f"{tag}未能同时确定 Rf/Rin（Rf="
                         f"{rf.des if rf else None}, "
                         f"Rin={rin.des if rin else None}）")
            return res

        rfq, rinq = rf.attrs.qty("RESISTANCE"), rin.attrs.qty("RESISTANCE")
        if not (rfq and rinq) or rinq.typ == 0:
            notes.append(tag + "Rf/Rin 阻值缺失或为 0")
            return res
        gain = rfq.typ / rinq.typ
        res["rf"] = rfq.typ
        res["rin"] = rinq.typ
        res["gain"] = gain
        res["inverting"] = True          # 观测形态；同相需另做
        if vref is None:
            return res                       # 无参考不敢算 offset
        res["offset"] = vref * (1 + gain)
        res["confidence"] = "high" if not notes else "low"
        return res

    def driver_envelope(self, des):
        """驱动级可输出上界：min(正电源轨, offset)。返回 (volt, note)。"""
        tr = self.driver_transfer(des)
        if tr["offset"] is None:
            return None, "传递函数不可算：" + "; ".join(tr["notes"])
        rail = None
        # 供电脚可能在公共组（channel_pins 的 ""）或与通道同组
        vp_key = None
        chans = self.channel_pins(des)
        for grp in [chans.get(tr.get("channel") or "", {}), chans.get("", {})]:
            for nm in ("V+", "VDD", "VCC", "VS+"):
                if nm in grp:
                    vp_key = grp[nm]
                    break
            if vp_key:
                break
        if vp_key:
            rail_net = self.pin_net.get((des.upper(), vp_key))
            rail = self._rail_voltage(des, rail_net)
        top = tr["offset"]
        ch = f"[通道{tr['channel']}] " if tr.get("channel") else ""
        note = (f"{ch}Vin=0 时输出 {top:.3g}V（增益 {tr['gain']:.3g}, "
                f"参考 {tr['vref']:.3g}V）")
        if rail is not None and rail < top:
            return rail, note + f"；受正轨 {rail:.3g}V 限制"
        return top, note

    def _rail_voltage(self, des, rail_net):
        """正电源轨电压：解析网络名（+13.6V）；解析不到返回 None。"""
        v = _voltage_from_netname(rail_net)
        return v


def _voltage_from_netname(net):
    """从网络名解析电压："+13.6V" / "3V3" / "1V8" / "-3.9V"；解析不到 None。"""
    if not net:
        return None
    s = str(net).strip()
    m = re.match(r"^[+-]?\d+(?:\.\d+)?V", s)
    if m:
        try:
            return float(re.match(r"^[+-]?\d+(?:\.\d+)?", s).group(0))
        except ValueError:
            return None
    m = re.match(r"^[+-]?D?(\d+)V(\d+)$", s.upper())
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    return None
