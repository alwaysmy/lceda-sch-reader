import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
su = "1cc4f0d4e74cf584"
d = db._docs[su]
lines = db._lines_of()
print("segs:", [(s, e, t) for s, e, t in d["segs"]])
for s, e, t in d["segs"]:
    print(f"  段 [{s}:{e}] 行数 {e-s}")
    for ln in lines[s:min(s+3, e)]:
        print("     ", ln[:110])
# 全文中有多少行含该 uuid
cnt = sum(1 for ln in lines if "1cc4f0d4e74cf584" in ln[:80])
print("全文含该 uuid 的行数:", cnt)
