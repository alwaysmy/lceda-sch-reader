"""电路块识别层（第 1 层）：把"运放及其无源网络"认成已知电路块。

## 三层架构（本次重构，取代原先"只支持两电阻模型"的做法）

```
第1层 电路块识别   lceda_blocks.py   本文件——认出 inverting/SK/MFB/T型/跟随…
第2层 网表导出     lceda_spice.py    把块（或整页/整网）导出为 SPICE 网表
第3层 计算或仿真   公式（本文件 FORMULAS）+ LLM/SPICE
```

**为什么分层**（用户 2026-09-15 指示）：
- 原来把"识别拓扑"与"套公式"揉在一个函数里、硬编码两电阻模型，
  识别不了就降级放弃——这是"限定模型"。
- 实测反例：V2 信号板 U19 的反馈网络是 R73/R74/R75/R76 + C98/C100/C101
  + L8 的**复合网络**，不是纯 T 型，任何预设公式都覆盖不全。
- 正确做法：第 1 层只负责"认出是什么块"（含"认不出"这一结论），
  第 2 层**无条件**导出网表（通用兜底，不依赖识别成功），
  第 3 层才算：简单块直接套公式（SK/MFB 等可查表），复杂块交给 LLM/SPICE。
- **第 3 层不要求全自动**（LLM 执行），故本层只需把"块信息 + 网表"
  结构化输出，不追求闭式解覆盖所有拓扑。

## 已实现的块种类与判据

| kind | 判据 | 可算参数 |
| ---- | ---- | -------- |
| `follower` | OUT 与 IN- 同网（直连或 0Ω） | 增益=1 |
| `inverting_amp` | IN- 经 Rf 通输出侧、经 Rin 通外部输入 | 增益、偏置 |
| `non_inverting_amp` | IN+ 接输入、IN- 经分压通输出 | 增益、偏置 |
| `integrator` | IN- 经 C 通输出侧 + 经 R 通输入 | 时间常数 |
| `t_network` | 求和节点除 Rf 外还有 ≥2 条无源支路 | 交网表（复杂） |
| `sallen_key_lp` | IN+ 前 2R 串联 + 2C（中点→OUT、IN+→地） | fc、Q |
| `sallen_key_hp` | 同构但 C 串联 R 落地 | fc、Q |
| `mfb_lp` | IN- 节点挂 3R+2C（多重反馈） | fc、Q |
| `comparator` | 输出到输入**无**反馈路径 | —（提示） |
| `opamp_network` | 有源但认不出上述种类 | 交网表（兜底） |

识别不确定时给 `confidence` 并保留 `evidence`，符合工具既有的
"分级置信度"原则；**认不出不报错，而是标记交由第 3 层**。
"""

from __future__ import annotations

import math
import re

try:
    from lceda_attrs import Attrs
    from lceda_netgraph import (R_CLAMP, R_DRIVER, R_PASSIVE, R_SERIES,
                                R_SWITCH)
except ImportError:
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lceda_attrs import Attrs
    from lceda_netgraph import (R_CLAMP, R_DRIVER, R_PASSIVE, R_SERIES,
                                R_SWITCH)


# 块种类
K_FOLLOWER = "follower"
K_INVERTING = "inverting_amp"
K_NONINV = "non_inverting_amp"
K_INTEGRATOR = "integrator"
K_TNET = "t_network"
K_SK_LP = "sallen_key_lp"
K_SK_HP = "sallen_key_hp"
K_MFB_LP = "mfb_lp"
K_MFB_BP = "mfb_bp"
K_COMPARATOR = "comparator"
K_UNKNOWN = "opamp_network"

# ---------------------------------------------------------------- 注册表
#
# 设计目标（用户 2026-09-15）：**逐渐拓展的结构**——内置若干能力，同时可添加。
# 识别器与公式都走注册表：
#   - 内置项在文件末尾 _register_builtins() 注册；
#   - 扩展项由 load_extensions() 从工具目录 block_ext.py 导入，
#     该文件顶层调用 register_recognizer()/register_formula() 即可增补；
#   - 新拓扑**不需要改本文件**，也便于让 LLM 走"提议→落盘→回归"。
#
# 每项带 verified 标记：输出与文档据此打「未验证」标（docs/...§十三）。

VERIFIED_REAL = "real"        # 在真实工程样本上验证过
VERIFIED_SYNTH = "synthetic"  # 仅合成样本验证
VERIFIED_STUB = "stub"        # 未验证


class Recognizer:
    """一条块识别规则。``fn(nb) -> Block|None``；priority 小者先试。"""

    __slots__ = ("kind", "fn", "priority", "verified", "note", "source")

    def __init__(self, kind, fn, priority=50, verified=VERIFIED_STUB,
                 note="", source="builtin"):
        self.kind = kind
        self.fn = fn
        self.priority = priority
        self.verified = verified
        self.note = note
        self.source = source

    def __repr__(self):
        return (f"<Rec {self.kind} p={self.priority} "
                f"{self.verified} {self.source}>")


