"""PCB 解析验证 + SCH↔PCB UID 映射 + Designator 交叉核对。"""
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

pcb_u = conn.execute(
    "SELECT uuid FROM documents WHERE docType=3 ORDER BY length(dataStr) DESC LIMIT 1"
).fetchone()[0]
sch_u = conn.execute(
    "SELECT uuid FROM documents WHERE docType=1 ORDER BY length(dataStr) DESC LIMIT 1"
).fetchone()[0]

pcb_text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (pcb_u,)).fetchone()[0])
sch_text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (sch_u,)).fetchone()[0])

print(f"PCB: {pcb_u[:16]} ({len(pcb_text)} chars)")
print(f"SCH: {sch_u[:16]} ({len(sch_text)} chars)")

# ════════════ PCB 解析 ════════════
pcb_recs = []
for ln in pcb_text.split("\n"):
    try:
        a = json.loads(ln)
        if isinstance(a, list): pcb_recs.append(a)
    except: pass

kinds = collections.Counter(r[0] for r in pcb_recs if isinstance(r, list))
print(f"\nPCB 记录类型: {dict(kinds.most_common(15))}")

# COMPONENT
pcb_comps = {}   # cid → dict
for r in pcb_recs:
    if not isinstance(r, list) or len(r) < 8 or r[0] != "COMPONENT":
        continue
    cid = str(r[1])
    comp = {
        "cid": cid,
        "layer": r[2],
        "x": r[3], "y": r[4], "rot": r[5],
        "uid": "",
        "designator": "",
        "value": "",
        "device": "",
    }
    # inline attrs
    if isinstance(r[7], dict):
        comp["uid"] = r[7].get("Unique ID", "")
    pcb_comps[cid] = comp

# ATTR 补充（PCB ATTR 格式不同，需要适配）
for r in pcb_recs:
    if not isinstance(r, list) or len(r) < 9 or r[0] != "ATTR":
        continue
    # 尝试多种字段位置找 parentId 和 key/value
    # V2 PCB ATTR 可能是: [type, id, ?, parentId, ?, x, y, key, value]
    cid_candidate = None
    key = None; val = None
    
    for idx in range(2, min(8, len(r))):
        v = str(r[idx]) if r[idx] is not None else ""
        if v in pcb_comps:
            cid_candidate = v
    
    for jdx in range(5, min(len(r), 12)):
        v = str(r[jdx]) if r[jdx] is not None else ""
        if v == "Designator":
            key = "Designator"
            if jdx+1 < len(r):
                val = str(r[jdx+1])
            break
    
    if cid_candidate and key and val:
        if cid_candidate in pcb_comps:
            if key == "Designator":
                pcb_comps[cid_candidate]["designator"] = val

with_desig = [c for c in pcb_comps.values() if c["designator"]]
print(f"\nPCB 元件总数: {len(pcb_comps)}, 有位号: {len(with_desig)}")

by_prefix = collections.defaultdict(list)
for c in sorted(with_desig, key=lambda x: x["designator"]):
    d = c["designator"]
    pfx = re.match(r'([A-Za-z]+)', d)
    if pfx:
        by_prefix[pfx.group(1)].append(d)

for pfx in sorted(by_prefix):
    print(f"  {pfx}: {len(by_prefix[pfx])} 个 — {by_prefix[pfx][:4]}")

# NET 记录
net_count = sum(1 for r in pcb_recs if isinstance(r, list) and len(r)>=2 and r[0]=="NET")
print(f"\nPCB NET 数: {net_count}")

# PAD_NET 记录
pad_net_count = sum(1 for r in pcb_recs if isinstance(r, list) and len(r)>=3 and r[0]=="PAD_NET")
print(f"PCB PAD_NET 数: {pad_net_count}")

# ════════════ SCH 解析 ════════════
sch_recs = []
for ln in sch_text.split("\n"):
    try:
        a = json.loads(ln)
        if isinstance(a, list): sch_recs.append(a)
    except: pass

sch_uid_desig = {}
sch_comp_by_cid = {}

for i, r in enumerate(sch_recs):
    if not isinstance(r, list): continue
    if r[0] == "COMPONENT":
        cid = r[1]
        sch_comp_by_cid[cid] = {"title": r[2] if len(r)>2 else "", 
                                "designator": "", "uid": ""}
    elif r[0] == "ATTR" and len(r) >= 5:
        pid = r[2]; key = r[3]; val = str(r[4]) if r[4] else ""
        if pid in sch_comp_by_cid:
            if key == "Designator":
                sch_comp_by_cid[pid]["designator"] = val
            elif key == "Unique ID":
                sch_comp_by_cid[pid]["uid"] = val

sch_uid_desig = {}
for cid, info in sch_comp_by_cid.items():
    uid = info.get("uid")
    desig = info.get("designator")
    if uid and desig:
        sch_uid_desig[uid] = desig

print(f"\nSCH UID→Designator 映射数: {len(sch_uid_desig)}")

# ════════════ PCB UID 提取（从 inline attrs） ════════════
pcb_uids = set()
for c in pcb_comps.values():
    if c["uid"]:
        pcb_uids.add(c["uid"])

sch_uids = set(sch_uid_desig.keys())
overlap_uids = pcb_uids & sch_uids

print(f"\n== PCB↔SCH UID 映射 ==")
print(f"PCB UID: {len(pcb_uids)}, SCH UID: {len(sch_uids)}, 交集: {len(overlap_uids)}")

# ════════════ Designator 交叉 ════════════
pcb_desig_set = {c["designator"] for c in pcb_comps.values() if c["designator"]}
sch_desig_set = set(sch_uid_desig.values())

des_overlap = pcb_desig_set & sch_desig_set
only_pcb_des = pcb_desig_set - sch_desig_set
only_sch_des = sch_desig_set - pcb_desig_set

print(f"\n== Designator 匹配 ==")
print(f"PCB 位号: {len(pcb_desig_set)}, SCH 位号: {len(sch_desig_set)}, 交集: {len(des_overlap)}")
print(f"仅PCB: {len(only_pcb_des)}, 仅SCH: {len(only_sch_des)}")

# 输出交集样例
if des_overlap:
    print(f"匹配样例: {sorted(des_overlap)[:10]}")
