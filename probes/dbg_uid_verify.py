"""全面核实 Unique ID 跨 SCH↔PCB 映射：多页/多板/匹配率/边界情况。"""
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

# ① 列出全部文档
docs_list = list(conn.execute(
    "SELECT uuid, title, docType FROM documents ORDER BY docType, title"))
sch_docs = [(u,t) for u,t,dt in docs_list if dt==1]
pcb_docs = [(u,t) for u,t,dt in docs_list if dt==3]
print(f"SCH 页数: {len(sch_docs)}, PCB 页数: {len(pcb_docs)}")

# ② 逐文档提取 (UniqueID → Designator) 映射
def extract_uid_desig(text):
    """从 epru 文本提取 UniqueID→Designator 映射。"""
    result = {}   # uid → designator
    desig_to_uid = {}
    
    # 方法1: 从 ATTR 记录提取（V2 SCH 格式）
    for ln in text.split("\n"):
        try:
            a = json.loads(ln)
        except:
            continue
        if not isinstance(a, list): continue
        
        if a[0] == "ATTR" and len(a) >= 5:
            pid, key, val = a[2], a[3], str(a[4])
            if key == "Unique ID":
                result.setdefault("_uids", set()).add(val)
                result.setdefault("_uid_map", {})[val] = pid
            elif key == "Designator":
                result.setdefault("_desigs", {})[pid] = val
    
    # 方法2: 从 COMPONENT inline attrs 提取（PCB 格式）
    for ln in text.split("\n"):
        try:
            a = json.loads(ln)
        except:
            continue
        if not isinstance(a, list) or len(a) < 8 or a[0] != "COMPONENT":
            continue
        cid = a[1]
        attrs = a[7] if isinstance(a[7], dict) else {}
        uid = attrs.get("Unique ID", "")
        
        # 从后续 ATTR 行找 Designator
        desig = None
        for ln2 in text.split("\n"):
            try:
                b = json.loads(ln2)
            except:
                continue
            if isinstance(b, list) and len(b) >= 5 and b[0] == "ATTR":
                if str(b[2]) == cid and b[3] == "Designator":
                    desig = str(b[4])
                    break
                # PCB 格式: parentId 在不同位置
                if len(b) > 3 and str(b[3]) == cid and b[4] == "Designator":
                    desig = str(b[5]) if len(b) > 5 else ""
        
        if uid and desig:
            result.setdefault("_uid_desig", {})[uid] = desig
    
    return result

# 简化方法：直接正则提取所有 UID→Designator 对
# 在同一段落中，先出现 Designator 后出现 Unique ID（或反之）
def extract_pairs(text):
    """提取 Designator↔UID 对（基于记录块分析）。"""
    pairs = {}   # uid → designator
    lines = text.split("\n")
    
    # 收集全部 ATTR 行，按 parentId 分组
    attr_by_parent = collections.defaultdict(dict)
    comp_uids = {}   # cid → uid（从 inline attrs）
    
    for ln in lines:
        try:
            a = json.loads(ln)
        except:
            continue
        if not isinstance(a, list): continue
        
        if a[0] == "COMPONENT" and len(a) >= 8:
            cid = a[1]
            if isinstance(a[7], dict):
                uid = a[7].get("Unique ID", "")
                if uid:
                    comp_uids[cid] = uid
        
        elif a[0] == "ATTR" and len(a) >= 5:
            # V2 SCH: [type, aid, parentId, key, value]
            # V2 PCB: [type, aid, ?, parentId, ?, x, y, key, value]
            pid = None; key = None; val = None
            
            if len(a) >= 5 and a[3] in ("Designator", "Unique ID", 
                "Name", "Device", "Supplier Part"):
                pid = a[2]; key = a[3]; val = str(a[4])
            elif len(a) >= 9 and a[7] == "Designator":
                pid = a[3]; key = "Designator"; val = a[8]
            
            if pid is not None and key:
                attr_by_parent[pid][key] = val
    
    # 组合：对每个有 Unique ID 的父对象，找其 Designator
    for pid, attrs in attr_by_parent.items():
        uid = attrs.get("Unique ID", "")
        desig = attrs.get("Designator", "")
        if uid:
            pairs[uid] = desig
        # 也检查 comp_uids（inline attrs 方式）
        if pid in comp_uids:
            pairs.setdefault(comp_uids[pid], desig or "")
    
    return pairs, attr_by_parent

# 逐文档解析
print("\n== 逐文档 UID↔Designator 提取 ==")
doc_data = {}
for u, title, dt in docs_list:
    if dt not in (1, 3):
        continue
    text = decompress(conn.execute(
        "SELECT dataStr FROM documents WHERE uuid=?", (u,)).fetchone()[0])
    if not text:
        continue
    
    pairs, attr_by_parent = extract_pairs(text)
    doc_data[u] = {
        "title": title, "docType": dt,
        "pairs": pairs,
        "attr_by_parent": attr_by_parent
    }

# 汇总 SCH 和 PCB 的 UID 集合
all_sch_pairs = {}   # uid → {designator, page}
all_pcb_pairs = {}

for u, dd in doc_data.items():
    for uid, desig in dd["pairs"].items():
        if not uid: continue
        entry = {"designator": desig, "page": dd["title"]}
        if dd["docType"] == 1:
            all_sch_pairs[uid] = entry
        elif dd["docType"] == 3:
            all_pcb_pairs[uid] = entry

print(f"\nSCH UID总数: {len(all_sch_pairs)}")
print(f"PCB UID总数: {len(all_pcb_pairs)}")

# 交集分析
common_uids = set(all_sch_pairs.keys()) & set(all_pcb_pairs.keys())
only_sch = set(all_sch_pairs.keys()) - common_uids
only_pcb = set(all_pcb_pairs.keys()) - common_uids

print(f"UID 交集: {len(common_uids)}")
print(f"仅SCH: {len(only_sch)}, 仅PCB: {len(only_pcb)}")

# 匹配的 UID 中位号是否一致
match_same = match_diff = 0
diff_samples = []
for uid in sorted(common_uids):
    s_d = all_sch_pairs[uid]["designator"]
    p_d = all_pcb_pairs[uid]["designator"]
    if s_d == p_d:
        match_same += 1
    else:
        match_diff += 1
        diff_samples.append((uid, s_d, p_d))

print(f"\n匹配 UID 的位号对比:")
print(f"  位号相同: {match_same}")
print(f"  位号不同: {match_diff}")
if diff_samples:
    print("  差异样例:")
    for uid, sd, pd in diff_samples[:10]:
        print(f"    {uid[:16]}: SCH={sd} vs PCB={pd}")

conn.close()