class Formula:
    """一条闭式解公式。``fn(block) -> dict``（第 3 层，可算则返回值）。"""

    __slots__ = ("kind", "fn", "verified", "note", "source")

    def __init__(self, kind, fn, verified=VERIFIED_STUB, note="",
                 source="builtin"):
        self.kind = kind
        self.fn = fn
        self.verified = verified
        self.note = note
        self.source = source


RECOGNIZERS = []      # [Recognizer]，按 priority 排序
FORMULAS = {}         # kind -> Formula
_LOADING_SOURCE = None   # 扩展加载期间置 "ext:<file>"，供 source 自动标注


def _resolve_source(source):
    if source and source != "builtin":
        return source
    return _LOADING_SOURCE or "builtin"


def register_recognizer(kind, fn, priority=50, verified=VERIFIED_STUB,
                        note="", source="builtin"):
    """注册一条块识别规则（内置或扩展）。同 kind 重复注册则覆盖。"""
    src = _resolve_source(source)
    for i, r in enumerate(RECOGNIZERS):
        if r.kind == kind:
            RECOGNIZERS[i] = Recognizer(kind, fn, priority, verified, note,
                                        src)
            RECOGNIZERS.sort(key=lambda x: x.priority)
            return RECOGNIZERS[i]
    RECOGNIZERS.append(Recognizer(kind, fn, priority, verified, note, src))
    RECOGNIZERS.sort(key=lambda x: x.priority)
    return RECOGNIZERS[-1]


def register_formula(kind, fn, verified=VERIFIED_STUB, note="",
                     source="builtin"):
    """注册一个块种类的闭式解（第 3 层）。"""
    FORMULAS[kind] = Formula(kind, fn, verified, note,
                             _resolve_source(source))
    return FORMULAS[kind]


def is_formula_kind(kind):
    """该种类当前是否有闭式解（替代静态 FORMULA_KINDS 常量）。"""
    return kind in FORMULAS


def verified_of(kind):
    """某块种类的验证状态（供输出打标记）。"""
    f = FORMULAS.get(kind)
    if f:
        return f.verified
    for r in RECOGNIZERS:
        if r.kind == kind:
            return r.verified
    return VERIFIED_STUB


def registry_info():
    """注册表自省（供 CLI/文档输出：能力/验证状态/来源）。"""
    return {
        "recognizers": [
            {"kind": r.kind, "priority": r.priority, "verified": r.verified,
             "source": r.source, "note": r.note} for r in RECOGNIZERS],
        "formulas": [
            {"kind": k, "verified": f.verified, "source": f.source,
             "note": f.note} for k, f in sorted(FORMULAS.items())],
    }


def load_extensions(path=None):
    """加载可选扩展文件（工具目录 block_ext.py）。

    扩展文件在模块顶层调用 register_recognizer/register_formula 即可增补
    能力；文件不存在时静默跳过（正常情况）。
    """
    import os as _os
    import sys as _sys
    p = path or _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                              "block_ext.py")
    if not _os.path.isfile(p):
        return {"loaded": False, "path": p, "reason": "不存在（正常）"}
    global _LOADING_SOURCE
    try:
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("block_ext", p)
        mod = _ilu.module_from_spec(spec)
        _sys.modules["block_ext"] = mod
        _LOADING_SOURCE = "ext:" + _os.path.basename(p)
        try:
            spec.loader.exec_module(mod)
        finally:
            _LOADING_SOURCE = None
        n_rec = sum(1 for r in RECOGNIZERS if r.source.startswith("ext:"))
        n_fml = sum(1 for f in FORMULAS.values()
                    if f.source.startswith("ext:"))
        return {"loaded": True, "path": p,
                "recognizers": n_rec, "formulas": n_fml}
    except Exception as e:
        _LOADING_SOURCE = None
        return {"loaded": False, "path": p,
                "reason": f"{type(e).__name__}: {e}"}


# 历史常量（保留兼容旧引用；能力查询请用 is_formula_kind）
FORMULA_KINDS = set()



class Block:
    """一个识别出的电路块。"""

    __slots__ = ("kind", "confidence", "anchor", "channel", "members",
                 "nets", "params", "evidence", "graph", "source_verified")

    def __init__(self, kind, anchor, graph, channel="", confidence="low"):
        self.kind = kind
        self.anchor = anchor          # 驱动件位号（运放）
        self.channel = channel        # 多通道运放的通道后缀
        self.graph = graph
        self.confidence = confidence
        self.members = set()          # 参与的无源件位号
        self.nets = {}                # 角色 -> net_key
        self.params = {}              # 提取到的元件值
        self.evidence = []
        self.source_verified = None   # 由 recognize() 从注册表回填

    @property
    def label(self):
        return f"{self.anchor}{('#' + self.channel) if self.channel else ''}"

    def can_compute(self):
        return is_formula_kind(self.kind) and self.confidence != "low"

    @property
    def verified(self):
        return verified_of(self.kind)

    def as_dict(self):
        return {"kind": self.kind, "anchor": self.anchor,
                "channel": self.channel, "confidence": self.confidence,
                "verified": self.verified,
                "members": sorted(self.members),
                "params": {k: (round(v, 6) if isinstance(v, float) else v)
                           for k, v in self.params.items()},
                "evidence": self.evidence}


