"""精确核对：CBB6/CBB7 在母图上的实际展开位号。
从 netlist 中 CBB6./CBB7. 前缀条目 + INSTANCE_ATTR 对照。"""
import io, sys, json, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
R = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py"
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"

p = subprocess.run([sys.executable, R, "--eprj", E, "--json", "netlist"],
                   capture_output=True, text=True, encoding="utf-8")
rows = json.loads(p.stdout)

# 收集 CBB6/CBB7 的全部展开成员及其网络
cbb6 = {}  # member → set(nets)
cbb7 = {}
for r in rows:
    for c in r["components"]:
        if "." in c:
            prefix, member = c.split(".", 1)
            if prefix == "CBB6":
                cbb6.setdefault(member, set()).update(r["sheets"])
            elif prefix == "CBB7":
                cbb7.setdefault(member, set()).update(r["sheets"])

print("== 当前工具输出的 CBB6 展开成员 ==")
for m in sorted(cbb6):
    print(f"  {m}")

print(f"\n== 当前工具输出的 CBB7 展开成员 ==")
for m in sorted(cbb7):
    print(f"  {m}")

# 现在用 getSourceCode 直接看 ControlDAC_A 页上 CBB6 引脚连接的元件
print("\n" + "="*60)
print("通过 pinmap 查 ControlDAC_A 页上 CBB6 引脚连接的对端器件")
p = subprocess.run([sys.executable, R, "--eprj", E, "--json", "pinmap",
                    "ControlDAC_A", "--schematic", "quadPizeoDriver_RevA"],
                   capture_output=True, text=True, encoding="utf-8")
pdata = json.loads(p.stdout)
for row in pdata:
    if row["designator"] == "CBB6":
        for pm in row["pins"]:
            if pm["net"]:
                print(f"  CBB6.{pm['pin']} -> {pm['net']}")

print("\n通过 netfind DAC0_SCLK_A 查贯通成员:")
p = subprocess.run([sys.executable, R, "--eprj", E, "netfind", "DAC0_SCLK_A"],
                   capture_output=True, text=True, encoding="utf-8")
for ln in p.stdout.split("\n"):
    if "CBB6." in ln or "U13" in ln or "U2" in ln:
        print(f"  {ln.strip()}")
