import json, io, sys, subprocess
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import lceda_reader as lr

R = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py"
N = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
W = r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe"

b0 = json.load(open(W + r"\base\bom_new.json", encoding="utf-8"))
p = subprocess.run([sys.executable, R, "--eprj", N, "--json", "bom"],
                   capture_output=True, text=True, encoding="utf-8")
b2 = json.loads(p.stdout)
m0 = {x["designators"]: x for x in b0}
m2 = {x["designators"]: x for x in b2}
print("bom 组数 base/now:", len(m0), len(m2))
print("designators 集合一致:", set(m0) == set(m2))
only0 = set(m0) - set(m2)
only2 = set(m2) - set(m0)
print("仅基线有的组:", len(only0), sorted(only0)[:4])
print("仅修复后有的组:", len(only2), sorted(only2)[:4])
devchg = [(d, m0[d]["device"], m2[d]["device"]) for d in m0
          if d in m2 and m0[d]["device"] != m2[d]["device"]]
print("device 字段变化组:", len(devchg), devchg[:3])
descchg = sum(1 for d in m0 if d in m2 and m0[d]["description"] != m2[d]["description"])
print("desc 字段变化组:", descchg)

db = lr.LcedaDB(N)
jump = set()
shorts = set()
dmap = db.device_map()
for uuid, title, sch, dt in db.sheets():
    if dt != 1:
        continue
    sh = lr.parse_sheet(db, uuid)
    for c in sh["components"]:
        du = c.get("device_uuid") or c.get("symbol_uuid") or ""
        desc = dmap.get(du, ("", "", ""))[2] if du else ""
        if lr._is_zero_ohm(c.get("title"), desc):
            jump.add(c.get("designator"))
        sym = lr.symbol_of(db, c)
        sp = db.symbol_pins(sym) if sym else None
        if sp and sp.get("symbol_type") == 22:
            shorts.add(lr._synth_designator(db, c))
print("\n0Ω 跳线识别:", len(jump), sorted(jump))
print("SHORT 短接符:", len(shorts), sorted(shorts)[:8])