# ---------------------------------------------------------------- 邻域

class _NB:
    """一个驱动通道的邻域视图（引脚->net + 可达无源件）。"""

    def __init__(self, graph, des, chan_keys, chan=""):
        self.g = graph
        self.des = des
        self.chan = chan
        # base(OUT/IN+/IN-/V+/V-) -> pin_key
        self.pin = dict(chan_keys)

    def net(self, base):
        k = self.pin.get(base)
        return self.g.pin_net.get((self.des.upper(), k)) if k else None

    def parts_on(self, net):
        """网络上挂的 (des, pin, Part)；排除本驱动自身。"""
        out = []
        for (d, pk) in self.g.net_pins.get(net, ()):
            if d == self.des.upper():
                continue
            p = self.g.part(d)
            if p:
                out.append((p.des, pk, p))
        return out

    def series_branches(self, net, exclude=()):
        """网络上挂的两脚无源件及其"另一端网络"。"""
        out = []
        for (d, pk, p) in self.parts_on(net):
            if p.role not in (R_SERIES, R_PASSIVE) or not p.is_two_pin:
                continue
            if d in exclude:
                continue
            for o in self.g.other_pins(d, pk):
                onet = self.g.pin_net.get((d.upper(), o))
                if onet and onet != net:
                    out.append((d, pk, p, onet))
        return out

    # parts_on_series/shunt 统一为"该网上的两脚无源支路"，由调用方按
    # 元件角色（R/C）与另一端去向（OUT 侧/地）区分——避免两套重复实现。
    def parts_on_series(self, net):
        return self.series_branches(net)

    def parts_on_shunt(self, net):
        return self.series_branches(net)

    def caps_on(self, net):
        return [(d, pk, p) for (d, pk, p) in self.parts_on(net)
                if p.role == R_PASSIVE and _is_cap(p)]

    def resistors_on(self, net):
        return [(d, pk, p) for (d, pk, p) in self.parts_on(net)
                if p.role == R_SERIES and _is_res(p)]


def _is_cap(part):
    return str(part.des).upper().startswith(("C", "CBB", "CTC")) or \
        part.attrs.has("CAPACITANCE")


def _is_res(part):
    return part.attrs.has("RESISTANCE")


def _r(part):
    q = part.attrs.qty("RESISTANCE")
    return q.typ if q and q.unit == "Ω" else None


def _c(part):
    q = part.attrs.qty("CAPACITANCE")
    return q.typ if q and q.unit == "F" else None


def _voltage_from_netname(net):
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


# ---------------------------------------------------------------- 识别

def _walk_out_side(nb, out_net, exclude=()):
    """从输出端沿无源件可达的网络集合（排除给定网络，避免绕回求和节点）。"""
    return set(nb.g.walk(out_net, max_hops=6, exclude=set(exclude))) | {out_net}


