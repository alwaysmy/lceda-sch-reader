"""深挖 LCEDA 正向标注（原理图→PCB）的关联机制：
① SCH COMPONENT 的 Unique ID 是否出现在 PCB 的 ATTR 中
② PCB COMPONENT 的 attrs dict（index 7）中是否有指向 SCH 的字段
③ SCH 页的 COMPONENT 是否有额外的隐藏关联属性
④ 检查 .eprj2 中是否存在专门的 sch-pcb 映射表或文档"""
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

# 取一个 SCH 页和一个 PCB 页
pcb_u = conn.execute("SELECT uuid FROM documents WHERE docType=3 LIMIT 1").fetchone()[0]
sch_u = conn.execute(
    "SELECT uuid FROM documents WHERE docType=1 ORDER BY length(dataStr) DESC LIMIT 1"
).fetchone()[0]

sch_text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (sch_u,)).fetchone()[0])
pcb_text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (pcb_u,)).fetchone()[0])

# ════════════════════════════
# ① SCH COMPONENT 的 Unique ID 值列表
# ════════════════════════════
# V2 SCH ATTR: ["ATTR", aid, parentId, key, value]
sch_uid_map = {}   # Designator → Unique ID
cur_comp_desig = {}
for ln in sch_text.split("\n"):
    try:
        a = json.loads(ln)
    except: continue
    if not isinstance(a, list) or len(a) < 5: continue
    if a[0] == "ATTR":
        pid, key, val = a[2], a[3], str(a[4])
        if key == "Designator":
            cur_comp_desig[pid] = val
        elif key == "Unique ID" and pid in cur_comp_desig:
            sch_uid_map[cur_comp_desig[pid]] = val

print("== ① SCH 元件的 Unique ID (前15) ==")
for des, uid in sorted(sch_uid_map.items())[:15]:
    print(f"  {des}: {uid}")

# ════════════════════════════
# ② PCB COMPONENT + Designator + inline attrs
# ════════════════════════════
pcb_recs = []
for ln in pcb_text.split("\n"):
    try:
        a = json.loads(ln)
        if isinstance(a, list): pcb_recs.append(a)
    except: pass

pcb_uid_map = {}   # Designator → Unique ID
for r in pcb_recs:
    if not isinstance(r, list) or len(r) < 8 or r[0] != "COMPONENT": continue
    cid = r[1]
    inline = r[7] if isinstance(r[7], dict) else {}
    uid = inline.get("Unique ID", "")
    # 找对应的 Designator ATTR
    for r2 in pcb_recs:
        if isinstance(r2, list) and len(r2) >= 9 and r2[0] == "ATTR" \
           and r2[3] == cid and r2[7] == "Designator":
            pcb_uid_map[r2[8]] = uid
            break

print(f"\n== ② PCB 元件的 Unique ID (前15) ==")
for des, uid in sorted(pcb_uid_map.items())[:15]:
    print(f"  {des}: {uid}")

# ════════════════════════════
# ③ 交叉：SCH UID vs PCB UID 是否有同位号元件的 UID 匹配
# ════════════════════════════
common_desigs = set(sch_uid_map.keys()) & set(pcb_uid_map.keys())
print(f"\n== ③ 同位号元件的 UID 对比 ==")
match_count = 0
for des in sorted(common_desigs)[:20]:
    s_uid = sch_uid_map.get(des, "?")
    p_uid = pcb_uid_map.get(des, "?")
    match = "✓" if s_uid == p_uid else "✗"
    if s_uid == p_uid: match_count += 1
    print(f"  {des:8s} SCH_UID={s_uid[:16]:18s} PCB_UID={p_uid[:16]:18s} {match}")

print(f"\nUID 匹配率: {match_count}/{len(common_desigs)}")

# ════════════════════════════
# ④ 检查 .eprj2 是否有专门的映射表/文档
# ════════════════════════════
print("\n== ④ 搜含 'netflag'/'netlink'/'forward'/'annotation' 的表或记录 ==")
tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")]
for t in tables:
    if re.search(r'link|map|forward|annot|net', t, re.I):
        n = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        print(f"  表 {t}: {n} 行")

# 检查 PCB 文档内是否有 NET 记录包含 SCH 引用
print("\n== PCB NET 记录样例 ==")
pcb_recs = []
for ln in pcb_text.split("\n"):
    try:
        a = json.loads(ln)
        if isinstance(a, list): pcb_recs.append(a)
    except: pass

count = 0
for r in pcb_recs:
    if isinstance(r, list) and len(r) >= 3 and r[0] == "NET":
        count += 1
        if count <= 3:
            print(f"  NET: {json.dumps(r, ensure_ascii=False)[:300]}")
print(f"  NET 总数: {count}")

conn.close()
