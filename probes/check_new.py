import io, json, re, subprocess, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

TOOL = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py"
NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"

def run(eprj, cmd):
    r = subprocess.run([sys.executable, TOOL, "--eprj", eprj] + cmd,
                       capture_output=True, text=True, encoding="utf-8")
    return json.loads(r.stdout)

# 各页元件/网络统计
nl = run(NEW, ["--json", "netlist"])
net_comp = {}
for r in nl:
    if r["net"]:
        net_comp[r["net"]] = len(r["components"])

print("== 新版关键网络成员数 ==")
for n in ["+15V", "-15V", "+24V", "+6.8V", "+3.9V", "+1.96V-REF", "+2.5V-REF",
          "V_REF", "EXT_REF", "2.5V+SIGNAL", "ADCIN", "IN_AM", "MUXOUT",
          "U_TEMP_SENSOR", "U_TEMP_CONTROLLER", "TEMP_CAL"]:
    print(f"  {n:20s}: {net_comp.get(n, 0)} 个元件")

# 逐页统计
print("\n== 新版逐页统计 ==")
sheets = subprocess.run([sys.executable, TOOL, "--eprj", NEW, "list"],
                        capture_output=True, text=True, encoding="utf-8").stdout
for ln in sheets.splitlines():
    m = re.match(r"\s*\[sch=(\S+)\s*\]\s*(.+)", ln)
    if m:
        sch, title = m.group(1), m.group(2).strip()
        if sch.startswith("schematic"):
            try:
                comps = run(NEW, ["--json", "components", title])
                n_real = sum(1 for c in comps if c.get("designator"))
                print(f"  {sch:14s} {title:20s}: {n_real} 元件")
            except Exception as e:
                print(f"  {sch:14s} {title:20s}: ERR {e}")