def _rec_sk(nb):
    """Sallen-Key 二阶滤波（单位增益常见）：IN+ 经**两级串联 RC** 接输入。

    标准 LP 拓扑（实测/教科书）：
        VIN ─R1─ MID ─R2─ IN+ ─┬─ C2 ─ GND
                     └─ C1 ────┘（C1 从 MID 到 OUT，构成 SK 正反馈抽头）
    判据（LP）：
      1) IN+ 上挂一个**落地电容**（C2）——shunt 到地/电源
      2) IN+ 经一个**串联电阻**（R2）到 MID
      3) MID 上挂一个**通 OUT 侧**的电容（C1，SK 抽头）
      4) MID 再经一个**串联电阻**（R1）到输入（VIN）
    HP 版对偶（串 C 并 R）。
    """
    inp = nb.net("IN+")
    if not inp:
        return None
    out_net = nb.net("OUT")
    if not out_net:
        return None
    is_power = nb.g._lr.is_power_net if nb.g._lr else \
        (lambda n: "GND" in str(n).upper())

    def _goes_to_power(net):
        nm = nb.g.net_name.get(net) or ""
        return bool(nm and is_power(nm))

    out_reach = _walk_out_side(nb, out_net, exclude=(inp,))

    for kind, ser, sh in ((K_SK_LP, _is_res, _is_cap),
                          (K_SK_HP, _is_cap, _is_res)):
        # 1) IN+ 的落地 shunt 件（ser/sh 对偶）
        shunt = [(d, pk, p, onet) for (d, pk, p, onet)
                 in nb.series_branches(inp)
                 if sh(p) and _goes_to_power(onet)]
        # 2) IN+ 的串联件 -> MID
        to_mid = [(d, pk, p, onet) for (d, pk, p, onet)
                  in nb.series_branches(inp)
                  if ser(p) and not _goes_to_power(onet) and onet != out_net]
        if len(shunt) != 1 or len(to_mid) != 1:
            continue
        mid = to_mid[0][3]
        # 3) MID 上有通 OUT 侧的 shunt 件（SK 抽头）
        tap = [(d, pk, p, onet) for (d, pk, p, onet)
               in nb.series_branches(mid)
               if sh(p) and onet in out_reach and d != to_mid[0][0]]
        # 4) MID 经串联件到更远的输入（VIN）
        chain = [(d, pk, p, onet) for (d, pk, p, onet)
                 in nb.series_branches(mid)
                 if ser(p) and d != to_mid[0][0]
                 and onet not in out_reach and onet != inp]
        if tap and chain:
            blk = Block(kind, nb.des, nb.g, nb.chan, "high")
            blk.members |= {shunt[0][0], to_mid[0][0], tap[0][0], chain[0][0]}
            blk.nets.update(inp=inp, mid=mid, out=out_net,
                            vin=chain[0][3])
            # 参数按拓扑角色命名，与公式约定一致：
            #  R1=输入侧串阻(chain) R2=靠IN+串阻(to_mid)
            #  C1=抽头电容(tap)     C2=IN+落地电容(shunt)
            if kind == K_SK_LP:
                blk.params.update(
                    r1=_r(chain[0][2]), r2=_r(to_mid[0][2]),
                    c1=_c(tap[0][2]), c2=_c(shunt[0][2]))
            else:
                blk.params.update(
                    r1=_c(chain[0][2]), r2=_c(to_mid[0][2]),
                    c1=_r(tap[0][2]), c2=_r(shunt[0][2]))
            blk.evidence.append(
                f"{kind}: {chain[0][0]}(串)→{mid[:12]}→{to_mid[0][0]}(串)→IN+，"
                f"{tap[0][0]}(MID→OUT 抽头)，{shunt[0][0]}(IN+ 落地)")
            return blk
    return None


def _rec_mfb(nb):
    """多重反馈（MFB）：IN- 节点挂 3 个 R（输入/反馈/落地）+ 2 个 C
    （反馈电容、输入落地电容）。与 inverting 的区别是**求和节点就在 IN-**，
    且电容参与反馈（不是纯补偿）。"""
    inn = nb.net("IN-")
    if not inn:
        return None
    rs = nb.resistors_on(inn)
    cs = nb.caps_on(inn)
    out_net = nb.net("OUT")
    if not out_net:
        return None
    # out_reach 需排除"可能经 R 到地的落地支路"干扰：先取 OUT 侧可达
    out_reach = _walk_out_side(nb, out_net)
    fb = [x for x in rs
          if (nb.g.pin_net.get((x[2].des.upper(),
                                nb.g.other_pins(x[0], x[1])[0])
                               if nb.g.other_pins(x[0], x[1]) else None)
              in out_reach)]
    # MFB 特征：IN- 上 R≥2、C≥2（典型 3R2C），且至少 1 条 R 通向 OUT 侧
    if len(rs) >= 2 and len(cs) >= 2 and fb:
        blk = Block(K_MFB_LP, nb.des, nb.g, nb.chan, "medium")
        blk.members |= {d for d, _p, _o in rs} | {d for d, _p, _o in cs}
        blk.nets.update(inn=inn, out=out_net)
        blk.evidence.append(
            f"MFB 形态: IN- 挂 {len(rs)}R + {len(cs)}C，反馈 {fb[0][0]}")
        return blk
    return None


def _rec_tnet(nb):
    """T 型/多电阻反馈：求和节点除 Rf、Rin 外**还有额外电阻支路**。

    关键：只数**电阻**支路，且**排除通向电源/地网的支路**——否则电源去耦
    电容与旁路电阻会让任何一级都被误判成 T 型（实测 U16 曾因此被吞掉）。
    """
    inn = nb.net("IN-")
    if not inn:
        return None
    first = nb.series_branches(inn)
    if not first:
        return None
    sum_net = first[0][3]
    out_net = nb.net("OUT")
    out_reach = _walk_out_side(nb, out_net, exclude=(sum_net,)) if out_net else set()
    is_power = nb.g._lr.is_power_net if nb.g._lr else \
        (lambda n: "GND" in str(n).upper())
    r_branches, c_branches = [], []
    drv_input_nets = {inn, nb.net("IN+")} - {None}
    for (d, pk, p, onet) in nb.series_branches(sum_net):
        name = nb.g.net_name.get(onet) or ""
        if name and is_power(name):
            continue                       # 电源/地旁路不算
        if onet in drv_input_nets:
            continue                       # 通向驱动自身输入 = 隔离电阻，不计支路
        if _is_res(p):
            r_branches.append((d, onet, p))
        elif _is_cap(p):
            c_branches.append((d, onet, p))
    # 需 ≥3 条电阻支路（Rf + Rin + 额外）才超出两电阻模型
    if len(r_branches) < 3:
        return None
    blk = Block(K_TNET, nb.des, nb.g, nb.chan, "high")
    blk.members.add(first[0][0])
    for (d, _o, _p) in r_branches:
        blk.members.add(d)
    for (d, _o, _p) in c_branches:
        blk.members.add(d)               # 同节点的补偿/滤波电容一并纳入
    blk.nets.update(inn=inn, sum=sum_net, out=out_net)
    blk.evidence.append(
        f"求和节点 {sum_net[:14]} 有 {len(r_branches)} 条电阻支路（>2），"
        f"超出两电阻模型：{', '.join(d for d,_,_ in r_branches)}"
        + (f"；同节点电容 {', '.join(d for d,_,_ in c_branches)}"
           if c_branches else ""))
    return blk


