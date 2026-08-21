import io, json, subprocess, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

TOOL = r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\lceda_reader.py"
NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"

def run(cmd):
    r = subprocess.run([sys.executable, TOOL, "--eprj", NEW] + cmd,
                       capture_output=True, text=True, encoding="utf-8")
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"ERR": r.stdout[:200], "rc": r.returncode}

j = run(["--json", "pinmap", "激励输出和AD采集", "--schematic", "schematic1"])
tot_nc = 0
ports = {}
for row in j:
    if row["designator"].startswith("PORT"):
        ports[row["designator"]] = [(p["pin"], p["net"]) for p in row["pins"]]
    for p in row["pins"]:
        if p.get("not_connected"):
            tot_nc += 1
print("== pinmap 激励输出和AD采集 ==")
print("not_connected 引脚:", tot_nc)
print("PORT 元件:", len(ports))
for des, pins in list(ports.items())[:6]:
    print(f"  {des}: {pins}")

# 全工程 NO_CONNECT / PORT 统计
import collections
tot = collections.Counter()
for t in ("激励输出和AD采集", "DA输出", "对外连接", "STM32H743VIT6",
          "卧贴USB切换串口", "POWER", "板载温度", "探头温度采集",
          "四路低速DA", "高速AD", "高速DA", "基准", "P1"):
    j = run(["--json", "pinmap", t])
    if isinstance(j, dict) and j.get("ERR"):
        continue
    for row in j:
        if row["designator"].startswith("PORT"):
            tot["PORT"] += 1
        for p in row["pins"]:
            if p.get("not_connected"):
                tot["NO_CONNECT"] += 1
print("\n== 全工程统计 ==")
print("PORT(NetFlag/NetPort) 实例:", tot.get("PORT", 0))
print("NO_CONNECT 引脚:", tot.get("NO_CONNECT", 0), "(库内 139)")

# NetFlag 端口网络名验证（PORTe363 应为 +3.3V 附近）
j = run(["--json", "pinmap", "激励输出和AD采集", "--schematic", "schematic1"])
for row in j:
    if row["designator"] == "PORTe363":
        print("\nPORTe363 (+3.3V NetFlag):", [(p["pin"], p["net"]) for p in row["pins"]])