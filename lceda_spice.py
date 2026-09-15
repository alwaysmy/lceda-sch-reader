"""网表导出层（第 2 层）：把原理图/电路块导出为 SPICE 网表。

## 定位（三层架构的第二层）

第 1 层（`lceda_blocks`）识别电路块，但**认不出也要能继续**——本层就是
那个通用兜底：**无条件**把"作用域内的元件 + 网络"转成网表，不依赖识别
成功。这样第 3 层（LLM / LTspice / ngspice）总有饭吃。

**不自造求解器**（方案 §3）：只导出，交给外部工具或 LLM 分析。

## 元件映射

| 器件 | 网表形式 |
| ---- | -------- |
| R/L/C | `Rxx n1 n2 <值>`（值取 `lceda_attrs` 的 SI 量） |
| 运放 | 行为子电路 `XU.. n+ n- out vcc vee OPAMP`（跨导+轨钳位+限流）|
| TVS/ESD/齐纳 | 两只齐纳反串联（`BV` 直接取属性 `击穿电压`）|
| 模拟开关 | 理想开关（`Ron` 取属性）|
| 电源网 | 由网络名生成 `V.. <net> 0 <电压>` |

节点命名：有网络名用名字（**跨页同名即同节点**，与 netgraph 口径一致），
无名用 `N<hash>`；`0` 固定为地（GND）。
"""

from __future__ import annotations

import re

try:
    from lceda_attrs import Attrs, clamp_onset
    from lceda_netgraph import (R_CLAMP, R_CONNECTOR, R_DRIVER, R_OTHER,
                                R_PASSIVE, R_POWER, R_SERIES, R_SWITCH)
except ImportError:
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lceda_attrs import Attrs, clamp_onset
    from lceda_netgraph import (R_CLAMP, R_CONNECTOR, R_DRIVER, R_OTHER,
                                R_PASSIVE, R_POWER, R_SERIES, R_SWITCH)


# 运放行为模型：跨导级 + 轨钳位 + 限流。参数化，便于按实测调整。
OPAMP_SUBCKT = """\
* --- 运放行为模型（跨导 + 轨钳位 + 限流）[工具生成，参数可调] ---
* AOL=开环增益(1e6)  GM=跨导(S)  ISC=输出限流(A)  ROUT=输出阻抗
.subckt OPAMP INP INN OUT VCC VEE
RIN   INP INN 1E7
EGM   0 G  INP INN {GM}
RG    G 0  1
E1    OUTP 0 G 0 {AOL}
RO1   OUTP OUTR 1
DHI   OUTR VCC  DCL
DLO   VEE OUTR  DCL
ROUT  OUTR OUT  {ROUT}
.model DCL D(IS=1E-15 N=1.0 RS=1)
.ends OPAMP

* --- 双向 TVS：两只齐纳反串联（单向钳位 = BV + VF）[工具生成] ---
.subckt TVS_BI A K {BV}
DZ1  A M  DZ{BV}
DZ2  M K  DZ{BV}
.model DZ{BV} D(BV={BV} IBV=10m RS=0.05 N=1.2)
.ends TVS_BI
"""


def _rail_v(net_name):
    if not net_name:
        return None
    s = str(net_name).strip()
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


def _spice_val(q, fallback_unit):
    if q is None:
        return None
    # SPICE 用工程记法（1k/1u/1n），保持可读
    v = q.typ
    if v == 0:
        return "0"
    for scale, suf in ((1e9, "G"), (1e6, "Meg"), (1e3, "k"), (1.0, ""),
                       (1e-3, "m"), (1e-6, "u"), (1e-9, "n"),
                       (1e-12, "p")):
        if abs(v) >= scale:
            return f"{v/scale:.6g}{suf}".replace(".", ".")
    return f"{v:.6g}"


