"""审查规则层：注册项式规则引擎 + 电气规则 R1~R4。

## 分层

- **规则** = ``Rule{id, scope, severity, check(ctx) -> [Finding]}``，
  配置驱动启停/阈值（``review_rules.json``，_note 标依据）。
- **规则只面对统一模型**（后端合成 + ``lceda_attrs`` 语义量 + ``lceda_netgraph``
  拓扑），不接触原始记录——格式差异已在后端归一（原则 8 的延伸）。
- 阈值等属**工具配置**（原则 9）：外置 json + `_note`，不写死在规则里。

## 已实现规则（依据 docs/电气规则层建议-2026-09-15.md）

| id | 名称 | 判据 |
| -- | ---- | ---- |
| ``R1`` | 端子/输出电气包络 vs 钳位件起始 | 设计上限 > 钳位起始(VBR_min + 双向修正) → WARN/ERROR |
| ``R2`` | 串联件能力 vs 最坏电流 | 磁珠 Isat / PTC Ihold < 驱动级可能电流 → WARN |
| ``R3`` | 电源轨来源 / 参考脚核对 | 无可见源的轨、参考脚接非地网 → INFO（需人工确认）|
| ``R4`` | 反相极性语义提示 | 输出级增益为负 → INFO（提示固件映射需反相）|

R1~R4 覆盖"运放输出级 + 端子保护件"这一高频形态（V2 信号板 6/6 命中），
其余拓扑按需增量——不做通用拓扑识别（方案 §6 边界）。
"""

from __future__ import annotations

import json
import os
import re

try:
    from lceda_attrs import Attrs, clamp_onset, is_bidirectional
    from lceda_netgraph import (NetGraph, R_CLAMP, R_CONNECTOR, R_DRIVER,
                                R_POWER, R_SERIES, R_SWITCH)
    from lceda_blocks import (Block, features, recognize_all, evaluate,
                              FORMULA_KINDS, K_UNKNOWN, K_TNET, K_COMPARATOR,
                              K_INVERTING, K_FOLLOWER)
    from lceda_spice import emit_for_block, NetlistWriter
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lceda_attrs import Attrs, clamp_onset, is_bidirectional
    from lceda_netgraph import (NetGraph, R_CLAMP, R_CONNECTOR, R_DRIVER,
                                R_POWER, R_SERIES, R_SWITCH)
    from lceda_blocks import (Block, features, recognize_all, evaluate,
                              FORMULA_KINDS, K_UNKNOWN, K_TNET, K_COMPARATOR,
                              K_INVERTING, K_FOLLOWER)
    from lceda_spice import emit_for_block, NetlistWriter


SEV_INFO = "info"
SEV_WARN = "warn"
SEV_ERROR = "error"


class Finding:
    """一条审查发现（机器可读 + 人可读，含证据链）。"""

    __slots__ = ("rule", "severity", "scope", "subject", "message", "evidence")

    def __init__(self, rule, severity, scope, subject, message, evidence=None):
        self.rule = rule
        self.severity = severity
        self.scope = scope            # "page: 页名" / "terminal: 端子"
        self.subject = subject        # 位号/端子名
        self.message = message
        self.evidence = evidence or {}

    def as_dict(self):
        return {"rule": self.rule, "severity": self.severity,
                "scope": self.scope, "subject": self.subject,
                "message": self.message, "evidence": self.evidence}

    def __repr__(self):
        return f"[{self.severity.upper()}] {self.rule} {self.subject}: {self.message}"


# ---------------------------------------------------------------- 配置

DEFAULT_CONFIG = {
    "_note": "审查规则配置[自创]——阈值依据 docs/电气规则层建议-2026-09-15.md §5；"
             "钳位余量 <warn 判 WARN、<error 判 ERROR",
    "rules": {
        "R1": {"enabled": True, "clamp_margin_warn_v": 0.5,
               "clamp_margin_error_v": 0.0},
        "R2": {"enabled": True, "current_margin": 0.8},
        "R3": {"enabled": True},
        "R4": {"enabled": True},
    },
    "tvs_bidir_vf": 0.7,
    "_tvs_bidir_vf_note": "[实测] 双向 TVS 反串联结构，实际钳位比标称 VBR 高约 V_F；"
                          "V2 信号板实测 7.28~7.48V vs 仿真 BV+V_F 吻合"
                          "（见 docs/电气规则层建议-2026-09-15.md §7）",
}


