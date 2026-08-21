import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
print("docs:", len(db._docs), "| meta:", len(db._meta))
# CBB 符号文档检查
su = "1cc4f0d4e74cf584"
print("CBB符号 in docs:", su in db._docs,
      "docType:", db._docs.get(su, {}).get("docType"))
print("CBB符号 meta:", str(db._meta.get(su))[:200])
# 符号映射
print("map:", db.cbb_symbol_board_map())
# 页查找
for u, t, s, dt in db.sheets():
    if "ControlDAC_A" in t:
        print("页:", t)
