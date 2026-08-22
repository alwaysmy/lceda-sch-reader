import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db = lr.Epro2DB(V3)
for pu, p in db._pages.items():
    if "old" in p["title"] and not p["schematic"]:
        print("PAGE", pu[:14], p)
        # 该文档段内的全部记录类型与 META 原文
        d = db._docs[pu]
        for s, e, t in d["segs"]:
            print(f"   seg {s}-{e} ticket={t}")
            for ln in db._lines_of()[s:e]:
                head, _, body = ln.partition("||")
                h = db._jl(head)
                if h and h.get("type") in ("DOCHEAD", "META"):
                    print("     ", h.get("type"),
                          str(db._jl(body.rstrip("|")))[:200])
        break
# 全部无 schematic 的页数
n = sum(1 for p in db._pages.values() if not p["schematic"])
print("无 schematic 的页数:", n)
# 对应 SCH 文档（uuid 前缀匹配这些页？）列出全部 SCH meta
for u, s in db._schs.items():
    if "old" in s["title"] or not s["board"]:
        print("SCH", u[:16], s)
