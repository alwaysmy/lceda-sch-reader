import io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

F_3 = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\V1.1版主控原理图\MCU主控-V1.1-2026.05.06_backup\MCU主控-V1.1-2026.05.06_2026-08-07-14-46.epro2"
db = lr.Epro2DB(F_3)
page = None
for u, t, s, dt in db.sheets():
    if dt != 1:
        continue
    sh = lr.parse_sheet(db, u)
    desigs = {c.get("designator") for c in sh["components"]}
    if "U3" in desigs:
        page = u
        break
print("页:", page)
def comps(u):
    return lr.parse_sheet(db, u)["components"]
c3 = next(c for c in comps(page) if c.get("designator") == "U3")
print("U3 title:", repr(c3.get("title")), "symbol_uuid:",
      repr(c3.get("symbol_uuid")), "device:", repr(c3.get("device_uuid")))
sp = db.symbol_pins(c3.get("symbol_uuid"))
print("symbol_pins:", None if not sp else
      f"pins={len(sp['pins'])} parts={sp['parts']} type={sp['symbol_type']}")
if not sp or not sp["pins"]:
    # dump 该符号文档原始记录类型
    su = c3.get("symbol_uuid")
    su2 = db._sym_uuid_by_title(su) if su else None
    print("  标题解析:", su2)
    docu = su if su in db._docs else su2
    if docu:
        kinds = collections.Counter()
        for ln in db._iter_doc_lines(docu):
            head, _, body = ln.partition("||")
            h = db._jl(head)
            if h:
                kinds[h.get("type")] += 1
        print("  符号文档记录分布:", dict(kinds))
        # PART/PIN 明细
        for ln in db._iter_doc_lines(docu):
            head, _, body = ln.partition("||")
            h = db._jl(head)
            if h and h.get("type") in ("PART", "PIN"):
                b = db._jl(body.rstrip("|"))
                print(f"   [{h['type']}] id={h.get('id')}:",
                      json.dumps(b, ensure_ascii=False)[:150])