def _rec_follower(nb):
    out_net, inn = nb.net("OUT"), nb.net("IN-")
    if out_net and inn and out_net == inn:
        blk = Block(K_FOLLOWER, nb.des, nb.g, nb.chan, "high")
        blk.nets.update(out=out_net, inn=inn, inp=nb.net("IN+"))
        blk.params["gain"] = 1.0
        blk.evidence.append("OUT 与 IN- 同网 → 电压跟随")
        return blk
    # 经 0Ω/短接符相连也算
    for (d, _pk, p, onet) in nb.series_branches(inn) if inn else []:
        if onet == out_net and (p.role == R_SERIES and _r(p) == 0):
            blk = Block(K_FOLLOWER, nb.des, nb.g, nb.chan, "medium")
            blk.members.add(d)
            blk.nets.update(out=out_net, inn=inn, inp=nb.net("IN+"))
            blk.params["gain"] = 1.0
            blk.evidence.append(f"OUT 经 0Ω({d}) 接 IN- → 跟随")
            return blk
    return None


def _rec_integrator(nb):
    inn = nb.net("IN-")
    out_net = nb.net("OUT")
    if not (inn and out_net):
        return None
    out_reach = _walk_out_side(nb, out_net, exclude=(inn,))
    for (d, _pk, p, onet) in nb.series_branches(inn):
        if onet in out_reach and _is_cap(p):
            rin = [x for x in nb.series_branches(inn)
                   if _is_res(x[2]) and x[3] not in out_reach]
            if rin:
                blk = Block(K_INTEGRATOR, nb.des, nb.g, nb.chan, "high")
                blk.members |= {d, rin[0][0]}
                blk.nets.update(inn=inn, out=out_net, vin=rin[0][3])
                blk.params.update(r=_r(rin[0][2]), c=_c(p))
                if blk.params["r"] and blk.params["c"]:
                    blk.params["tau"] = blk.params["r"] * blk.params["c"]
                blk.evidence.append(f"IN- 经 C({d}) 反馈 + R({rin[0][0]}) 输入 → 积分器")
                return blk
    return None


def _sum_node(nb):
    """求和节点：IN- 经**电阻**（不是电容）到达的节点——运放输入无电流，
    故 V(求和)=V(IN-)=Vref，R 是唯一信号通路；电容是补偿/反馈元件，不通 DC。

    实测 V2 U16：IN- 上挂 C83(反馈电容) 与 R66(隔离电阻)，求和节点在 R66 另一端。
    """
    inn = nb.net("IN-")
    if not inn:
        return None
    for (d, _pk, p, onet) in nb.series_branches(inn):
        if _is_res(p):
            return onet
    return None


