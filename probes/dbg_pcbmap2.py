"""核对 SCH↔PCB 器件映射：Unique ID 交集 + Designator 对应。"""
import io, sys, json, sqlite3, base64, gzip, re, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)

def decompress(ds):
    if not ds: return ""
    if ds.startswith("base64"):
        raw = base64.b64decode(ds[6:])
        try: return gzip.decompress(raw).decode("utf-8")
        except: return raw.decode("utf-8", errors="replace")
    return ds

# 找同一板的 SCH 和 PCB
# boards 表为空（旧版），用 documents 的 title 匹配
# pcb1 ↔ schematic1（编号对应）
pcb_uuid = conn.execute(
    "SELECT uuid FROM documents WHERE docType=3 AND title='pcb1'").fetchone()
if pcb_uuid:
    pcb_uuid = pcb_uuid[0]
else:
    pcb_uuid = conn.execute(
        "SELECT uuid FROM documents WHERE docType=3 LIMIT 1").fetchone()[0]

sch_uuid = conn.execute(
    "SELECT uuid FROM documents WHERE docType=1 AND title LIKE '%1%' LIMIT 1"
).fetchone()
if sch_uuid:
    sch_uuid = sch_uuid[0]
else:
    sch_uuid = conn.execute(
        "SELECT uuid FROM documents WHERE docType=1 LIMIT 1").fetchone()[0]

sch_text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (sch_uuid,)).fetchone()[0])
pcb_text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (pcb_uuid,)).fetchone()[0])

# 提取两页的 Unique ID 集合
sch_uids = set(re.findall(r'"Unique ID"\s*,\s*"([^"]+)"', sch_text))
pcb_uids = set(re.findall(r'"Unique ID"\s*,\s*"([^"]+)"', pcb_text))

overlap = sch_uids & pcb_uids
print(f"SCH 页 UID 数: {len(sch_uids)}")
print(f"PCB 页 UID 数: {len(pcb_uids)}")
print(f"UID 交集: {len(overlap)}")
if overlap:
    print("  样例:", sorted(overlap)[:10])

# 也检查 Designator 交叉
sch_desigs = set(re.findall(r'"Designator"\s*,\s*"([^"]+)"', sch_text))
pcb_desigs = set(re.findall(r'"Designator"\s*,\s*"([^"]+)"', pcb_text))
des_overlap = sch_desigs & pcb_desigs
print(f"\nSCH Designator 数: {len(sch_desigs)}")
print(f"PCB Designator 数: {len(pcb_desigs)}")
print(f"Designator 交集: {len(des_overlap)}")
print(f"  样例: {sorted(des_overlap)[:15]}")

conn.close()

# ══════════════════════════════════════
# .epro2 Piezo 检查
# ══════════════════════════════════════
X = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro2"
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr
db = lr.Epro2DB(X)

# 找一个有内容的 PCB 文档和一个 SCH_PAGE 文档
pcb_u = sch_u = None
for u, d in db._docs.items():
    if d["docType"] == "PCB" and not pcb_u:
        pcb_u = u
    if d["docType"] == "SCH_PAGE" and not sch_u:
        # 找有 COMPONENT 的
        recs = db.sheet_records(u)
        if recs and any(r[0] == "COMPONENT" for r in recs):
            sch_u = u

if pcb_u and sch_u:
    pcb_lines = list(db._iter_doc_lines(pcb_u))
    sch_lines = list(db._iter_doc_lines(sch_u))
    
    pcb_uids = set()
    sch_uids = set()
    
    for ln in pcb_lines:
        head, _, body = ln.partition("||")
        h = db._jl(head)
        b = db._jl(body.rstrip("|"))
        if h and b and isinstance(b, dict):
            uid = b.get("Unique ID") or b.get("unique_id")
            if uid:
                pcb_uids.add(uid)
    
    for ln in sch_lines:
        if '"ATTR"' not in ln[:16]:
            continue
        b = db._jl(ln.partition("||")[2].rstrip("|"))
        if b and isinstance(b, dict) and b.get("key") == "Unique ID":
            sch_uids.add(b.get("value"))
    
    overlap = pcb_uids & sch_uids
    print(f"\n== .epro2 Piezo ==")
    print(f"PCB UID 数: {len(pcb_uids)}, SCH_UID 数: {len(sch_uids)}, 交集: {len(overlap)}")
    if overlap:
        print(f"  交集样例: {sorted(overlap)[:5]}")
