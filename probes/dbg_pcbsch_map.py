"""PCB↔SCH 器件映射深度调查。"""
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

pcb_u = conn.execute("SELECT uuid FROM documents WHERE docType=3 LIMIT 1").fetchone()[0]
sch_u = None
for row in conn.execute("SELECT uuid, length(dataStr) FROM documents WHERE docType=1 ORDER BY length(dataStr) DESC"):
    if row[1] > 5000:
        sch_u = row[0]
        break

sch_text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (sch_u,)).fetchone()[0])
pcb_text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (pcb_u,)).fetchone()[0])

def parse_recs(text):
    recs = []
    for ln in text.split("\n"):
        try:
            a = json.loads(ln)
            if isinstance(a, list): recs.append(a)
        except: pass
    return recs

sch_recs = parse_recs(sch_text)
pcb_recs = parse_recs(pcb_text)

# ── SCH COMPONENT + 紧随 ATTR ──
print("== ① SCH COMPONENT 完整结构 ==")
sch_comps = []
i = 0
while i < len(sch_recs):
    a = sch_recs[i]
    if a[0] == "COMPONENT":
        cid = a[1]
        comp = {"record": a[:8], "attrs": {}}
        j = i + 1
        while j < len(sch_recs) and j < i + 30:
            b = sch_recs[j]
            if b[0] == "ATTR" and len(b) >= 5 and b[2] == cid:
                comp["attrs"][b[3]] = str(b[4])[:60]
                j += 1
            elif b[0] == "ATTR":
                j += 1
            else:
                break
        sch_comps.append(comp)
        i = j
    else:
        i += 1

print(f"SCH 组件数: {len(sch_comps)}")
for c in sch_comps[:3]:
    print(f"  record: {json.dumps(c['record'], ensure_ascii=False)[:180]}")
    print(f"  attrs: {json.dumps(c['attrs'], ensure_ascii=False)[:250]}")
    print()

# ── PCB COMPONENT + 紧随 ATTR/PAD_NET ──
print("\n== ② PCB COMPONENT 完整结构 ==")
pcb_comps = []
i = 0
while i < len(pcb_recs):
    a = pcb_recs[i]
    if a[0] == "COMPONENT":
        cid = a[1]
        comp = {"record": a[:8], "attrs": {}, "pad_nets": []}
        j = i + 1
        while j < len(pcb_recs) and j < i + 50:
            b = pcb_recs[j]
            if b[0] == "ATTR" and len(b) >= 5 and len(b) > 2 and str(b[2]) == cid:
                comp["attrs"][b[3]] = str(b[4])[:60]
                j += 1
            elif b[0] == "PAD_NET":
                comp["pad_nets"].append(b)
                j += 1
            elif b[0] in ("LINE", "ARC", "CIRCLE", "RECT", "STRING"):
                j += 1  # 封装图形，跳过
            else:
                break
        pcb_comps.append(comp)
        i = j
    else:
        i += 1

print(f"PCB 组件数: {len(pcb_comps)}")
for c in pcb_comps[:3]:
    print(f"  record: {json.dumps(c['record'], ensure_ascii=False)[:200]}")
    print(f"  attrs: {json.dumps(c['attrs'], ensure_ascii=False)[:250]}")
    print(f"  pad_nets: {len(c['pad_nets'])} 条")
    print()

# ── 映射键候选对比 ──
print("\n== ③ 映射键候选 ==")

# SCH 侧：收集 Designator 和 Unique ID
sch_by_desig = {}
sch_uids = set()
for c in sch_comps:
    d = c["attrs"].get("Designator", "")
    uid = c["attrs"].get("Unique ID", "")
    if d:
        sch_by_desig[d] = c
    if uid:
        sch_uids.add(uid)

# PCB 侧
pcb_by_desig = {}
pcb_uids = set()
for c in pcb_comps:
    d = c["attrs"].get("Designator", "") or \
        c["attrs"].get("designator", "")
    uid = c["attrs"].get("Unique ID", "")
    if d:
        pcb_by_desig[d] = c
    if uid:
        pcb_uids.add(uid)

# Designator 交叉
sch_d = set(sch_by_desig.keys())
pcb_d = set(pcb_by_desig.keys())
overlap = sch_d & pcb_d
print(f"SCH 位号数: {len(sch_d)}")
print(f"PCB 位号数: {len(pcb_d)}")
print(f"位号交集: {len(overlap)}")
if overlap:
    print(f"  样例: {sorted(overlap)[:10]}")

# UID 交叉
sch_u = {c["attrs"].get("Unique ID") for c in sch_comps 
         if c["attrs"].get("Unique ID")}
pcb_u = {c["attrs"].get("Unique ID") for c in pcb_comps 
         if c["attrs"].get("Unique ID")}
uid_overlap = sch_u & pcb_u
print(f"\nSCH UniqueID 数: {len(sch_u)}")
print(f"PCB UniqueID 数: {len(pcb_u)}")
print(f"UID 交集: {len(uid_overlap)}")

# 检查 PCB attrs 是否有其他可关联字段
all_pcb_attr_keys = set()
for c in pcb_comps:
    all_pcb_attr_keys.update(c["attrs"].keys())
all_sch_attr_keys = set()
for c in sch_comps:
    all_sch_attr_keys.update(c["attrs"].keys())
common_keys = all_sch_attr_keys & all_pcb_attr_keys
print(f"\nSCH/PCB 共有属性键: {sorted(common_keys)}")
