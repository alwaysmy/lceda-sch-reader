import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db = lr.Epro2DB(V3)
lines = db._lines_of()

# 找一个页上 Symbol 值含 GND 的实例 → partId → 符号文档结构
page = next(u for u, t, s, dt in db.sheets()
            if t == "quadPizeoDriver_RevA::ControlDAC_A")
gnd_comp = None
for ln in db._iter_doc_lines(page):
    if '"ATTR"' not in ln[:16]:
        continue
    b = db._jl(ln.partition("||")[2].rstrip("|"))
    if b and b.get("key") == "Symbol" and "GND" in str(b.get("value")):
        print("GND 实例 Symbol attr:", b.get("value"), "parentId:", b.get("parentId"))
        gnd_comp = b.get("parentId")
        break
if gnd_comp:
    for ln in db._iter_doc_lines(page):
        if '"COMPONENT"' in ln[:20] and gnd_comp in ln:
            print("COMPONENT 原文:", ln[:220])
            break

# SHORT 上下文
print("\n== SHORT 出现上下文（前5处） ==")
n = 0
for i, ln in enumerate(lines):
    if "SHORT" in ln:
        j = ln.find("SHORT")
        print(f"  L{i}: ...{ln[max(0,j-60):j+60]}...")
        n += 1
        if n >= 5:
            break

# 符号文档引脚数分布
dist = collections.Counter()
for u, d in db._docs.items():
    if d["docType"] != "SYMBOL":
        continue
    npin = sum(1 for ln in db._iter_doc_lines(u) if '"PIN"' in ln[:14])
    dist[npin] += 1
print("\nSYMBOL 文档 PIN 数分布:", dict(sorted(dist.items())))
