"""属性串结构化：立创EDA 器件描述串 → 规范键 + 可比较的 SI 量值。

## 为什么需要这一层

EDA 的器件属性是**人类可读的中文字符串**：
    "极性:双向;反向截止电压(Vrwm):5V;击穿电压:7V;钳位电压:12V;"
它能被人读懂、却是**字符串、不可比较**——审查规则无法问"这颗 TVS 的
击穿电压是否低于驱动级可达上限"。本模块把它解析成
``{规范键: Quantity}``，供审查规则 / BOM / 选型共用。

## 分层位置

这与后端里的"格式归一化"（V2/V3/ZIP 容器差异 → 统一模型）**是两类**：
属性串是立创EDA 自身的数据格式，三种后端吐出的都是同一串，不属于任何
后端。故本模块是**语义归一化层**，独立于 backends。

## 依据

规范键与单位取自对 5 个真实工程的全量普查（``probes/attr_survey.py``，
174 个属性键），只登记实测出现过的键名，不臆造（仓库"参数依据纪律"）。
"""

from __future__ import annotations

import re
from math import floor, log10


def _sig(x, n=12):
    """归整到 n 位有效数字，消除浮点噪声（6.4+0.7 -> 7.1 而非 7.100000...05）。

    规则层要做数值比较（钳位余量 < 0.5V 判 WARN），尾差会污染判据。
    """
    if x == 0:
        return 0.0
    try:
        return round(x, -int(floor(log10(abs(x)))) + (n - 1))
    except (ValueError, OverflowError):
        return x


# ---------------------------------------------------------------- SI 量值

# 数量级前缀（大小写敏感：m=毫 / M=兆）
_PREFIX = [
    ("p", 1e-12), ("n", 1e-9), ("u", 1e-6), ("µ", 1e-6), ("μ", 1e-6),
    ("m", 1e-3), ("k", 1e3), ("K", 1e3), ("M", 1e6), ("G", 1e9),
]

# 基本电学单位（归一化后的写法）
_BASE = {
    "V": "V", "A": "A", "Ohm": "Ω", "F": "F", "H": "H", "W": "W",
    "Hz": "Hz", "s": "s", "S": "S",
}

_NUM_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")
_TAIL_RE = re.compile(r"^[^\d\s,;()]*")

# 无值占位（实测 '-' 出现 64+ 次）
_NULLISH = {"", "-", "—", "–", "N/A", "n/a", "NA", "null", "None"}


def _norm_text(s):
    """统一 Unicode（Ω/µ/μ 变体）、全角波浪号。"""
    return (str(s).replace("Ω", "Ohm").replace("Ω", "Ohm")
            .replace("μ", "u").replace("µ", "u")
            .replace("～", "~").replace("−", "-").strip())


def _parse_unit(tok):
    """单位 token -> (规范单位, 数量级因子)；无法识别时原样返回、因子 1。"""
    t = tok.strip()
    if not t:
        return ("", 1.0)
    if t.startswith("ppm"):
        return ("ppm", 1.0)
    if t in ("℃", "C", "°C"):
        return ("℃", 1.0)
    if t == "%":
        return ("%", 1.0)
    t = t.split("/")[0]          # 复合后缀 "V/us" / "ppm/℃" 取主单位
    if t in _BASE:
        return (_BASE[t], 1.0)
    for pre, factor in _PREFIX:
        if t.startswith(pre) and len(t) > len(pre):
            b = _BASE.get(t[len(pre):])
            if b:
                return (b, factor)
    return (t, 1.0)


class Quantity:
    """一个带单位的量值。``lo``/``hi`` 以基本 SI 单位表示；单值时两者相等。

    区间语义（如 TVS "击穿电压:6.4V~7.0V" 是规格带）——``.min`` 是保守下界，
    判"钳位是否吃掉输出"时应取 :attr:`min`。
    """

    __slots__ = ("lo", "hi", "unit", "raw", "qualifier", "is_tolerance")

    def __init__(self, lo, hi, unit, raw, qualifier="", is_tolerance=False):
        self.lo = lo
        self.hi = hi
        self.unit = unit
        self.raw = raw
        self.qualifier = qualifier
        self.is_tolerance = is_tolerance

    @property
    def min(self):
        return self.lo

    @property
    def max(self):
        return self.hi

    @property
    def typ(self):
        return self.lo if self.lo == self.hi else (self.lo + self.hi) / 2.0

    @property
    def is_range(self):
        return self.lo != self.hi

    def __repr__(self):
        if self.is_range:
            body = f"{self.lo:g}~{self.hi:g}"
        else:
            body = f"{self.lo:g}"
        q = f" {self.qualifier}" if self.qualifier else ""
        return f"<{body}{self.unit or ''}{q}>"

    def __eq__(self, other):
        return (isinstance(other, Quantity) and self.lo == other.lo
                and self.hi == other.hi and self.unit == other.unit)


