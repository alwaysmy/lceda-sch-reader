"""lceda_attrs.py 验证：真实串单元 + 全库归一率。

用法: python probes/verify_attrs.py
"""
import io
import os
import sys

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import lceda_reader as R
from lceda_attrs import (Attrs, parse_quantity, canonical_key, clamp_onset,
                         is_bidirectional)

FAIL = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAIL.append((name, got, want))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}" + ("" if ok else f" != {want!r}"))


def unit(q):
    return None if q is None else q.unit


def main():
    # ---- 1. 真实串单元测试（全部取自实测属性串）----
    print("=== 量值解析（真实串）===")
    cases = [
        ("7V", 7.0, 7.0, "V"),
        ("6.4V~7.0V", 6.4, 7.0, "V"),          # TVS 规格带
        ("5V", 5.0, 5.0, "V"),
        ("600mV@1A", 0.6, 0.6, "V"),           # 带 @ 限定
        ("8.2A@10/1000us", 8.2, 8.2, "A"),
        ("5.5A@(8/20us)", 5.5, 5.5, "A"),
        ("5Ω@10V", 5.0, 5.0, "Ω"),
        ("3.2Ω", 3.2, 3.2, "Ω"),
        ("10kΩ", 10000.0, 10000.0, "Ω"),
        ("300mΩ", 0.3, 0.3, "Ω"),
        ("12pF", 12e-12, 12e-12, "F"),
        ("4.7uF", 4.7e-6, 4.7e-6, "F"),
        ("220nH", 220e-9, 220e-9, "H"),
        ("200mA", 0.2, 0.2, "A"),
        ("100A", 100.0, 100.0, "A"),
        ("24V", 24.0, 24.0, "V"),
        ("250uV", 250e-6, 250e-6, "V"),
        ("3MHz", 3e6, 3e6, "Hz"),
        ("-40℃~+85℃", -40.0, 85.0, "℃"),
        ("±5%", 5.0, 5.0, "%"),
    ]
    for s, lo, hi, u in cases:
        q = parse_quantity(s)
        check(s, (q.lo, q.hi, q.unit) if q else None, (lo, hi, u))

    # 无值占位 —— 必须 None（不能当 0）
    for s in ("-", "—", "", None, "N/A"):
        check(f"nullish {s!r}", parse_quantity(s), None)

    # ---- 2. 规范键归一 ----
    print("\n=== 键名归一 ===")
    for raw, want in [
        ("击穿电压", "VBR"),
        ("击穿电压(VBR)", "VBR"),
        ("反向截止电压(Vrwm)", "VRWM"),
        ("钳位电压", "VCLAMP"),
        ("最大钳位电压", "VCLAMP"),
        ("保持电流", "IHOLD"),                 # PTC 实测键
        ("饱和电流(Isat)", "ISAT"),
        ("直流电阻(DCR)", "DCR"),
        ("导通电阻(Ron@VCC)", "RON"),
        ("增益带宽积(GBW)", "GBW"),
        ("增益带宽积(GBP)", "GBW"),            # 姊妹写法
        ("阻值", "RESISTANCE"),
        ("未登记的自定义键", "未登记的自定义键"),   # 不丢弃
    ]:
        check(raw, canonical_key(raw), want)

    # ---- 3. 双向 TVS 钳位修正（V2 削顶实测资产）----
    print("\n=== 双向 TVS 钳位起始 ===")
    vbr = parse_quantity("7V")
    check("is_bidirectional 双向", is_bidirectional("双向"), True)
    check("is_bidirectional 单向", is_bidirectional("单向"), False)
    bi = clamp_onset(vbr, "双向")
    check("双向 7V -> 7.7V", (bi.lo, bi.unit), (7.7, "V"))
    uni = clamp_onset(vbr, "单向")
    check("单向 7V -> 7.0V", (uni.lo, uni.unit), (7.0, "V"))
    band = clamp_onset(parse_quantity("6.4V~7.0V"), "双向")
    check("双向 6.4~7.0 -> 7.1~7.7", (band.lo, band.hi), (7.1, 7.7))

    # ---- 4. Attrs 视图 ----
    print("\n=== Attrs 视图 ===")
    a = Attrs("极性:双向;反向截止电压(Vrwm):5V;击穿电压:7V;钳位电压:12V;")
    check("get POLARITY", a.get("POLARITY"), "双向")
    check("qty VBR", a.qty("VBR").lo, 7.0)
    check("qty VRWM", a.qty("VRWM").lo, 5.0)
    check("has VBR", a.has("VBR"), True)
    check("has 不存在", a.has("ISAT"), False)
    check("qty 缺失 -> None", a.qty("ISAT"), None)

    # ---- 5. 全库归一率（真实工程）----
    print("\n=== 全库归一率（真实工程）===")
    files = [
        os.path.join(ROOT, "..", "examples", "涡流传感器.eprj2"),
        os.path.join(ROOT, "..", "examples", "Piezo_Driver.eprj2"),
        os.path.join(ROOT, "..", "examples", "MCU主控-V1.1-2026.05.06.eprj2"),
        r"D:/WorkDesigns/2_WorkProjects/E_distance/1_sch/V2版/信号板/信号板.eprj2",
    ]
    tot_keys = tot_canon = tot_qty = 0
    for f in files:
        if not os.path.isfile(f):
            continue
        try:
            db = R.detect_backend(f)
            if db == "DECRYPT_NEW":
                db = R.Epro2DB(R._decrypt_new_eprj2(f))
            elif isinstance(db, type):
                db = db(f)
            dmap = db.device_map()
        except Exception as e:
            print(f"  [skip] {os.path.basename(f)}: {type(e).__name__}")
            continue
        nk = nc = nq = 0
        for _u, (_t, _d, desc) in dmap.items():
            if not desc:
                continue
            a = Attrs(desc)
            nk += len(a.raw_keys())
            nc += len(a._by_canon)
            for k in a._by_canon:
                if a.qty(k) is not None:
                    nq += 1
        print(f"  {os.path.basename(f):42s} 原始键 {nk:5d}  归一 {nc:5d}  可量化 {nq:5d}")
        tot_keys += nk
        tot_canon += nc
        tot_qty += nq
    print(f"  合计: 原始 {tot_keys}  归一 {tot_canon}  可量化 {tot_qty}")
    if tot_keys:
        print(f"  归一率(键)  {tot_canon / tot_keys:.1%}")
        print(f"  可量化率(值) {tot_qty / max(1, tot_keys):.1%}")

    # ---- 6. 端到端：V2 信号板三颗 TVS ----
    print("\n=== 端到端：V2 信号板 TVS（R1 的输入）===")
    f = files[-1]
    if os.path.isfile(f):
        db = R.detect_backend(f)
        if isinstance(db, type):
            db = db(f)
        dmap = db.device_map()
        for u, (t, d, desc) in dmap.items():
            if "SMAJ5.0CA" in (d or "") or "ESD8U5.0C" in (d or ""):
                a = Attrs(desc)
                pol = a.get("POLARITY")
                vbr = a.qty("VBR")
                onset = clamp_onset(vbr, pol)
                print(f"  {d:16s} 极性={pol} VBR={a.raw_text('VBR')} "
                      f"-> 钳位起始={onset}")
                break

    print()
    if FAIL:
        print(f"ALL: FAIL ({len(FAIL)} 项)")
        for n, g, w in FAIL:
            print(f"   {n}: got={g!r} want={w!r}")
        sys.exit(1)
    print("ALL: PASS")


if __name__ == "__main__":
    main()
