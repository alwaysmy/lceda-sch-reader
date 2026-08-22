import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
su = "1cc4f0d4e74cf584"
print("CBB符号 in docs:", su in db._docs)
print("meta:", str(db._meta.get(su))[:250])
print("map:", db.cbb_symbol_board_map())
# 实抓段里 CBB 符号的 META 行
import zipfile
z = zipfile.ZipFile(X)
name = [n for n in z.namelist() if n.endswith(".epru")][0]
lines = z.read(name).decode("utf-8").split("\n")
for i, ln in enumerate(lines):
    if '"DOCHEAD"' in ln[:30] and "1cc4f0d4e74cf584" in ln:
        print("DOCHEAD L", i, ln[:120])
        for j in range(i+1, min(i+4, len(lines))):
            print("  +", j, lines[j][:140])
        break
