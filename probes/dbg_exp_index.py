import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
print("docs:", len(db._docs), "meta:", len(db._meta),
      "boards:", len(db._boards), "schs:", len(db._schs),
      "pages:", len(db._pages))
# 抽一个 BOARD / SCH / PAGE
for u, d in list(db._docs.items()):
    if d["docType"] == "BOARD":
        print("BOARD", u[:12], "meta:", str(db._meta.get(u))[:120])
        break
for u, d in list(db._docs.items()):
    if d["docType"] == "SCH":
        print("SCH", u[:12], "meta:", str(db._meta.get(u))[:160])
        break
for u, d in list(db._docs.items()):
    if d["docType"] == "SCH_PAGE":
        print("PAGE", u[:12], "meta:", str(db._meta.get(u))[:160])
        break
