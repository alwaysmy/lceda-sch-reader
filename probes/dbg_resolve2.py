import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
sig = lr._cbb_sig(db)
r = lr._resolve_cbb_target(db, sig, "_cbb_max5318_2l")
print("resolve ->", r, "| sig 样例:",
      [(t) for _, _, t in list({(u, p, ti) for u, (p, f, ti) in sig.items()})[:5]]
      if sig else "空")
# 全局 netlist 的 CBB 条目
import json
rows = json.load(open(r"C:\Users\dell\AppData\Local\Temp\nla.json",
                      encoding="utf-8"))
comps = set()
for r2 in rows:
    for c in r2["components"]:
        if "." in c:
            comps.add(c.split(".")[0])
print("CBB 展开实例:", len(comps), sorted(comps)[:8])
