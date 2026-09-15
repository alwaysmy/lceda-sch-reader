"""三层架构验证：块识别 + 网表导出 + 公式。

覆盖：
  1. V2 信号板真实工程：U16/U18 认反相、U19 认不出→降级（不给错值）
  2. 网表导出：U19 的复合反馈网络必须完整出现在网表里（第2层兜底）
  3. 公式：反相级增益/偏置与人工手算一致；SK 低通 fc/Q 对标准值
  4. 合成 SK/MFB 样本：构造图直接喂识别器（真实工程缺这类样本）

用法: python probes/verify_layers.py
"""
import io
import os
import sys

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import lceda_reader as LR
import lceda_netgraph as NG
import lceda_blocks as BL
import lceda_spice as SP

V2 = r"D:/WorkDesigns/2_WorkProjects/E_distance/1_sch/V2版/信号板/信号板.eprj2"
FAIL = []


def check(name, got, want, tol=0.01):
    if isinstance(want, float) and isinstance(got, (int, float)):
        ok = abs(got - want) <= tol * max(1.0, abs(want))
    else:
        ok = got == want
    if not ok:
        FAIL.append((name, got, want))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}" +
          ("" if ok else f"  (期望 {want!r})"))


def open_db(p):
    db = LR.detect_backend(p)
    if db == "DECRYPT_NEW":
        return LR.Epro2DB(LR._decrypt_new_eprj2(p))
    return db(p) if isinstance(db, type) else db


# ---------------------------------------------------------------- 合成样本

class FakePart:
    def __init__(self, des, title, desc, pins, role, page="P1"):
        self.des = des
        self.title = title
        self.attrs = __import__("lceda_attrs").Attrs(desc)
        self.pin_names = [p[0] for p in pins]
        self.pins = pins
        self.role = role
        self.page = page
        self.role_reason = "synthetic"

    @property
    def is_two_pin(self):
        return len(self.pins) <= 2


class FakeGraph:
    """最小净图：直接给 net_pins / pin_net / parts，供识别器消费。"""

    def __init__(self, parts, net_pins, pin_net, net_name=None):
        self.parts = {p.des.upper(): p for p in parts}
        self.net_pins = net_pins
        self.pin_net = pin_net
        self.net_name = net_name or {}
        self.dom = {}
        self.group_name = {}
        self._lr = LR
        # channel_pins 依赖 lceda_netgraph 实现，这里复用
        self._ng = NG.NetGraph()
        self._ng.parts = self.parts
        self._ng.pin_net = pin_net
        self._ng.net_pins = net_pins
        self._ng.net_name = self.net_name
        self._ng._lr = LR

    def part(self, d):
        return self.parts.get(str(d).upper())

    def channel_pins(self, d):
        return self._ng.channel_pins(d)

    def other_pins(self, d, pk):
        return self._ng.other_pins(d, pk)

    def walk(self, *a, **k):
        return self._ng.walk(*a, **k)

    def pin_named(self, d, *names):
        return self._ng.pin_named(d, *names)


def synth_sk_lowpass():
    """合成 Sallen-Key 低通（单位增益，标准教科书拓扑）：
        VIN ─R1─ MID ─R2─ NINP(=IN+) ─┬─ C2 ─ GND
                     └─ C1 ── OUT ────┘（C1 从 MID 到 OUT 为 SK 抽头）
    取 R1=R2=10k, C1=C2=10n：
        fc = 1/(2π√(R1R2C1C2)) = 1/(2π·1e-5) ≈ 1591.55 Hz
        Q  = √(R1R2C1C2)/(C2(R1+R2)) = 1e-5/(1e-8·2e4) = 0.5
    """
    U1 = FakePart("U1", "OPAxxx", "放大器数:单路;",
                  [("IN+", "1", "IN+"), ("IN-", "2", "IN-"),
                   ("OUT", "3", "OUT"), ("V+", "4", "V+"),
                   ("V-", "5", "V-")], BL.R_DRIVER)
    R1 = FakePart("R1", "R10k", "阻值:10kΩ;", [("1", "1", "1"), ("2", "2", "2")], BL.R_SERIES)
    R2 = FakePart("R2", "R10k", "阻值:10kΩ;", [("1", "1", "1"), ("2", "2", "2")], BL.R_SERIES)
    C1 = FakePart("C1", "C10n", "容值:10nF;", [("1", "1", "1"), ("2", "2", "2")], BL.R_PASSIVE)
    C2 = FakePart("C2", "C10n", "容值:10nF;", [("1", "1", "1"), ("2", "2", "2")], BL.R_PASSIVE)
    pin_net = {
        ("U1", "IN+"): "NINP", ("U1", "IN-"): "NOUT", ("U1", "OUT"): "NOUT",
        ("U1", "V+"): "+5V", ("U1", "V-"): "GND",
        ("R1", "1"): "VIN", ("R1", "2"): "MID",
        ("R2", "1"): "MID", ("R2", "2"): "NINP",
        ("C1", "1"): "MID", ("C1", "2"): "NOUT",
        ("C2", "1"): "NINP", ("C2", "2"): "GND",
    }
    net_pins = {}
    for (d, pk), n in pin_net.items():
        net_pins.setdefault(n, set()).add((d, pk))
    return FakeGraph([U1, R1, R2, C1, C2], net_pins, pin_net,
                     {"NOUT": "", "NINP": "", "MID": "", "VIN": "",
                      "+5V": "+5V", "GND": "GND"})


