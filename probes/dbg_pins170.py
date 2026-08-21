import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
sig = lr._cbb_sig(db)
r = lr._resolve_cbb_target(db, sig, "_cbb_max5318_2l")
print("resolve('_cbb_max5318_2l') ->", r)
sp = db.symbol_pins("1cc4f0d4e74cf584")
print("pins:", len(sp["pins"]), "parts:", sp["parts"][:5])
# PIN id 样例（看是否多版本混杂）
print("pin ids:", [p["id"][:10] for p in sp["pins"][:8]])
# 导出 epru 中该符号段的 PIN 行数
import zipfile
z = zipfile.ZipFile(X)
name = [n for n in z.namelist() if n.endswith(".epru")][0]
lines = z.read(name).decode("utf-8").split("\n")
idx = [i for i, ln in enumerate(lines)
       if '"DOCHEAD"' in ln[:30] and "1cc4f0d4e74cf584" in ln]
print("该符号 DOCHEAD 段数:", len(idx))
for i0 in idx:
    nxt = None
    for j in range(i0+1, len(lines)):
        if '"DOCHEAD"' in lines[j][:30]:
            nxt = j
            break
    seg = lines[i0:(nxt or len(lines))]
    npin = sum(1 for ln in seg if '"PIN"' in ln[:14])
    print(f"  段 L{i0}: 行 {len(seg)}, PIN {npin}")