def parse_quantity(text):
    """把 "7V" / "6.4V~7.0V" / "600mV@1A" / "±5%" 解析为 Quantity。

    无值占位（'-' 等）与不可解析输入返回 ``None``（调用方需处理缺失，
    不要静默当 0 —— 0 是有意义的电气量）。
    """
    if text is None:
        return None
    raw = str(text).strip()
    if raw in _NULLISH:
        return None
    s = _norm_text(raw)

    qualifier = ""
    if "@" in s:
        s, q = s.split("@", 1)
        qualifier = "@" + q.strip()
        s = s.strip()

    is_tol = False
    if s.startswith("+/-"):
        is_tol = True
        s = s[3:].strip()
    elif s.startswith("±"):
        is_tol = True
        s = s[1:].strip()

    segs = [x.strip() for x in s.split("~") if x.strip()]
    vals = []
    unit = ""
    for seg in segs:
        m = _NUM_RE.search(seg)
        if not m:
            continue
        try:
            num = float(m.group(0))
        except ValueError:
            continue
        tail = _TAIL_RE.match(seg[m.end():])
        tok = tail.group(0).strip() if tail else ""
        u, factor = _parse_unit(tok)
        if u:
            unit = unit or u
        vals.append(num * factor)
    if not vals:
        return None
    vals.sort()
    return Quantity(_sig(vals[0]), _sig(vals[-1]), unit, raw, qualifier,
                    is_tol)


# ---------------------------------------------------------------- 规范键表

# 规范键 -> 已知原始键名别名（取自 probes/attr_survey.py 全量普查，
# 5 工程 174 键中出现过的才登记）。
KEY_ALIASES = {
    # --- 钳位件 / 保护件 ---
    "VBR": ["击穿电压", "击穿电压(VBR)", "击穿电压(Vbr)"],
    "VRWM": ["反向截止电压(Vrwm)", "反向工作电压", "反向工作电压(Vrwm)",
             "反向截止电压"],
    "VCLAMP": ["钳位电压", "最大钳位电压", "钳位电压(Vc)", "最大箝位电压"],
    "POLARITY": ["极性", "二极管配置"],
    "VF": ["正向压降(Vf)", "正向压降", "正向电压(Vf)", "正向导通压降(VF)"],
    "IPP": ["峰值脉冲电流(Ipp)", "峰值脉冲电流(Ipp)@10/1000us",
            "峰值脉冲电流"],
    "PPP": ["峰值脉冲功率(Ppp)", "峰值脉冲功率(Ppp)@10/1000us",
            "峰值脉冲功率"],
    "VR": ["直流反向耐压(Vr)", "直流反向耐压"],

    # --- 串联件能力 ---
    "IHOLD": ["保持电流", "保持电流(Ihold)", "保持电流(Ih)"],
    "ITRIP": ["跳闸电流", "跳闸电流(It)"],
    "ISAT": ["饱和电流(Isat)", "饱和电流", "额定电流(Isat)"],
    "DCR": ["直流电阻(DCR)", "直流电阻"],
    "RON": ["导通电阻(Ron@VCC)", "导通电阻", "导通电阻(RDS(on)@Vgs,Id)",
            "导通电阻(RDS(on))"],
    "I_RATED": ["额定电流", "额定电流(DC)", "触点电流"],
    "V_RATED": ["额定电压", "额定电压(DC)", "最大电压"],

    # --- 无源件 ---
    "RESISTANCE": ["阻值"],
    "CAPACITANCE": ["容值"],
    "INDUCTANCE": ["电感值"],
    "POWER": ["功率", "额定功率"],
    "TOLERANCE": ["精度", "误差", "容差"],
    "TEMPCO": ["温度系数", "材质(温度系数)"],
    "IMPEDANCE": ["阻抗@频率", "阻抗"],

    # --- 有源件 / 供电 ---
    "V_SUPPLY": ["工作电压", "最大工作电压", "电源电压", "供电电压",
                 "供电电压范围"],
    "I_OUT": ["输出电流", "连续漏极电流(Id)", "整流电流"],
    "GBW": ["增益带宽积(GBW)", "增益带宽积(GBP)", "增益带宽积"],
    "SR": ["压摆率(SR)", "压摆率"],
    "VOS": ["输入失调电压(Vos)", "输入失调电压"],
    "IB": ["输入偏置电流(Ib)", "输入偏置电流"],
    "RAIL2RAIL": ["轨到轨"],
    "VOUT": ["输出电压"],
}

