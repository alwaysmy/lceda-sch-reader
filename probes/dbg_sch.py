import io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db = lr.Epro2DB(V3)
print("SCH uuids:", sorted(u[:20] for u in db._schs))
miss = collections.Counter()
for pu, p in db._pages.items():
    su = p["schematic"]
    if su not in db._schs:
        miss[su] += 1
print("未命中 schematic 引用:", dict(miss))
for su in list(miss)[:4]:
    cands = [u for u in db._docs if u.startswith(su[:16]) or su.startswith(u)]
    info = [(c[:16], db._docs[c]["docType"]) for c in cands[:3]]
    print(f"  {su} -> 前缀匹配: {info}")
