"""PCB↔SCH 器件映射深度调查：
① PCB COMPONENT 的完整属性（找与 SCH 的关联键）
② SCH COMPONENT 的完整属性（同上）
③ 对比两者看有哪些字段可以建立映射
④ 检查 LCEDA 是否有专门的 sch-pcb 链接机制"""
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

# 找一个 SCH 页和一个 PCB 页（同一板的）
# 先列出全部文档
docs_list = list(conn.execute(
    "SELECT uuid, title, docType FROM documents ORDER BY docType, title"))
for u, t, dt in docs_list:
    print(f"  {dt} {t[:30]} {u[:12]}")

# 取 pcb1 和 schematic1 的第一个页
pcb_u = conn.execute(
    "SELECT uuid FROM documents WHERE docType=3 AND title LIKE '%1%' LIMIT 1").fetchone()
if pcb_uuid := (pcb_u[0] if pcb_u else None):
    pass

# 直接取第一个 PCB 和第一个有内容的 SCH
pcb_u = conn.execute("SELECT uuid FROM documents WHERE docType=3 LIMIT 1").fetchone()[0]
sch_u = None
for row in conn.execute("SELECT uuid, length(dataStr) FROM documents WHERE docType=1"):
    if row[1] > 5000:
        sch_u = row[0]
        break

print(f"\n分析: SCH={sch_u[:12]} PCB={pcb_u[:12]}")

sch_text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (sch_u,)).fetchone()[0])
pcb_text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (pcb_u,)).fetchone()[0])

def parse_records(text):
    recs = []
    for ln in text.split("\n"):
        try:
            a = json.loads(ln)
            if isinstance(a, list):
                recs.append(a)
        except:
            pass
    return recs

sch_recs = parse_records(sch_text)
pcb_recs = parse_records(pcb_text)

print(f"\nSCH 记录数: {len(sch_recs)}")
print(f"PCB 记录数: {len(pcb_recs)}")

# ════════════════════════════════
# 1) SCH COMPONENT 的完整结构
# ════════════════════════════════
print("\n== 1) SCH COMPONENT 完整记录（含后续 ATTR） ==")
sch_comps = []
i = 0
while i < len(sch_recs):
    a = sch_recs[i]
    if a[0] == "COMPONENT":
        cid = a[1]
        comp = {"record": a, "attrs": {}}
        # 收集紧随其后的 ATTR
        j = i + 1
        while j < len(sch_recs):
            b = sch_recs[j]
            if b[0] == "ATTR" and len(b) >= 5 and b[2] == cid:
                comp["attrs"][b[3]] = str(b[4])[:60]
                j += 1
            else:
                break
        sch_comps.append(comp)
        i = j
    else:
        i += 1

print(f"SCH 组件数: {len(sch_comps)}")
for c in sch_comps[:3]:
    print(f"  record: {json.dumps(c['record'], ensure_ascii=False)[:200]}")
    print(f"  attrs: {json.dumps(c['attrs'], ensure_ascii=False)[:300]}")
    print()

# ════════════════════════════════
# 2) PCB COMPONENT 的完整结构
# ════════════════════════════════
print("\n== 2) PCB COMPONENT 完整记录（含后续 ATTR/PAD_NET） ==")
pcb_comps = []
i = 0
while i < len(pcb_recs):
    a = pcb_recs[i]
    if a[0] == "COMPONENT":
        cid = a[1]
        comp = {"record": a, "attrs": {}, "pad_nets": []}
        j = i + 1
        while j < len(pcb_recs):
            b = pcb_recs[j]
            if b[0] == "ATTR" and len(b) >= 5 and len(b) > 2 and b[2] == cid:
                comp["attrs"][b[3]] = str(b[4])[:60]
                j += 1
            elif b[0] == "PAD_NET":
                comp["pad_nets"].append(b)
                j += 1
            else:
                break
        pcb_comps.append(comp)
        i = j
    else:
        i += 1

print(f"PCB 组件数: {len(pcb_comps)}")
for c in pcb_comps[:3]:
    print(f"  record: {json.dumps(c['record'], ensure_ascii=False)[:200]}")
    if c["pad_nets"]:
        print(f"  pad_nets: {json.dumps(c['pad_nets'][:2], ensure_ascii=False)[:200]}")

# ════════════════════════════════
# 3) 对比：找映射键候选
# ════════════════════════════════
print("\n== 3) 映射键候选 ==")

# SCH 侧的标识符
sch_keys = set()
for c in sch_comps:
    for k, v in c["attrs"].items():
        if /unique|uuid|id/i.search(k):
            sch_keys.add(f"{k}={v[:30]}")
        # Designator 也是
        if k == "Designator":
            sch_keys.add(f"DESIG={v}")

# PCB 侧的标识符  
pcb_keys = set()
for c in pcb_comps:
    for k, v in c["attrs"].items():
        if /unique|uuid|id/i.search(k):
            pcb_keys.add(f"{k}={v[:30]}")
        if k == "Designator":
            pcb_keys.add(f"DESIG={v}")