def load_config(path=None):
    """加载 review_rules.json（缺省与 DEFAULT_CONFIG 合并）。"""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))     # 深拷贝
    p = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "review_rules.json")
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                user = json.load(f)
            for k, v in (user.get("rules") or {}).items():
                cfg["rules"].setdefault(k, {}).update(v)
            if "tvs_bidir_vf" in user:
                cfg["tvs_bidir_vf"] = user["tvs_bidir_vf"]
        except Exception:
            pass
    return cfg


# ---------------------------------------------------------------- 规则

class Ctx:
    """规则上下文：净图 + 配置 + reader 模块。"""

    def __init__(self, graph, cfg, lr):
        self.g = graph
        self.cfg = cfg
        self.lr = lr
        self._terminals = None
        self._drivers = None

    def terminals(self):
        """连接器实例（端子候选）。"""
        if self._terminals is None:
            self._terminals = [p for p in self.g.parts.values()
                               if p.role == R_CONNECTOR]
        return self._terminals

    def drivers(self):
        if self._drivers is None:
            self._drivers = [p for p in self.g.parts.values()
                             if p.role == R_DRIVER]
        return self._drivers


def _clamp_of_graph(ctx, start_net, max_hops=8):
    """端子网络上最近的有效钳位件（就近 1 个，其余在 evidence 列出）。"""
    return ctx.g.find_clamps(start_net, max_hops=max_hops)


def _pick_clamp(clamps, cfg):
    """从候选钳位件里选**实际起限制作用**的那个：钳位起始最低者。

    不能只取跳数最近的——实测 V2 信号板 U19 输出同时挂 D11(18V,到+13.6V)
    与 D12(5V,到 GND)，最近的是 D11，但真正吃掉量程的是 D12。取起始最低者
    才对应"最先导通、最先限幅"的物理事实。
    """
    best, best_onset = None, None
    for c in clamps:
        onset = clamp_onset(c["part"].attrs.qty("VBR"),
                           c["part"].attrs.get("POLARITY"),
                           vf=cfg.get("tvs_bidir_vf", 0.7))
        if onset is None:
            continue
        if best_onset is None or onset.min < best_onset.min:
            best, best_onset = c, onset
    return best, best_onset


def rule_R1(ctx):
    """端子/输出电气包络 vs 钳位件起始。

    对每个"驱动级输出可达的钳位件"，比较驱动级可输出上界与钳位起始。
    锚点用驱动级（比用连接器更通用——很多板的"端子"是排针/网络端口，
    且驱动级一定能算包络）。
    """
    findings = []
    opts = ctx.cfg["rules"].get("R1", {})
    warn_v = opts.get("clamp_margin_warn_v", 0.5)
    err_v = opts.get("clamp_margin_error_v", 0.0)
    for drv in ctx.drivers():
        des = drv.des
        top, note = ctx.g.driver_envelope(des)
        out = ctx.g.pin_named(des, "OUT")
        if not out or not out[1]:
            continue
        clamps = ctx.g.find_clamps(out[1], max_hops=8)
        if not clamps:
            continue
        tr = ctx.g.driver_transfer(des)
        if top is None:
            findings.append(Finding(
                "R1", SEV_INFO, f"driver:{des}", des,
                f"驱动级输出包络不可算（{'; '.join(tr['notes'])}）；"
                f"其输出网络挂有钳位件 {', '.join(c['des'] for c in clamps)}，"
                f"请人工确认量程是否被钳位",
                {"confidence": tr["confidence"], "notes": tr["notes"],
                 "clamps": [c["des"] for c in clamps]}))
            continue
        # 真正起限制作用者 = 钳位起始最低（见 _pick_clamp 说明）
        c0, onset = _pick_clamp(clamps, ctx.cfg)
        if onset is None:
            continue
        pol = c0["part"].attrs.get("POLARITY")
        margin = onset.min - top
        ev = {"driver": des, "driver_top_v": round(top, 3),
              "clamp": c0["des"], "clamp_part": c0["part"].title,
              "vbr_raw": c0["part"].attrs.raw_text("VBR"),
              "polarity": pol, "clamp_onset_v": round(onset.min, 3),
              "margin_v": round(margin, 3), "hops": c0["hops"],
              "transfer": {"gain": tr["gain"], "offset": tr["offset"],
                           "vref": tr["vref"], "rf": tr["rf"],
                           "rin": tr["rin"], "confidence": tr["confidence"]},
              "all_clamps": [c["des"] for c in clamps]}
        if margin < err_v:
            sev = SEV_ERROR
            msg = (f"输出量程被保护件吃掉：驱动可到 {top:.2f}V，"
                   f"但 {c0['des']}({c0['part'].title}) 钳位起始 "
                   f"{onset.min:.2f}V（VBR={c0['part'].attrs.raw_text('VBR')}"
                   f"{'，双向+0.7V' if is_bidirectional(pol) else ''}）——"
                   f"上端 {abs(margin):.2f}V（{abs(margin)/top:.0%}）不可达")
        elif margin < warn_v:
            sev = SEV_WARN
            msg = (f"钳位余量偏小：驱动可到 {top:.2f}V，钳位起始 "
                   f"{onset.min:.2f}V，余量仅 {margin:.2f}V（< {warn_v}V）")
        else:
            continue
        findings.append(Finding("R1", sev, f"driver:{des}", des, msg, ev))
    return findings


