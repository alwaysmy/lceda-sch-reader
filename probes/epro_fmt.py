import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

E2 = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_TPS56C230_Buck_12Vto5V_6A_2026-08-13.epro"
db = lr.EproDB(E2)
for uuid, title, sch, dt in db.sheets():
    recs = db.sheet_records(uuid)
    kinds = collections.Counter(a[0] for a in recs if isinstance(a, list))
    print(title, "记录类型:", dict(kinds))
    for a in recs:
        if isinstance(a, list) and a[0] == "WIRE":
            print("WIRE 样例:", json.dumps(a)[:200])
            break
    for a in recs:
        if isinstance(a, list) and a[0] == "ATTR" and a[3] == "NET":
            print("ATTR NET 样例:", json.dumps(a)[:160])
            break
    for a in recs:
        if isinstance(a, list) and a[0] == "COMPONENT":
            print("COMPONENT 样例:", json.dumps(a)[:160])
            break
    # Convert to PCB 取值分布
    vals = collections.Counter()
    for a in recs:
        if isinstance(a, list) and len(a) >= 5 and a[0] == "ATTR" and \
                a[3] in ("Convert to PCB", "Add into BOM"):
            vals[(a[3], str(a[4]))] += 1
    print("BOM/PCB 标志取值:", dict(vals))
    break

# E1 的 Convert to PCB 取值
E1 = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
db1 = lr.EproDB(E1)
vals = collections.Counter()
dnp0r = []
for uuid, title, sch, dt in db1.sheets():
    recs = db1.sheet_records(uuid)
    if not recs:
        continue
    desig_of = {}
    title_of = {}
    attrs_of = collections.defaultdict(dict)
    for a in recs:
        if not isinstance(a, list) or len(a) < 5 or a[0] != "ATTR":
            continue
        if a[3] == "Designator":
            desig_of[a[2]] = a[4]
        if a[3] == "Name" or a[3] in ("Convert to PCB", "Add into BOM"):
            attrs_of[a[2]][a[3]] = str(a[4])
    for cid, at in attrs_of.items():
        if "Convert to PCB" in at:
            vals[at["Convert to PCB"]] += 1
        if at.get("Add into BOM") == "no":
            t = title_of.get(cid) or ""
            d = desig_of.get(cid, "")
            if d.startswith("R") or "0R" in t or "0000" in t:
                dnp0r.append((title, d, t, at.get("Convert to PCB")))
print("E1 Convert to PCB 取值分布:", dict(vals))
print("E1 上BOM=no 且位号R开头的实例:", len(dnp0r), dnp0r[:10])