def _rec_inverting(nb):
    """反相/同相放大：IN- 经 R 到求和节点，求和节点上 Rf 通输出侧、Rin 通输入。

    判据用"从 OUT 排除求和节点后的可达集"识别 Rf——这样不会把输入侧
    （经 Rf→求和节点→Rin 可达）误当输出侧。
    """
    inn = nb.net("IN-")
    out_net = nb.net("OUT")
    if not (inn and out_net):
        return None
    sum_net = _sum_node(nb)
    if sum_net is None:
        return None
    out_reach = _walk_out_side(nb, out_net, exclude=(sum_net,))
    rf = rin = None
    drv_input_nets = {inn, nb.net("IN+")} - {None}
    for (d, _pk, p, onet) in nb.series_branches(sum_net):
        if not _is_res(p):
            continue
        if onet in out_reach:
            rf = rf or (d, p, onet)
        elif onet not in drv_input_nets:
            rin = rin or (d, p, onet)
    if not (rf and rin):
        return None
    # T 型检测：Rin 通向的"输入节点"上**还挂着别的电阻** → 输入不是直接
    # 进来，而是经 T 型/两级网络（实测 V2 U19：求和节点 -R75- (605,160)
    # -R74- 输入，另有 R76；简单两电阻模型会算出错误的 7.27 增益而漏掉
    # 真实的 4.364）。此时交 tnet/网表，不给闭式解。
    rin_node = rin[2]
    further = [q for q in nb.g.net_pins.get(rin_node, ())
               if (nb.g.part(q[0]) and nb.g.part(q[0]).role == R_SERIES
                   and _is_res(nb.g.part(q[0]))
                   and q[0].upper() not in (rin[0].upper(), rf[0].upper())
                   and _branch_other_net(nb, nb.g.part(q[0]), q[1]) != sum_net)]
    if further:
        return None
    # 求和节点上还有别的**电阻**支路 → 交 T 型/网表（这里只认最简两电阻）。
    # 但排除"通向驱动自身输入引脚网"的隔离电阻——实测 V2 U16 的 R66(3.9k)
    # 连 IN- 自身，因运放输入无电流而不影响直流增益，文档公式里也不出现，
    # 不应把它当成额外支路而否掉这个最简反相级。
    drv_in2 = drv_input_nets
    extra = [d for (d, _pk, _p, onet) in nb.series_branches(sum_net)
             if d not in (rf[0], rin[0]) and _is_res(_p)
             and onet not in drv_in2]
    if extra:
        return None
    blk = Block(K_INVERTING, nb.des, nb.g, nb.chan, "high")
    blk.members |= {rf[0], rin[0]}
    blk.nets.update(inn=inn, sum=sum_net, out=out_net,
                    vin=rin[2], inp=nb.net("IN+"))
    blk.params.update(rf=_r(rf[1]), rin=_r(rin[1]))
    blk.evidence.append(
        f"IN- ─R({_sum_branch_des(nb, inn)})─ 求和节点，"
        f"Rf({rf[0]})→输出侧、Rin({rin[0]})→输入({rin[2][:12]}) → 反相级")
    return blk


def _sum_branch_des(nb, inn):
    for (d, _pk, p, _onet) in nb.series_branches(inn):
        if _is_res(p):
            return d
    return "?"


def _branch_other_net(nb, part, pin_key):
    """两脚件在给定引脚之外的"另一端"网络。"""
    others = nb.g.other_pins(part.des, pin_key)
    return nb.g.pin_net.get((part.des.upper(), others[0])) if others else None


def _rec_noninv(nb):
    """同相放大：IN+ 接外部输入，IN- 经分压（Rf 通 OUT 侧、Rg 通地）。"""
    inp = nb.net("IN+")
    out_net = nb.net("OUT")
    inn = nb.net("IN-")
    if not (inp and out_net and inn):
        return None
    # IN+ 直接连"外部输入"（不是本驱动输出侧、不是地）
    out_reach = _walk_out_side(nb, out_net)
    if inp in out_reach:
        return None                      # 这是跟随器形态
    is_power = nb.g._lr.is_power_net if nb.g._lr else \
        (lambda n: "GND" in str(n).upper())
    nm = nb.g.net_name.get(inp) or ""
    if nm and is_power(nm):
        return None                      # IN+ 接地/电源 → 不是同相放大
    # IN- 上两个 R：一个通 OUT 侧，一个通地
    rf = rg = None
    for (d, _pk, p, onet) in nb.series_branches(inn):
        if not _is_res(p):
            continue
        onm = nb.g.net_name.get(onet) or ""
        if onet in out_reach:
            rf = rf or (d, p)
        elif onm and is_power(onm) and ("GND" in onm.upper()):
            rg = rg or (d, p)
    if not (rf and rg):
        return None
    blk = Block(K_NONINV, nb.des, nb.g, nb.chan, "high")
    blk.members |= {rf[0], rg[0]}
    blk.nets.update(inn=inn, out=out_net, inp=inp, vin=inp)
    blk.params.update(rf=_r(rf[1]), rg=_r(rg[1]))
    blk.evidence.append(f"IN+({inp[:12]}) 接输入，IN- 经 Rf({rf[0]})/Rg({rg[0]}) 分压 → 同相级")
    return blk


def _rec_comparator(nb):
    inn, inp, out_net = nb.net("IN-"), nb.net("IN+"), nb.net("OUT")
    if not out_net:
        return None
    out_reach = _walk_out_side(nb, out_net)
    tied = any(onet in out_reach for (_d, _pk, _p, onet)
               in nb.series_branches(inn) if inn) if inn else False
    if not tied:
        blk = Block(K_COMPARATOR, nb.des, nb.g, nb.chan, "medium")
        blk.nets.update(out=out_net, inn=inn, inp=inp)
        blk.evidence.append("OUT 到 IN- 无反馈路径 → 比较器/开环")
        return blk
    return None