def main():
    # ---- 1. V2 真实工程：识别 ----
    if os.path.isfile(V2):
        db = open_db(V2)
        g = NG.NetGraph.build(db, LR, pages={"DA输出调理", "模拟输出"})
        print("=== V2 真实工程：块识别 ===")
        blks = {b.anchor: b for b in BL.recognize_all(g)}
        check("U16=反相级", blks.get("U16").kind, BL.K_INVERTING)
        check("U18=反相级", blks.get("U18").kind, BL.K_INVERTING)
        check("U19 不误判为反相级（T型/多支路）",
              blks.get("U19").kind != BL.K_INVERTING, True)
        check("U19 降级（conf≠high 或非公式种类）",
              blks.get("U19").confidence != "high"
              or not blks.get("U19").can_compute(), True)

        print("\n=== V2：第3层公式（对照人工手算）===")
        t16 = g.driver_transfer("U16")
        check("U16 增益", t16["gain"], 4.2857, tol=0.01)
        check("U16 offset", t16["offset"], 10.36, tol=0.01)
        check("U16 置信 high", t16["confidence"], "high")
        t19 = g.driver_transfer("U19")
        check("U19 不给错误增益（宁可不报）", t19["gain"], None)

        print("\n=== V2：第2层网表导出（U19 复合网络必须完整）===")
        net = SP.emit_for_block(g, blks["U19"], "U19")
        for comp in ("RR73", "RR74", "RR75", "RR76", "CC98", "CC100", "CC101"):
            check(f"网表含 {comp}", comp + " " in net or f"{comp} " in net, True)
        check("网表含运放子电路", ".subckt OPAMP" in net, True)
        check("网表含 XU19", "XU19 " in net, True)
        check("双向 TVS 用反串联子电路", "TVS_BI" in net, True)
    else:
        print("V2 样本缺失，跳过真实工程项")

    # ---- 2. 合成 SK 低通 ----
    print("\n=== 合成 Sallen-Key 低通（真实工程缺此类样本）===")
    gsk = synth_sk_lowpass()
    blk = BL.recognize(gsk, "U1")
    print(f"  识别: kind={blk.kind} conf={blk.confidence} "
          f"members={sorted(blk.members)}")
    for e in blk.evidence:
        print(f"    {e}")
    check("识别为 SK 低通", blk.kind, BL.K_SK_LP)
    vals = BL.evaluate(blk)
    print(f"  公式: {vals}")
    # fc = 1/(2π√(R1R2C1C2)) = 1/(2π·1e-5) ≈ 1591.55 Hz
    check("fc ≈ 1591.5 Hz", vals.get("fc_hz"), 1591.55, tol=0.01)
    check("Q = 0.5", vals.get("q"), 0.5, tol=0.02)

    # ---- 3. 网表：合成 SK ----
    print("\n=== 合成 SK：网表导出 ===")
    nsk = SP.emit_for_block(gsk, blk, "SK")
    check("含 R1/R2", ("RR1 " in nsk and "RR2 " in nsk), True)
    check("含 C1/C2", ("CC1 " in nsk and "CC2 " in nsk), True)

    print()
    if FAIL:
        print(f"ALL: FAIL ({len(FAIL)})")
        for n, gp, w in FAIL:
            print(f"   {n}: got={gp!r} want={w!r}")
        sys.exit(1)
    print("ALL: PASS")


if __name__ == "__main__":
    main()