class NetlistWriter:
    """按作用域导出 SPICE 网表。"""

    def __init__(self, graph):
        self.g = graph
        self._node = {}       # net_key -> 节点名
        self._used = {}
        self._power_srcs = []

    def node(self, net_key):
        if net_key is None:
            return "NC_"
        if net_key in self._node:
            return self._node[net_key]
        name = (self.g.net_name.get(net_key) or "").strip()
        if name.upper() in ("GND", "AGND", "DGND", "PGND", "0", "GROUND"):
            n = "0"
        elif name:
            n = re.sub(r"[^0-9A-Za-z_\-+]", "_", name)
        else:
            n = f"N{abs(hash(net_key)) % 100000}"
        # 去重
        base, i = n, 1
        while self._used.get(n) and self._used[n] != net_key:
            i += 1
            n = f"{base}_{i}"
        self._used[n] = net_key
        self._node[net_key] = n
        return n

    def _pin_node(self, des, pin_key):
        return self.node(self.g.pin_net.get((des.upper(), pin_key)))

    def _chan_groups(self, des):
        return self.g.channel_pins(des)

    def emit(self, pages=None, only_nets=None, title="schematic"):
        """导出网表。

        pages: 限定页（None=全部）；only_nets: 只含这些网络（含网表名/键）。
        """
        g = self.g
        if pages is not None:
            wanted = {p.des.upper() for p in g.parts.values()
                      if p.page in pages or _page_of(g, p) in pages}
        else:
            wanted = {p.des.upper() for p in g.parts.values()}
        if only_nets:
            keep = set()
            for des in wanted:
                pp = g.part(des)
                for (_n, _num, k) in pp.pins:
                    nk = g.pin_net.get((des, k))
                    if nk and (nk in only_nets
                               or (g.net_name.get(nk) or "") in only_nets):
                        keep.add(des)
                        break
            wanted &= keep

        lines = [f"* {title} — 由 lceda_sch_reader 导出（第2层网表）",
                 "* 节点命名：优先网络名（跨页同名=同节点），0=地",
                 ".param AOL=1e6 GM=1 ISC=25m ROUT=10", ""]
        lines.append(OPAMP_SUBCKT)

        # 元件
        for des in sorted(wanted):
            p = g.part(des)
            if not p or p.attrs.has("_skip"):
                continue
            line = self._element(p)
            if line:
                lines.append(line)

        # 电源网（有名且像电压源的网络，未被外部源显式给定时）
        lines.extend(self._power_lines(wanted))

        lines.append("")
        lines.append(".tran 1m 10m")
        lines.append(".end")
        return "\n".join(lines)

    def _element(self, p):
        g, des = self.g, p.des.upper()
        pins = p.pins
        if p.role in (R_SERIES, R_PASSIVE):
            a = self._pin_node(des, pins[0][2]) if len(pins) > 0 else "NC_"
            b = self._pin_node(des, pins[1][2]) if len(pins) > 1 else "NC_"
            if _is_cap(p):
                v = _spice_val(p.attrs.qty("CAPACITANCE"), "F")
                return f"C{des} {a} {b} {v or '1n'}"
            if p.attrs.has("INDUCTANCE"):
                v = _spice_val(p.attrs.qty("INDUCTANCE"), "H")
                dcr = p.attrs.qty("DCR")
                extra = f" Rser={_spice_val(dcr, 'Ohm')}" if dcr else ""
                return f"L{des} {a} {b} {v or '1u'}{extra}"
            v = _spice_val(p.attrs.qty("RESISTANCE"), "Ohm")
            return f"R{des} {a} {b} {v or '1k'}"
        if p.role == R_CLAMP:
            # TVS/ESD：两端 + BV（双向用反串联子电路）
            bv = p.attrs.qty("VBR")
            a = self._pin_node(des, pins[0][2]) if len(pins) > 0 else "NC_"
            b = self._pin_node(des, pins[1][2]) if len(pins) > 1 else "NC_"
            bvv = f"{bv.typ:g}" if bv else "6.8"
            pol = p.attrs.get("POLARITY")
            if pol and "双" in str(pol):
                return f"XD{des} {a} {b} TVS_BI {bvv}"
            return f"D{des} {a} {b} DZ_{des}\n.model DZ_{des} D(BV={bvv} IBV=10m RS=0.05)"
        if p.role == R_SWITCH:
            # 模拟开关：理想开关 + 导通电阻
            ron = p.attrs.qty("RON")
            rv = f"{ron.typ:g}" if ron else "5"
            return (f"* 模拟开关 {p.des}({p.title})：理想开关，Ron≈{rv}Ω"
                    f"（引脚 {[n for n,_x,_k in p.pins]}）")
        if p.role == R_DRIVER:
            return self._opamp(p)
        if p.role == R_CONNECTOR:
            return f"* 连接器 {p.des}({p.title})：{len(p.pins)} 脚（端子）"
        if p.role == R_POWER:
            return f"* 电源器件 {p.des}({p.title})（源按网名建模）"
        return None

    def _opamp(self, p):
        g, des = self.g, p.des.upper()
        chans = self._chan_groups(des)
        out = []
        # 供电脚（公共组）
        vcc = vee = None
        common = chans.get("", {})
        if "V+" in common:
            vcc = self._pin_node(des, common["V+"])
        if "V-" in common:
            vee = self._pin_node(des, common["V-"])
        for suf, d in chans.items():
            if not {"OUT", "IN+", "IN-"} <= set(d):
                continue
            ip = self._pin_node(des, d["IN+"])
            im = self._pin_node(des, d["IN-"])
            o = self._pin_node(des, d["OUT"])
            name = f"X{des}{suf} {ip} {im} {o} {vcc or 'VCC'} {vee or 'VEE'} OPAMP"
            out.append(name)
        return "\n".join(out) if out else f"* 运放 {p.des}({p.title}) 引脚不全，未展开"

    def _power_lines(self, wanted):
        """由网络名生成电源源（未在作用域内已有源器件时）。"""
        seen = set()
        lines = []
        for net_key, pins in sorted(self.g.net_pins.items(),
                                    key=lambda kv: kv[0]):
            name = self.g.net_name.get(net_key) or ""
            if not name or name in seen:
                continue
            v = _rail_v(name)
            if v is None:
                continue
            has_src = any((self.g.part(d) and
                           self.g.part(d).role == R_POWER) for d, _ in pins)
            if has_src:
                continue
            n = self.node(net_key)
            if n in ("0", "NC_"):
                continue
            seen.add(name)
            lines.append(f"V_{re.sub(r'[^0-9A-Za-z]', '', name)} {n} 0 {v:g}")
        if lines:
            lines.insert(0, "* 电源轨（按网络名生成；实际来源见 R3 审查）")
        return lines


