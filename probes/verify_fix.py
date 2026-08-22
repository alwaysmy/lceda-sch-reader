import json, io, sys, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
R = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py"
N = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
O = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2"
W = r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe"
p = subprocess.run([sys.executable, R, "--eprj", N, "--eprj", O,
                    "--json", "link-check"], capture_output=True,
                   text=True, encoding="utf-8")
j = json.loads(p.stdout)
rows = j["rows"]
bad = [r for r in rows if r["connector_a"].startswith(("PORT", "SHORT"))
       or r["connector_b"].startswith(("PORT", "SHORT"))]
print("link-check 候选对:", len(rows), "含PORT/SHORT:", len(bad))
for r in rows[:8]:
    print("   %s <-> %s  %s/%s" % (r["connector_a"], r["connector_b"],
                                   r["pin_common"], r["pin_total"]))

# bom / find 差异性质检查
b0 = json.load(open(W + r"\base\bom_new.json", encoding="utf-8"))
b1 = json.load(open(W + r"\after\bom_new.json", encoding="utf-8"))
p = subprocess.run([sys.executable, R, "--eprj", N, "--json", "bom"],
                   capture_output=True, text=True, encoding="utf-8")
b2 = json.loads(p.stdout)
print("\nbom 行数 base/after/now:", len(b0), len(b1), len(b2))
diff_rows = [(x, y) for x, y in zip(b0, b2) if x != y]
print("bom 差异行数:", len(diff_rows))
for x, y in diff_rows[:4]:
    print("   base desig=%s dev=%r desc=%r" % (x["designators"][:20], x["device"], x["description"][:30]))
    print("   now  desig=%s dev=%r desc=%r" % (y["designators"][:20], y["device"], y["description"][:30]))
# 检查是否仍按相同 designators 分行（归并未变）
same_desigs = [x["designators"] for x, y in zip(b0, b2) if x["designators"] == y["designators"]]
print("designators 分组一致的行:", len(same_desigs), "/", len(b0))

f0 = json.load(open(W + r"\base\find_new.json", encoding="utf-8"))
p = subprocess.run([sys.executable, R, "--eprj", N, "--json", "find", "U28"],
                   capture_output=True, text=True, encoding="utf-8")
f2 = json.loads(p.stdout)
print("\nfind U28 差异:", f0 != f2)
for x, y in zip(f0, f2):
    if x != y:
        print("   base:", {k: x[k] for k in ("sheet", "device")}, str(x.get("description"))[:40])
        print("   now :", {k: y[k] for k in ("sheet", "device")}, str(y.get("description"))[:40])
        break

# 0Ω 跳线识别数量（应仍为 14 个 0Ω 电阻 + short 符号）
import lceda_reader as lr
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
db = lr.LcedaDB(N)
jump = set()
shorts = set()
for uuid, title, sch, dt in db.sheets():
    if dt != 1:
        continue
    sh = lr.parse_sheet(db, uuid)
    dmap = db.device_map()
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
print("SHORT 短接符:", len(shorts), sorted(shorts)[:6])