# 反查索引（原始键名 -> 规范键）
_CANONICAL_OF = {}
for _canon, _aliases in KEY_ALIASES.items():
    for _a in _aliases:
        _CANONICAL_OF[_a] = _canon
    _CANONICAL_OF.setdefault(_canon, _canon)

_TAIL_PAREN_RE = re.compile(r"[(（][^)）]*[)）]\s*$")


def canonical_key(raw_key):
    """原始属性键 -> 规范键；未登记的原样返回（保留信息，不丢弃）。"""
    k = str(raw_key).strip()
    if not k:
        return ""
    if k in _CANONICAL_OF:
        return _CANONICAL_OF[k]
    # 去掉结尾括号限定（"峰值脉冲电流(Ipp)@10/1000us" 已显式登记，
    # 这里兜底 "XX(YY)" -> "XX"）
    k2 = _TAIL_PAREN_RE.sub("", k).strip()
    if k2 in _CANONICAL_OF:
        return _CANONICAL_OF[k2]
    return k


def split_attr_string(desc):
    """描述串 -> [(原始键, 原始值)]；非 "k:v;..." 形态返回 []。

    EDA 有**两种**描述形态（实测）：
      格式2（器件属性表）: "击穿电压:7V;钳位电压:12V;"
      格式1（简洁值）:     "10KΩ (1002) ±1%" —— 无键名，本函数不处理，
                          由 lceda_reader.parse_value 的老路径负责。
    """
    if not desc or ";" not in desc or ":" not in desc:
        return []
    out = []
    for kv in str(desc).split(";"):
        kv = kv.strip()
        if ":" not in kv:
            continue
        k, v = kv.split(":", 1)
        k, v = k.strip(), v.strip()
        if k:
            out.append((k, v))
    return out


class Attrs:
    """器件属性的结构化视图。

    用法::

        a = Attrs(desc)
        q = a.qty("VBR")        # Quantity | None
        v = a.raw_text("VBR")   # 原始串 "6.4V~7.0V"
        pol = a.get("POLARITY") # "双向"
    """

    __slots__ = ("_by_canon", "_by_raw", "_items")

    def __init__(self, desc):
        self._by_canon = {}
        self._by_raw = {}
        self._items = []
        for raw_k, raw_v in split_attr_string(desc):
            self._by_raw[raw_k] = raw_v
            self._items.append((raw_k, raw_v))
            ck = canonical_key(raw_k)
            if ck and ck not in self._by_canon:
                self._by_canon[ck] = raw_v

    def get(self, canon, default=None):
        """规范键的原始字符串值。"""
        return self._by_canon.get(canon, default)

    def raw_text(self, canon):
        return self._by_canon.get(canon)

    def qty(self, canon):
        """规范键的 Quantity（不可解析/缺失返回 None）。"""
        v = self._by_canon.get(canon)
        return parse_quantity(v) if v is not None else None

    def has(self, canon):
        return canon in self._by_canon

    def raw_keys(self):
        return [k for k, _ in self._items]

    def __contains__(self, canon):
        return canon in self._by_canon

    def __repr__(self):
        return f"<Attrs {len(self._by_canon)} canonical / {len(self._items)} raw>"


# ---------------------------------------------------------------- 语义辅助

# 双向 TVS 实际钳位比标称 VBR 高约 V_F（两只齐纳反串联：一只正偏 + 一只击穿）。
# 依据：V2 信号板模拟输出削顶实测——标称 VBR 6.6V(typ) 实测钳位 7.28~7.48V，
# 仿真取 BV+V_F 后与实测吻合（docs/电气规则层建议-2026-09-15.md §7）。
BIDIR_TVS_VF = 0.7


def is_bidirectional(polarity_text):
    """极性文本是否为双向（"双向"/"Bidirectional"/"Bi-dir"）。"""
    t = str(polarity_text or "").lower()
    return "双" in t or "bi" in t and "dir" in t


def clamp_onset(q_vbr, polarity=None, vf=BIDIR_TVS_VF):
    """钳位件的**实际起始电平**（保守取 VBR 下界）。

    - 双向 TVS：``VBR + V_F``（反串联结构，见 :data:`BIDIR_TVS_VF`）
    - 单向 / 极性未知：``VBR`` 本身

    返回 Quantity（单位继承 VBR）。``q_vbr`` 为 None 时返回 None。
    """
    if q_vbr is None:
        return None
    offset = vf if is_bidirectional(polarity) else 0.0
    return Quantity(_sig(q_vbr.min + offset), _sig(q_vbr.max + offset),
                    q_vbr.unit, q_vbr.raw,
                    qualifier=q_vbr.qualifier,
                    is_tolerance=q_vbr.is_tolerance)