def rule_R2(ctx):
    """串联件能力 vs 最坏电流。

    仅对"驱动级输出链上的串联件"报：其额定电流能力与驱动级可能灌出的
    电流（用"到最近的钳位/地路径的电阻"粗估）比较。能力未知则不报。
    """
    findings = []
    for drv in ctx.drivers():
        out = ctx.g.pin_named(drv.des, "OUT")
        if not out or not out[1]:
            continue
        tr = ctx.g.driver_transfer(drv.des)
        top, _ = ctx.g.driver_envelope(drv.des)
        if top is None:
            continue
        clamps = ctx.g.find_clamps(out[1], max_hops=8)
        if not clamps:
            continue
        c0, onset = _pick_clamp(clamps, ctx.cfg)
        if onset is None:
            continue
        excess = top - onset.min               # 钳位点之上多出的电压
        if excess <= 0:
            continue
        # 输出链上可估阻值的串联件（用其阻值/DCR 估电流）
        hops = ctx.g.walk(out[1], max_hops=8)
        series = []
        for net in hops:
            for (d, pk) in ctx.g.net_pins.get(net, ()):
                p = ctx.g.part(d)
                if p and p.role == R_SERIES and p.is_two_pin:
                    r = p.attrs.qty("RESISTANCE") or p.attrs.qty("DCR")
                    series.append((p, r))
        rsum = sum(r.typ for _p, r in series if r and r.unit == "Ω")
        if rsum <= 0:
            continue
        i_worst = excess / rsum
        for p, _r in series:
            lim = p.attrs.qty("ISAT") or p.attrs.qty("IHOLD") or \
                  p.attrs.qty("I_RATED")
            if lim is None or lim.unit != "A":
                continue
            if i_worst > lim.min * ctx.cfg["rules"]["R2"].get(
                    "current_margin", 0.8):
                findings.append(Finding(
                    "R2", SEV_WARN, f"driver:{drv.des}", p.des,
                    f"串联件 {p.des}({p.title}) 电流能力 "
                    f"{lim.min*1000:.0f}mA < 最坏电流 {i_worst*1000:.0f}mA"
                    f"（{drv.des} 可高出钳位点 {excess:.2f}V / 链路 "
                    f"{rsum:.2f}Ω）",
                    {"part": p.title, "limit_a": lim.min,
                     "limit_raw": p.attrs.raw_text("ISAT")
                     or p.attrs.raw_text("IHOLD")
                     or p.attrs.raw_text("I_RATED"),
                     "worst_current_a": round(i_worst, 4),
                     "excess_v": round(excess, 3),
                     "series_r_ohm": round(rsum, 3)}))
    return findings


