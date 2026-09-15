"""lceda_rules.py 验证：V2 信号板端到端 + 负向（无误报）。

对照基准 = 实测故障（docs/电气规则层建议-2026-09-15.md）：
  U16/U18 通道设计 10.36V，被 5V 档 TVS 钳在 ~7.3V（实测 7.28/7.48V）。

用法: python probes/verify_rules.py
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
import lceda_rules as R

V2 = r"D:/WorkDesigns/2_WorkProjects/E_distance/1_sch/V2版/信号板/信号板.eprj2"
FAIL = []


def check(name, got, want):
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


def main():
    if not os.path.isfile(V2):
        print(f"样本缺失，跳过: {V2}")
        return
    db = open_db(V2)
    lr = LR
    g = NG.NetGraph.build(db, lr, pages={"DA输出调理", "模拟输出"})
    cfg = R.load_config()
    findings = R.run_rules(g, cfg, lr)

    print("=== R1 钳位冲突（对照实测故障）===")
    r1 = [f for f in findings if f.rule == "R1" and f.severity == "error"]
    subj = sorted(f.subject for f in r1)
    check("U16 报 ERROR", "U16" in subj, True)
    check("U18 报 ERROR", "U18" in subj, True)
    # 实测值 7.28/7.48V；规则给 7.70V（典型 VBR 7V + 双向 0.7V）——
    # 量级一致（都在 7.x），这正是"评审阶段拦下"所需
    u16 = next(f for f in r1 if f.subject == "U16")
    check("U16 钳位起始 7.7V", u16.evidence["clamp_onset_v"], 7.7)
    check("U16 驱动上限 10.36V", u16.evidence["driver_top_v"], 10.36)
    check("U16 所报钳位件是 D8(5V档)", u16.evidence["clamp"], "D8")

    print("\n=== U19（T 型网络）不应误报 ERROR ===")
    u19 = [f for f in findings if f.subject == "U19" and f.rule == "R1"]
    sevs = [f.severity for f in u19]
    check("U19 无 ERROR（不可算时降级 INFO）", "error" in sevs, False)
    check("U19 有 INFO 提示人工确认", "info" in sevs, True)

    print("\n=== R4 反相语义提示 ===")
    r4 = sorted(f.subject for f in findings if f.rule == "R4")
    check("U16/U18 提示反相", ("U16" in r4 and "U18" in r4), True)
    check("U19 不乱报（不可算不提示极性）", "U19" in r4, False)

    print("\n=== R3 电源轨（INFO，需人工确认）===")
    r3 = sorted(f.subject for f in findings if f.rule == "R3")
    print(f"  报告的无源轨: {r3}")
    check("报出板外供电轨(+13.6V)", "+13.6V" in r3, True)
    check("GND 不报（地无需源）",
          any("GND" in s.upper() for s in r3), False)

    print("\n=== 端子电气包络表 ===")
    table = R.terminal_table(g, cfg, lr)
    t16 = next((r for r in table if r["driver"] == "U16"), None)
    check("表含 U16", t16 is not None, True)
    if t16:
        check("U16 表内余量 -2.66V", t16["margin_v"], -2.66)
        check("U16 表内钳位件 D8", t16["clamp"], "D8")

    print("\n=== 配置驱动启停 ===")
    cfg2 = R.load_config()
    cfg2["rules"]["R1"]["enabled"] = False
    only_r4 = [f for f in R.run_rules(g, cfg2, lr) if f.rule == "R1"]
    check("R1 关闭后不再产出", len(only_r4), 0)

    print("\n=== 无误报：干净工程不应出 ERROR ===")
    clean = os.path.join(ROOT, "..", "examples", "涡流传感器.eprj2")
    if os.path.isfile(clean):
        db2 = open_db(clean)
        g2 = NG.NetGraph.build(db2, lr)
        f2 = R.run_rules(g2, cfg, lr)
        err2 = [f for f in f2 if f.severity == "error"]
        print(f"  涡流工程: {len(f2)} 条发现，其中 ERROR {len(err2)}")
        for f in err2[:5]:
            print(f"    {f}")
        # 信息级可以，但不应有 ERROR（该工程无此缺陷）
        check("涡流工程无 ERROR", len(err2), 0)

    print()
    if FAIL:
        print(f"ALL: FAIL ({len(FAIL)})")
        for n, gp, w in FAIL:
            print(f"   {n}: got={gp!r} want={w!r}")
        sys.exit(1)
    print("ALL: PASS")


if __name__ == "__main__":
    main()
