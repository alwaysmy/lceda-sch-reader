"""PCB↔SCH 映射完整核对：Designator 匹配率 + PCB 独有字段。"""
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

# 取第一个 PCB 和一个 SCH 页
pcb_u = conn.execute("SELECT uuid FROM documents WHERE docType=3 LIMIT 1").fetchone()[0]
pcb_text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (pcb_u,)).fetchone()[0])

# 找一个有较多元件的 SCH 页
sch_u = None
best = 0
for row in conn.execute("SELECT uuid, length(dataStr) FROM documents WHERE docType=1"):
    txt = decompress(conn.execute(
        "SELECT dataStr FROM documents WHERE uuid=?", (row[0],)).fetchone()[0])
    n = len(re.findall(r'"Designator"', txt))
    if n > best:
        best = n
        sch_u = row[0]
if sch_u:
    sch_text = decompress(conn.execute(
        "SELECT dataStr FROM documents WHERE uuid=?", (sch_u,)).fetchone()[0])
else:
    sch_text = ""

# ═══ 解析 PCB COMPONENT + Designator ═══
pcb_comps = {}   # cid → {designator, uid, x, y, layer}
i = 0
recs_pcb = []
for ln in pcb_text.split("\n"):
    try:
        a = json.loads(ln)
        if isinstance(a, list): recs_pcb.append(a)
    except: pass

for r in recs_pcb:
    if not isinstance(r, list) or len(r) < 8 or r[0] != "COMPONENT":
        continue
    cid = r[1]
    comp = {"cid": cid, "layer": r[2], "x": r[3], "y": r[4], 
            "rot": r[5], "uid": "", "designator": ""}
    # inline attrs at index 7
    if isinstance(r[7], dict):
        comp["uid"] = r[7].get("Unique ID", "")
    pcb_comps[cid] = comp

# ATTR 记录格式（PCB）: ["ATTR", attrId, 0, compCid, 3, x, y, "Designator", "C35", ...]
for r in recs_pcb:
    if not isinstance(r, list) or len(r) < 9 or r[0] != "ATTR":
        continue
    body = r
    # Designator 在 index 7/8
    if len(body) >= 9 and body[7] == "Designator":
        target_cid = body[3]
        if target_cid in pcb_comps:
            pcb_comps[target_cid]["designator"] = body[8]

# 统计有位号的 PCB 元件
with_desig = [c for c in pcb_comps.values() if c["designator"]]
print(f"PCB 元件总数: {len(pcb_comps)}, 有位号: {len(with_desig)}")

# ═══ 解析 SCH COMPONENT + Designator ═══
# V2 SCH ATTR 格式: ["ATTR", attrId, parentId, key, value, ...]
sch_recs = []
for ln in sch_text.split("\n"):
    try:
        a = json.loads(ln)
        if isinstance(a, list): sch_recs.append(a)
    except: pass

sch_comps = {}
for i, r in enumerate(sch_recs):
    if r[0] == "COMPONENT":
        cid = r[1]
        sch_comps[cid] = {"cid": cid, "title": r[2] if len(r)>2 else "",
                          "designator": "", "uid": ""}
    elif r[0] == "ATTR" and len(r) >= 5:
        pid = r[2]
        if pid in sch_comps:
            if r[3] == "Designator":
                sch_comps[pid]["designator"] = r[4]
            elif r[3] == "Unique ID":
                sch_comps[pid]["uid"] = r[4]

with_desig_sch = [c for c in sch_comps.values() if c["designator"]]
print(f"\nSCH 元件总数: {len(sch_comps)}, 有位号: {len(with_desig_sch)}")

# ═══ 位号匹配分析 ═══
pcb_desigs = {c["designator"] for c in pcb_comps.values() if c["designator"]}
sch_desigs = {c["designator"] for c in sch_comps.values() if c["designator"]}

overlap = sch_desigs & pcb_desigs
only_sch = sch_desigs - pcb_desigs  
only_pcb = pcb_desigs - sch_desigs

print(f"\n== 位号匹配 ==")
print(f"  SCH 位号: {len(sch_desigs)}")
print(f"  PCB 位号: {len(pcb_desigs)}")
print(f"  匹配: {len(overlap)}")
print(f"  仅SCH: {len(only_sch)} — 样例: {sorted(only_sch)[:8]}")
print(f"  仅PCB: {len(only_pcb)} — 样例: {sorted(only_pcb)[:8]}")

# PCB 独有的位号可能是 PCB 布局时的辅助器件（安装孔、丝印标识等）
# 或其他板的元件混入了这个 PCB 文档

# 检查 PCB 的 PAD_NET 记录（焊盘网络归属——PCB 网络表）
pad_nets = collections.defaultdict(set)
for r in recs_pcb:
    if isinstance(r, list) and len(r) >= 5 and r[0] == "PAD_NET":
        pad_nets[r[3]].add(str(r[4])[:20])

print(f"\n== PCB PAD_NET 网络（前10） ==")
for net, pads in list(pad_nets.items())[:10]:
    print(f"  {net}: {len(pads)} 焊盘")

conn.close()
