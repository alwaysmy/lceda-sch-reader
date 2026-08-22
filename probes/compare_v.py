import io, json, re, subprocess, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

TOOL = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py"
OLD = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2"
NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"

def run(eprj, cmd):
    r = subprocess.run([sys.executable, TOOL, "--eprj", eprj] + cmd,
                       capture_output=True, text=True, encoding="utf-8")
    return json.loads(r.stdout)

def parse_desigs(row):
    return [x for x in row["designators"].split(",") if x]

def stats(eprj, tag):
    bom = run(eprj, ["--json", "bom"])
    netlist = run(eprj, ["--json", "netlist"])
    n_comp = 0
    for r in bom:
        n_comp += len(parse_desigs(r))
    print(f"== {tag} ==")
    print(f"  BOM 器件类型: {len(bom)}, 元件实例总数: {n_comp}")
    print(f"  网络总数: {len(netlist)}")
    nets = sorted((r["net"] or "") for r in netlist)
    pow = [n for n in nets if re.match(r'^(GND|AGND|DGND|PGND|VCC|VDD|VSS|VBUS|D3V3|3V3|3\.3V|5V|\+3\.3V|\+5V|\+15V|-15V|15V)$', n, re.I)]
    sig = [n for n in nets if n and n not in pow]
    print(f"  电源网络: {len(pow)}, 信号网络: {len(sig)}")
    print(f"  样例信号网络: {sig[:12]}")
    return bom, netlist

bom_o, nl_o = stats(OLD, "旧版 涡流传感器.eprj2")
print()
bom_n, nl_n = stats(NEW, "新版 涡流传感器-V1.0-2026.04.01.eprj2")

print()
desigs_o = set()
for r in bom_o:
    desigs_o |= set(parse_desigs(r))
desigs_n = set()
for r in bom_n:
    desigs_n |= set(parse_desigs(r))
print(f"旧版位号数: {len(desigs_o)}, 新版位号数: {len(desigs_n)}")
print(f"新版新增位号({len(desigs_n - desigs_o)}): {sorted(desigs_n - desigs_o)[:40]}")
print(f"新版缺失位号({len(desigs_o - desigs_n)}): {sorted(desigs_o - desigs_n)[:40]}")