def _page_of(graph, part):
    return part.page


def _is_cap(part):
    return (str(part.des).upper().startswith(("C", "CBB", "CTC"))
            or part.attrs.has("CAPACITANCE"))


def emit_for_block(graph, block, title=None):
    """导出驱动块邻域的网表（第 1 层 → 第 2 层的直接通路）。

    **不依赖识别结果**：即使块是 `opamp_network`（未识别），也从驱动的
    OUT/IN± 出发按网络邻域聚合元件——这样第 3 层（LLM/SPICE）总有完整
    网表可用。识别出的 `members` 作为附加提示，不作为唯一来源。
    """
    w = NetlistWriter(graph)
    des = block.anchor
    p = graph.part(des)
    chans = graph.channel_pins(des)
    suf = block.channel or ""
    keys = chans.get(suf) or next((d for d in chans.values()
                                   if {"OUT", "IN+", "IN-"} <= set(d)), {})
    seeds = []
    for base in ("OUT", "IN+", "IN-", "V+", "V-"):
        k = keys.get(base)
        if k:
            nk = graph.pin_net.get((des.upper(), k))
            if nk:
                seeds.append(nk)

    # 邻域：从各引脚网出发，沿无源件（含电容/电感）展开 2 跳
    is_power = graph._lr.is_power_net if graph._lr else \
        (lambda n: "GND" in str(n).upper())
    scope_nets = set(seeds)
    frontier = list(seeds)
    for _hop in range(2):
        nxt = []
        for net in frontier:
            for (d, pk) in graph.net_pins.get(net, ()):
                pp = graph.part(d)
                if not pp or pp.des.upper() == des.upper():
                    continue
                if pp.role not in (R_SERIES, R_PASSIVE, R_CLAMP):
                    continue
                for o in graph.other_pins(pp.des, pk):
                    onet = graph.pin_net.get((pp.des.upper(), o))
                    if not onet or onet in scope_nets:
                        continue
                    name = graph.net_name.get(onet) or ""
                    if name and is_power(name):
                        continue             # 电源网只作为节点，不展开
                    scope_nets.add(onet)
                    nxt.append(onet)
        frontier = nxt

    # 收集作用域内的两脚无源件 + 驱动本身
    members = set()
    for net in scope_nets:
        for (d, _pk) in graph.net_pins.get(net, ()):
            pp = graph.part(d)
            if not pp or pp.des.upper() == des.upper():
                continue
            if pp.role in (R_SERIES, R_PASSIVE) and pp.is_two_pin:
                members.add(pp.des)
            elif pp.role == R_CLAMP:
                members.add(pp.des)
    # 识别出的成员也并入（可能含跨跳件）
    members |= {m for m in block.members if graph.part(m)}

    lines = [f"* 电路块 {block.label} kind={block.kind} "
             f"conf={block.confidence}",
             f"* 识别成员: {', '.join(sorted(block.members)) or '(未识别)'}",
             f"* 邻域导出: {', '.join(sorted(members)) or '(无)'}"]
    for e in block.evidence:
        lines.append(f"* 依据: {e}")
    lines.append("")
    lines.append(OPAMP_SUBCKT)
    for m in sorted(members):
        pp = graph.part(m)
        if pp:
            ln = w._element(pp)
            if ln:
                lines.append(ln)
    lines.append(w._opamp(p))
    lines.extend(w._power_lines(set()))
    lines.append("")
    lines.append(".end")
    return "\n".join(lines)