def recognize(graph, des, chan=None):
    """识别一个运放（通道）的电路块。返回 Block（认不出则 opamp_network）。"""
    p = graph.part(des)
    if not p or p.role != R_DRIVER:
        return None
    chans = graph.channel_pins(des)
    picks = [(suf, d) for suf, d in chans.items()
             if {"OUT", "IN+", "IN-"} <= set(d)]
    if not picks:
        return None
    if chan is not None:
        picks = [x for x in picks if x[0] == chan] or picks
    best = None
    for suf, keys in picks:
        nb = _NB(graph, des, keys, suf)
        # 识别顺序由注册表 priority 决定（小者先试）：SK/MFB(10，结构特征最
        # 明确且 OUT↔IN- 可能同网须先于 follower) → 跟随/积分(20) → 同相/反相
        # (30) → T 型(90，判据最宽兜底归类) → 比较器(95)。
        for rec in RECOGNIZERS:
            try:
                blk = rec.fn(nb)
            except Exception:
                continue                 # 单个识别器出错不拖垮整轮
            if blk is not None:
                blk.source_verified = rec.verified
            if blk and blk.confidence == "high":
                return blk
            if blk and best is None:
                best = blk
    if best:
        return best
    # 兜底：有源但认不出 → 交第 3 层
    suffix = picks[0][0] if picks else ""
    blk = Block(K_UNKNOWN, des, graph, suffix, "low")
    blk.nets.update(out=graph.pin_net.get((des.upper(),
                                          chans.get(suffix, {}).get("OUT"))),
                    inn=graph.pin_net.get((des.upper(),
                                          chans.get(suffix, {}).get("IN-"))),
                    inp=graph.pin_net.get((des.upper(),
                                          chans.get(suffix, {}).get("IN+"))))
    blk.evidence.append("未匹配已知块种类 → 导出网表交 LLM/SPICE 分析")
    return blk


def recognize_all(graph):
    """识别图中所有驱动块。"""
    out = []
    for p in graph.parts.values():
        if p.role != R_DRIVER:
            continue
        blk = recognize(graph, p.des)
        if blk:
            out.append(blk)
    out.sort(key=lambda b: (b.anchor, b.channel))
    return out


# ---------------------------------------------------------------- 第3层公式

def _vref_of(block):
    return _voltage_from_netname(block.nets.get("vin") or "")         or _voltage_from_netname(block.graph.net_name.get(
            block.nets.get("inp") or "", ""))


def _fml_follower(block):
    return {"gain": 1.0, "offset": _vref_of(block), "inverting": False}


def _fml_inverting(block):
    pr = block.params
    if not (pr.get("rf") and pr.get("rin")):
        return {}
    out = {"gain": -pr["rf"] / pr["rin"], "inverting": True,
           "vref": _vref_of(block), "rf": pr["rf"], "rin": pr["rin"]}
    v = out["vref"]
    if v is not None:
        out["offset"] = v * (1 + pr["rf"] / pr["rin"])
    return out


def _fml_noninv(block):
    """⚠ 未验证（verified=stub）——标准同相式，未在真实/合成样本验证。"""
    pr = block.params
    if not (pr.get("rf") and pr.get("rg")):
        return {}
    gain = 1 + pr["rf"] / pr["rg"]
    v = _vref_of(block)
    return {"gain": gain, "inverting": False, "vref": v,
            "rf": pr["rf"], "rg": pr["rg"],
            "offset": v * gain if v is not None else None}


def _fml_integrator(block):
    """⚠ 未验证（verified=stub）。"""
    tau = block.params.get("tau")
    if not tau:
        return {}
    return {"tau_s": tau, "f_unity_hz": 1.0 / (2 * math.pi * tau)}


def _fml_sk(block):
    """Sallen-Key 单位增益：fc=1/(2π√(R1R2C1C2))，Q=√(R1R2C1C2)/(C2(R1+R2))。

    验证：⚠ synthetic——仅合成样本（R=10k/C=10n → 1591.55Hz/Q=0.5）；
    真实工程尚无样本。
    """
    pr = block.params
    r1, r2, c1, c2 = (pr.get("r1"), pr.get("r2"), pr.get("c1"),
                      pr.get("c2"))
    if not all((r1, r2, c1, c2)):
        return {}
    fc = 1.0 / (2 * math.pi * math.sqrt(r1 * r2 * c1 * c2))
    q = math.sqrt(r1 * r2 * c1 * c2) / (c2 * (r1 + r2))
    return {"fc_hz": fc, "q": q, "order": 2}


def _fml_mfb(block):
    """⚠ 未验证（verified=stub）——参数提取(3R2C)未完成，当前恒返回 {}。"""
    pr = block.params
    need = ("r1", "r2", "r3", "c1", "c2")
    if not all(pr.get(k) for k in need):
        return {"note": "MFB 参数提取未完成（需 3R+2C），交网表/LLM"}
    r1, r2, r3 = pr["r1"], pr["r2"], pr["r3"]
    c1, c2 = pr["c1"], pr["c2"]
    fc = 1.0 / (2 * math.pi * math.sqrt(r2 * r3 * c1 * c2))
    q = math.sqrt(r2 * r3 * c1 * c2) / (c2 * (r2 + r3)) * (1 + r3 / r1)
    return {"fc_hz": fc, "q": q, "order": 2, "gain_dc": -r2 / r1}