def rule_R3(ctx):
    """电源轨来源 / 参考脚核对（INFO——网表看不出刻意浮动接法）。"""
    findings = []
    # 收集所有"电源网名"（由 is_power_net 判定）与其上是否挂了源器件
    power_nets = {}
    for net, pins in ctx.g.net_pins.items():
        name = ctx.g.net_name.get(net) or ""
        if name and ctx.lr.is_power_net(name):
            power_nets.setdefault(name, set()).update(pins)
    for name, pins in sorted(power_nets.items()):
        has_src = any((ctx.g.part(d) and ctx.g.part(d).role == R_POWER)
                      for d, _pk in pins)
        # GND 不需要源
        if name.upper().find("GND") >= 0:
            continue
        if not has_src and len(pins) >= 2:
            findings.append(Finding(
                "R3", SEV_INFO, "power", name,
                f"电源轨 {name} 未发现可见源器件（稳压器/连接器/二极管），"
                f"可能来自板外或刻意浮动接法，需人工确认",
                {"net": name, "pin_count": len(pins),
                 "members": sorted({d for d, _ in pins})[:12]}))
    return findings


def rule_R4(ctx):
    """反相极性语义提示（INFO——供固件映射对照需求）。"""
    findings = []
    for drv in ctx.drivers():
        tr = ctx.g.driver_transfer(drv.des)
        if tr["gain"] is None or tr["confidence"] != "high":
            continue
        if tr["inverting"]:
            findings.append(Finding(
                "R4", SEV_INFO, f"driver:{drv.des}", drv.des,
                f"该级为反相放大（增益 -{tr['gain']:.3g}，Vin=0 时输出 "
                f"{tr['offset']:.2f}V）→ 软件映射需反相；"
                f"若需求文档按正相关描述（如 0~10V），评审需核对语义",
                {"gain": tr["gain"], "offset": tr["offset"],
                 "inverting": True, "vref": tr["vref"]}))
    return findings


RULES = {
    "R1": rule_R1,
    "R2": rule_R2,
    "R3": rule_R3,
    "R4": rule_R4,
}


def run_rules(graph, cfg, lr, only=None):
    """执行启用的规则，返回 [Finding]（按严重度排序）。"""
    ctx = Ctx(graph, cfg, lr)
    out = []
    for rid, fn in RULES.items():
        if only and rid not in only:
            continue
        if not cfg["rules"].get(rid, {}).get("enabled", True):
            continue
        try:
            out.extend(fn(ctx))
        except Exception as e:                       # 单规则失败不拖垮整轮
            out.append(Finding(rid, SEV_INFO, "runner", rid,
                               f"规则执行异常：{type(e).__name__}: {e}",
                               {"error": str(e)}))
    order = {SEV_ERROR: 0, SEV_WARN: 1, SEV_INFO: 2}
    out.sort(key=lambda f: (order.get(f.severity, 9), f.rule, f.subject))
    return out


# ---------------------------------------------------------------- 报告

def terminal_table(graph, cfg, lr):
    """端子电气包络表（R5 规格书雏形）：每驱动级一行。"""
    rows = []
    for drv in graph.parts.values():
        if drv.role != R_DRIVER:
            continue
        tr = graph.driver_transfer(drv.des)
        out = graph.pin_named(drv.des, "OUT")
        clamps = graph.find_clamps(out[1], max_hops=8) if out and out[1] else []
        top, _ = graph.driver_envelope(drv.des)
        c0, onset = _pick_clamp(clamps, cfg) if clamps else (None, None)
        rows.append({
            "driver": drv.des, "part": drv.title,
            "gain": tr["gain"], "vref": tr["vref"], "offset": tr["offset"],
            "top_v": top, "confidence": tr["confidence"],
            "clamp": c0["des"] if c0 else "",
            "clamp_vbr": c0["part"].attrs.raw_text("VBR") if c0 else "",
            "clamp_onset_v": round(onset.min, 3) if onset else None,
            "margin_v": (round(onset.min - top, 3)
                         if (onset and top is not None) else None),
            "inverting": tr["inverting"],
        })
    rows.sort(key=lambda r: r["driver"])
    return rows
