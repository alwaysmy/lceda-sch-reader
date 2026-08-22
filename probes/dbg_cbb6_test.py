"""实测：两个修订版图中 CBB6 内部器件与位号对比。
通过 netlist 中 CBB6.* 展开条目提取成员列表。"""
import io, sys, json, subprocess, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
R = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py"
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"

for rev in ("quadPizeoDriver_RevA", "quadPizeoDriver_RevA_1.1"):
    print(f"\n{'='*60}")
    print(f"图: {rev}")
    print(f"{'='*60}")

    # 逐页查 CBB6 的展开条目
    members = set()   # (模板cid, 母图位号) 对
    for page in ("ControlDAC_A",):
        p = subprocess.run(
            [sys.executable, R, "--eprj", E, "--json", "netlist"],
            capture_output=True, text=True, encoding="utf-8")
        rows = json.loads(p.stdout)
        for row in rows:
            for c in row["components"]:
                if c.startswith("CBB6."):
                    member_des = c.split(".", 1)[1]
                    members.add(member_des)

    if not members:
        # 尝试通过 pinmap 获取
        p = subprocess.run(
            [sys.executable, R, "--eprj", E, "--json", "pinmap",
             f"{rev}::ControlDAC_A" if "::" in rev else "ControlDAC_A",
             "--schematic", rev],
            capture_output=True, text=True, encoding="utf-8")
        try:
            pdata = json.loads(p.stdout)
            for row in pdata:
                des = row["designator"]
                if des.startswith("CBB6."):
                    members.add(des.split(".", 1)[1])
        except Exception:
            pass

    if members:
        print(f"  CBB6 内部器件位号 ({len(members)} 个):")
        for m in sorted(members):
            print(f"    {m}")
    else:
        print("  未找到展开条目")

    # 也查 CBB7
print("\n" + "="*60)
print("用 netlist 全局搜 CBB6./CBB7. 前缀:")
p = subprocess.run(
    [sys.executable, R, "--eprj", E, "--json", "netlist"],
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

print(f"\nCBB6 (MAX5318 DAC) 内部器件:")
for m in sorted(cbb6_members):
    print(f"  {m}")
print(f"CBB7 (MAX5318 DAC) 内部器件:")
for m in sorted(cbb7_members):
    print(f"  {m}")
