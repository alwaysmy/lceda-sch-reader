import io, json, re, subprocess, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

TOOL = r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\lceda_reader.py"
OLD = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2"
NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"

def run(eprj, cmd):
    r = subprocess.run([sys.executable, TOOL, "--eprj", eprj] + cmd,
                       capture_output=True, text=True, encoding="utf-8")
    return json.loads(r.stdout)

nl_o = run(OLD, ["--json", "netlist"])
nl_n = run(NEW, ["--json", "netlist"])

nets_o = {r["net"] for r in nl_o}
nets_n = {r["net"] for r in nl_n}
print(f"旧版网络: {len(nets_o)}, 新版网络: {len(nets_n)}")
print(f"新版新增网络({len(nets_n - nets_o)}):")
for n in sorted(x for x in nets_n - nets_o if x):
    print(f"  + {n}")
print(f"新版缺失网络({len(nets_o - nets_n)}):")
for n in sorted(x for x in nets_o - nets_n if x):
    print(f"  - {n}")

# 连接器对比
def conns(eprj):
    out = subprocess.run([sys.executable, TOOL, "--eprj", eprj, "pinmap", "对外连接"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    return out

print("\n=== 旧版 对外连接 页连接器 ===")
print(conns(OLD)[:1500])