"""精确核对：在母图上找 CBB6/CBB7 内部器件的真实位号。
方法：通过 CBB6 引脚连接的网络名，找到这些网络上的其他元件，
      再对照 LCEDA 中看到的位号。"""
import io, sys, json, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
R = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py"
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"

# 获取全工程 netlist
p = subprocess.run([sys.executable, R, "--eprj", E, "--json", "netlist"],
                   capture_output=True, text=True, encoding="utf-8")
rows = json.loads(p.stdout)

# 1) 找 CBB6 引脚连接的网络
cbb6_nets = set()
for r in rows:
    for c in r["components"]:
        if c == "CBB6":
            cbb6_nets.add(r["net"])

print("CBB6 连接的网络:", sorted(cbb6_nets))

# 2) 在这些网络上找所有非 CBB 前缀的器件（这些可能是 CBB 内部的真实位号）
print("\n== 这些网络上的全部非端口/非短接元件 ==")
for net in sorted(cbb6_nets):
    members = []
    for r in rows:
        if r["net"] == net:
            for c in r["components"]:
                if not c.startswith(("PORT", "SHORT", "CBB")):
                    members.append((net, c))
    if members:
        print(f"\n  {net}:")
        for n, c in sorted(members):
            print(f"    {c}")

# 3) 同样查 CBB7
print("\n\n== CBB7 网络 ==")
cbb7_nets = set()
for r in rows:
    for c in r["components"]:
        if c == "CBB7":
            cbb7_nets.add(r["net"])
for net in sorted(cbb7_nets):
    members = []
    for r in rows:
        if r["net"] == net:
            for c in r["components"]:
                if not c.startswith(("PORT", "SHORT", "CBB")):
                    members.append((net, c))
    if members:
        print(f"\n  {net}:")
        for n, c in sorted(members):
            print(f"    {c}")
