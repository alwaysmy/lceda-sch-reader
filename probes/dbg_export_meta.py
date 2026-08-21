import io, sys, json, zipfile, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
z = zipfile.ZipFile(X)
name = [n for n in z.namelist() if n.endswith(".epru")][0]
text = z.read(name).decode("utf-8")
lines = text.split("\n")
print("总行数:", len(lines))
# 定位 CBB 符号 DOCHEAD
idx = [i for i, ln in enumerate(lines)
       if '"DOCHEAD"' in ln[:30] and '1cc4f0d4e74cf584' in ln]
print("CBB 符号 DOCHEAD 行号:", idx)
if idx:
    i0 = idx[0]
    seg = lines[i0:i0+80]
    metas = [j for j, ln in enumerate(seg) if '"META"' in ln[:16]]
    print("段内 META 行偏移:", metas[:3])
    if metas:
        print("META 内容:", seg[metas[0]][:220])
    # 该段到下一个 DOCHEAD 的范围
    nxt = None
    for j in range(i0+1, len(lines)):
        if '"DOCHEAD"' in lines[j][:30]:
            nxt = j
            break
    print("段长度:", (nxt or len(lines)) - i0)
    print("段尾 3 行:")
    for ln in lines[(nxt or len(lines))-3:nxt or len(lines)]:
        print("   ", ln[:150])
