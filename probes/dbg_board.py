import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db = lr.Epro2DB(V3)
bkeys = {u for u, _, _ in db._boards}
print("BOARD uuid 长度分布:", {len(u) for u in bkeys})
for u, s in db._schs.items():
    b = s["board"]
    ok = b in bkeys
    if not ok:
        cand = [k for k in bkeys if k and b and (k.startswith(b) or b.startswith(k))]
        print(f"  SCH {u[:12]} board={b} 未命中, 前缀候选={[(c[:16], dict((bu,bt) for bu,bt,_ in db._boards)[c]) for c in cand]}")