def _fml_none(block):
    """无闭式解——显式声明"交第2层网表"。"""
    return {}


def evaluate(block):
    """对可闭式计算的块套公式（第 3 层；不需仿真/LLM）。

    公式取自 FORMULAS 注册表——扩展新块种类时一并 register_formula 即可，
    本函数无需改动。不可算返回 {}（调用方转交第 2 层网表）。
    """
    if not block.can_compute():
        return {}
    f = FORMULAS.get(block.kind)
    if f is None:
        return {}
    try:
        return f.fn(block)
    except (ZeroDivisionError, ValueError, TypeError, AttributeError):
        return {}


def features(block, graph):
    """第 3 层（LLM/SPICE）所需的块特征：元件清单+网络+量值。"""
    comps = []
    for des in sorted(block.members):
        p = graph.part(des)
        if not p:
            continue
        comps.append({"designator": p.des, "title": p.title,
                      "kind": ("C" if _is_cap(p) else
                               "R" if _is_res(p) else "L" if p.attrs.has("INDUCTANCE")
                               else "other"),
                      "value": (p.attrs.raw_text("RESISTANCE")
                                or p.attrs.raw_text("CAPACITANCE")
                                or p.attrs.raw_text("INDUCTANCE") or "")})
    nets = {}
    for role, key in block.nets.items():
        name = graph.net_name.get(key) or key
        members = sorted({d for d, _ in graph.net_pins.get(key, ())})
        nets[role] = {"net": name, "members": members}
    return {"components": comps, "nets": nets}


# ---------------------------------------------------------------- 内置注册
#
# priority 小者先试；顺序 = 从"结构特征最明确"到"最宽泛"：
#   10 SK/MFB（结构特征明确，且 OUT↔IN- 可能同网必须先于 follower）
#   20 follower / 积分器
#   30 同相 / 反相（最简放大）
#   90 T 型（判据最宽，兜底归类，避免吞掉最简级）
#   95 比较器（无反馈=开环）
#
# verified 依据见 docs/电气规则层-实现说明.md §十三「验证状态」表：
#   real      = 真实工程验证
#   synthetic = 仅合成样本
#   stub      = 未验证
def _register_builtins():
    reg = register_recognizer
    # SK 的 LP/HP 是同一识别器的对偶分支（函数内循环、返回实际匹配的
    # kind），故只注册一次（kind 取 LP 作代表），避免同一函数被调两遍。
    reg(K_SK_LP, _rec_sk, priority=10, verified=VERIFIED_SYNTH,
        note="SK 二阶（LP/HP 对偶）；合成样本验证 LP"
             "（R=10k/C=10n → 1591.55Hz/Q=0.5）；真实工程尚无样本")
    reg(K_MFB_LP, _rec_mfb, priority=10, verified=VERIFIED_STUB,
        note="识别形态已实现；参数提取(3R2C)未完成，公式恒返回空")
    reg(K_FOLLOWER, _rec_follower, priority=20, verified=VERIFIED_REAL,
        note="v4(U3#A) 与 Piezo(U31#A/U56#B) 真实验证")
    reg(K_INTEGRATOR, _rec_integrator, priority=20, verified=VERIFIED_STUB,
        note="未在真实工程或合成样本上验证")
    reg(K_NONINV, _rec_noninv, priority=30, verified=VERIFIED_STUB,
        note="未验证")
    reg(K_INVERTING, _rec_inverting, priority=30, verified=VERIFIED_REAL,
        note="V2 信号板 U16/U18 真实验证（增益 4.286/offset 10.36）")
    reg(K_TNET, _rec_tnet, priority=90, verified=VERIFIED_REAL,
        note="V2 信号板 U19 真实验证（复合网络，正确降级不给错值）")
    reg(K_COMPARATOR, _rec_comparator, priority=95, verified=VERIFIED_STUB,
        note="未验证")

    fml = register_formula
    fml(K_FOLLOWER, _fml_follower, verified=VERIFIED_REAL)
    fml(K_INVERTING, _fml_inverting, verified=VERIFIED_REAL)
    fml(K_NONINV, _fml_noninv, verified=VERIFIED_STUB)
    fml(K_INTEGRATOR, _fml_integrator, verified=VERIFIED_STUB)
    fml(K_SK_LP, _fml_sk, verified=VERIFIED_SYNTH)
    fml(K_SK_HP, _fml_sk, verified=VERIFIED_STUB,
        note="与 LP 同式（fc 对偶相同）；HP 未单独验证")
    fml(K_MFB_LP, _fml_mfb, verified=VERIFIED_STUB,
        note="标准反相 MFB 低通式；参数提取未完成故当前恒返回空")
    fml(K_TNET, _fml_none, verified=VERIFIED_REAL,
        note="交第2层网表（复合网络无预设公式）")
    fml(K_UNKNOWN, _fml_none, verified=VERIFIED_REAL,
        note="兜底种类：交网表/LLM")


_register_builtins()
