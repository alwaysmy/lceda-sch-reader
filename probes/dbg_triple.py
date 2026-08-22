"""三重核对：
① .eprj2 中 CBB 展开用的是模板位号还是母图位号
② .epro2 导出中 CBB 展开的位号是否保持母图位号
③ CBB 实例编号（CBB6/CBB7 等）在工具输出中是否正确
④ ControlDAC_A 页有几个 CBB 实例
⑤ epro2 中 CBB 内器件的阻值信息
"""
import io, sys, json, subprocess, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
R = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py"
EPRJ = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-22.epro2"
EPRJ_OLD = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"

# ═══════════════════════════════════════════
print("=" * 70)
print("① .epro2 (官方导出) 中 ControlDAC_A 的 CBB 展开——位号来源")
print("=" * 70)

p = subprocess.run([sys.executable, R, "--eprj", EPRJ, "--json", "netlist"],
                   capture_output=True, text=True, encoding="utf-8")
rows = json.loads(p.stdout)

cbb6_members = set()
cbb7_members = set()
for r in rows:
    for c in r["components"]:
        if c.startswith("CBB6."):
            cbb6_members.add(c.split(".", 1)[1])
        elif c.startswith("CBB7."):
            cbb7_members.add(c.split(".", 1)[1])

print(f"\nCBB6 展开成员 ({len(cbb6_members)}): {sorted(cbb6_members)}")
print(f"CBB7 展开成员 ({len(cbb7_members)}): {sorted(cbb7_members)}")

# 判断：这些是模板位号还是母图位号？
# 从 INSTANCE_ATTR 我们知道母图位号应该是：
# CBB6 → U2, CBB7 → U14
if "U2" in str(cbb6_members):
    print("\n  ✅ CBB6 包含 U2（母图位号）→ .epro2 导出保持了母图位号")
elif "U13" in str(cbb6_members):
    print("\n  ⚠️ CBB6 包含 U13（模板位号）→ 可能是模板位号")

# 检查 CBB6 和 CBB7 的展开是否不同（不同实例应该有不同位号）
overlap = cbb6_members & cbb7_members
only6 = cbb6_members - cbb7_members
only7 = cbb7_members - cbb6_members
print(f"\n  CBB6/CBB7 重叠成员: {len(overlap)}")
print(f"  仅 CBB6 有: {sorted(only6)[:5]}")
print(f"  仅 CBB7 有: {sorted(only7)[:5]}")

# ═══════════════════════════════════════════
print("\n" + "=" * 70)
print("② ControlDAC_A 页有几个 CBB 实例")
print("=" * 70)

p = subprocess.run([sys.executable, R, "--eprj", EPRJ, "--json", "pinmap",
                    "ControlDAC_A", "--schematic", "quadPizeoDriver_RevA"],
                   capture_output=True, text=True, encoding="utf-8")
pdata = json.loads(p.stdout)
cbb_insts = sorted(set(r["designator"] for r in pdata 
                       if r["designator"].startswith("CBB")))
print(f"pinmap 输出的 CBB 实例: {cbb_insts}")
for inst in cbb_insts:
    pins = [r for r in pdata if r["designator"] == inst]
    print(f"  {inst}: {len(pins)} 引脚")

# ═══════════════════════════════════════════
print("\n" + "=" * 70)
print("③ .eprj2 旧版格式中同页的 CBB 展开——对比位号来源")
print("=" * 70)
# 用旧版 .eprj2 涡流工程验证（无 CBB），跳过

# ═══════════════════════════════════════════
print("\n" + "=" * 70)
print("④ CBB 内部器件阻值（从 netlist 网络连接推断）")
print("=" * 70)

# 对 CBB6 展开的每个电阻，找其两端网络
for member in ["R23", "R25", "R26", "R27", "R28", "R29", "R30", "R31"]:
    full_id = f"CBB6.{member}"
    nets_on = []
    for r in rows:
        if full_id in r["components"]:
            nets_on.append(r["net"])
    print(f"  {member}: 连接网络 = {nets_on}")

# ═══════════════════════════════════════════
print("\n" + "=" * 70)
print("⑤ 新版加密 .eprj2 直接读取的 CBB 展开——对比")
print("=" * 70)
p = subprocess.run([sys.executable, R, "--eprj", 
                    r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2",
                    "--json", "netlist"],
                   capture_output=True, text=True, encoding="utf-8")
rows2 = json.loads(p.stdout)
cbb6_new = set()
for r in rows2:
    for c in r["components"]:
        if c.startswith("CBB6."):
            cbb6_new.add(c.split(".", 1)[1])

print(f"新版 .eprj2 CBB6 成员 ({len(cbb6_new)}): {sorted(cbb6_new)}")
print(f".epro2 CBB6 成员:   {len(cbb6_members)}")
same = cbb6_new == cbb6_members
print(f"两者一致: {same}")
