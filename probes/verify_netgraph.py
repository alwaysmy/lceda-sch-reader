"""lceda_netgraph.py 验证：用 V2 信号板对照分析文档的已知答案。

对照基准（E_distance 2_mcu_fw/dis_fw_v2_uart4test/5_docs/
模拟输出削顶机理分析_2026-09-15.md §2）：
  - 端子 DSUB4.2 (net U_TEMP_SENSOR)：上游 F1(PTC) → D8(TVS VBR=7V)
    → 驱动级 U16(OPA171)，增益 Rf/Rin=24k/5.6k=4.286，参考 1.96V
    → Vin=0 输出 10.36V
  - 距离通道 U19：T 型网络，增益 4.364

用法: python probes/verify_netgraph.py
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

V2 = r"D:/WorkDesigns/2_WorkProjects/E_distance/1_sch/V2版/信号板/信号板.eprj2"

FAIL = []


def check(name, got, want, tol=0.02):
    if isinstance(want, float) and isinstance(got, (int, float)):
        ok = abs(got - want) <= tol * max(1.0, abs(want))
    else:
        ok = got == want
    if not ok:
        FAIL.append((name, got, want))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}" +
          ("" if ok else f"  (期望 {want!r})"))


def open_db(path):
    db = LR.detect_backend(path)
    if db == "DECRYPT_NEW":
        return LR.Epro2DB(LR._decrypt_new_eprj2(path))
    return db(path) if isinstance(db, type) else db


def main():
    if not os.path.isfile(V2):
        print(f"样本缺失，跳过: {V2}")
        return
    db = open_db(V2)
    print("=== 构建净图（DA输出调理 + 模拟输出 两页）===")
    g = NG.NetGraph.build(db, LR, pages={"DA输出调理", "模拟输出"})
    print(f"  元件 {len(g.parts)}  网络 {len(g.net_pins)}")

    # ---- 1. 分类抽查 ----
    print("\n=== 元件分类（对照实测）===")
    check("U16 运放", g.part("U16").role, NG.R_DRIVER)
    check("U19 运放", g.part("U19").role, NG.R_DRIVER)
    check("U15 模拟开关", g.part("U15").role, NG.R_SWITCH)
    check("D8 钳位件(TVS)", g.part("D8").role, NG.R_CLAMP)
    check("D7 钳位件(TVS)", g.part("D7").role, NG.R_CLAMP)
    check("F1 PTC 串联件", g.part("F1").role, NG.R_SERIES)
    check("L3 磁珠 串联件", g.part("L3").role, NG.R_SERIES)
    check("R63 电阻 串联件", g.part("R63").role, NG.R_SERIES)
    check("DSUB4 连接器", g.part("DSUB4").role, NG.R_CONNECTOR)

    # ---- 2. 受引导遍历：不穿电源网 ----
    print("\n=== 受引导遍历（从端子网络 U_TEMP_SENSOR）===")
    hops = g.walk("U_TEMP_SENSOR", max_hops=8)
    names = [g.net_name.get(k, "") for k in hops]
    print(f"  可达 {len(hops)} 个网络节点: "
          f"{[(g.net_name.get(k) or k) for k in hops]}")
    power_leaked = [n for n in names if n and LR.is_power_net(n)]
    check("遍历未穿入电源/地网", power_leaked, [])

    # ---- 3. 钳位件检索（应 1 跳命中 D8）----
    print("\n=== 钳位件检索 ===")
    clamps = g.find_clamps("U_TEMP_SENSOR", max_hops=8)
    cdes = sorted({c["des"] for c in clamps})
    print(f"  命中: {[(c['des'], c['hops'], c['net']) for c in clamps]}")
    check("含 D8", "D8" in cdes, True)
    d8 = next((c for c in clamps if c["des"] == "D8"), None)
    if d8:
        check("D8 跳数=1（PTC 板内侧）", d8["hops"], 1)
        vbr = d8["part"].attrs.qty("VBR")
        pol = d8["part"].attrs.get("POLARITY")
        from lceda_attrs import clamp_onset
        onset = clamp_onset(vbr, pol)
        print(f"     D8 VBR={vbr} 极性={pol} → 钳位起始={onset}")
        # 工程文件里 D8 属性是**典型单值** 击穿电压:7V（无 6.4~7.0 规格带）；
        # 双向 TVS +0.7V → 7.7V，与文档仿真 BV=7.0V→7.764V 吻合。
        # （文档 §2 的 7.1V 是用规格带下界 6.4V 算的，属人工补充知识，
        #   不在工程数据内——数据边界见 docs/电气规则层-实现说明.md）
        check("D8 钳位起始 7.7V（单值+双向修正）", round(onset.lo, 2), 7.7)

    # ---- 4. 驱动级检索 ----
    print("\n=== 驱动级检索 ===")
    drv = g.find_drivers("U_TEMP_SENSOR", max_hops=8)
    ddes = [d["des"] for d in drv]
    print(f"  命中: {[(d['des'], d['hops'], d['out_net']) for d in drv]}")
    check("含 U16", "U16" in ddes, True)

    # ---- 5. 传递函数（对照文档手算）----
    print("\n=== 驱动级传递函数（对照文档手算）===")
    # U16/U18：两电阻反相级，须精确；U19：T 型网络，必须**降级**而非给错值
    for des, want_gain, want_off in (("U16", 4.286, 10.36),
                                     ("U18", 4.286, 10.36)):
        tr = g.driver_transfer(des)
        print(f"  {des}: gain={tr['gain']} offset={tr['offset']} "
              f"conf={tr['confidence']} rf={tr['rf']} rin={tr['rin']}")
        check(f"{des} 增益", tr["gain"], want_gain, tol=0.02)
        check(f"{des} Vin=0 输出", tr["offset"], want_off, tol=0.02)
        check(f"{des} 置信度 high", tr["confidence"], "high")

    tr19 = g.driver_transfer("U19")
    print(f"  U19(T型): gain={tr19['gain']} conf={tr19['confidence']} "
          f"notes={tr19['notes']}")
    # 关键：T 型网络**必须降级**——绝不能给出高置信的错误增益
    # （曾出现 gain=7.27 的错误 high 结果，比返回 None 更危险）
    check("U19 T型网络降级为 low", tr19["confidence"], "low")
    check("U19 不给错误增益", tr19["gain"], None)

    # ---- 6. 端到端：驱动上界 vs 钳位起始 ----
    print("\n=== 端到端：U16 输出上界 vs D8 钳位起始 ===")
    top, note = g.driver_envelope("U16")
    print(f"  输出上界 {top}  ({note})")
    check("U16 输出上界 10.36V", round(top, 2), 10.36, tol=0.02)
    if top and onset:
        margin = onset.min - top
        conflict = margin < 0.5
        print(f"  钳位余量 = {onset.min:.2f} - {top:.2f} = {margin:.2f}V "
              f"→ {'⚠ 冲突（钳位吃掉输出）' if conflict else 'OK'}")
        check("U16 判定为钳位冲突", conflict, True)

    print()
    if FAIL:
        print(f"ALL: FAIL ({len(FAIL)})")
        for n, gp, w in FAIL:
            print(f"   {n}: got={gp!r} want={w!r}")
        sys.exit(1)
    print("ALL: PASS")


if __name__ == "__main__":
    main()
