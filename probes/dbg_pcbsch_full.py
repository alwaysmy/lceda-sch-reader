"""完整输出：SCH↔PCB UID 匹配 + 位号差异清单（反标数据）。"""
import io, sys, sqlite3, base64, gzip, json, re, collections
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

# 收集全部文档的 (uid→designator, uid→device)
all_sch = {}   # uid → {designator, device, page}
all_pcb = {}

docs_list = list(conn.execute(
    "SELECT uuid, title, docType FROM documents ORDER BY docType"))

for u, title, dt in docs_list:
    if dt not in (1, 3):
        continue
    text = decompress(conn.execute(
        "SELECT dataStr FROM documents WHERE uuid=?", (u,)).fetchone()[0])
    if not text:
        continue
    
    lines = text.split("\n")
    
    # 按 parentId 收集属性
    attrs_by_pid = collections.defaultdict(dict)
    # COMPONENT inline attrs
    for ln in lines:
        try:
            a = json.loads(ln)
        except: continue
        if not isinstance(a, list): continue
        
        if a[0] == "COMPONENT" and len(a) >= 8:
            cid = str(a[1])
            if isinstance(a[7], dict):
                uid = a[7].get("Unique ID", "")
                if uid:
                    attrs_by_pid[cid]["_inline_uid"] = uid
        
        elif a[0] == "ATTR" and len(a) >= 5:
            # V2 SCH 格式: [type, aid, parentId, key, value]
            if len(a) >= 5 and isinstance(a[2], str):
                pid = a[2]
                key = a[3]
                val = str(a[4]) if a[4] is not None else ""
                if key in ("Designator", "Device", "Unique ID", 
                           "Manufacturer Part", "Name"):
                    attrs_by_pid[pid][key] = val
            
            # V2 PCB 格式: [type, aid, ?, parentId, ?, x, y, key, value]
            if len(a) >= 9 and isinstance(a[7], str) and a[7] in (
                    "Designator", "Device"):
                pid = str(a[3])
                key = a[7]
                val = str(a[8])
                attrs_by_pid[pid][key] = val
    
    for pid, attrs in attrs_by_pid.items():
        uid = attrs.get("_inline_uid") or attrs.get("Unique ID")
        desig = attrs.get("Designator")
        device = attrs.get("Device") or attrs.get("Manufacturer Part") or ""
        
        if uid and desig:
            entry = {"designator": desig, "device": device[:40], "page": title}
            if dt == 1:
                all_sch[uid] = entry
            elif dt == 3:
                all_pcb[uid] = entry

conn.close()

print(f"SCH UID 总数: {len(all_sch)}")
print(f"PCB UID 总数: {len(all_pcb)}")

common = set(all_sch) & set(all_pcb)
only_sch = set(all_sch) - set(all_pcb)
only_pcb = set(all_pcb) - set(all_sch)
print(f"交集: {len(common)}, 仅SCH: {len(only_sch)}, 仅PCB: {len(only_pcb)}")

# 分类统计
same_desig = []
diff_desig = []   # PCB 反标候选
for uid in sorted(common):
    s = all_sch[uid]["designator"]
    p = all_pcb[uid]["designator"]
    if s == p:
        same_desig.append((uid, s))
    else:
        diff_desig.append({
            "uid": uid,
            "sch_desig": s, "pcb_desig": p,
            "sch_device": all_sch[uid].get("device",""),
            "pcb_device": all_pcb[uid].get("device",""),
            "page": all_sch[uid].get("page",""),
        })

print(f"\n== 位号一致性 ==")
print(f"一致: {len(same_desig)}")
print(f"不一致(PCB反标数据): {len(diff_desig)}")

if diff_desig:
    print(f"\n== 位号不一致明细（PCB 反标映射表） ==")
    for d in sorted(diff_desig, key=lambda x: x["sch_desig"]):
        print(f"  SCH:{d['sch_desig']:8s} → PCB:{d['pcb_desig']:8s} "
              f"器件={d['sch_device'] or d['pcb_device'][:20]} 页={d['page'][:20]}")

# 仅一侧有的器件
print(f"\n== 仅SCH有(未布局到PCB) ==")
for uid in sorted(only_sch)[:15]:
    e = all_sch[uid]
    print(f"  {e['designator']:8s} {e['device'][:30]} 页={e['page'][:20]}")

print(f"\n== 仅PCB有(SCH中无对应) ==")
for uid in sorted(only_pcb)[:15]:
    e = all_pcb[uid]
    print(f"  {e['designator']:8s} {e['device'][:30]} 页={e['page'][:20]}")

# 保存为 JSON
out = {
    "matched": len(common),
    "desig_same": len(same_desig),
    "desig_diff": [{"uid":d["uid"], "sch":d["sch_desig"], "pcb":d["pcb_desig"],
                    "device":d["sch_device"]} for d in diff_desig],
    "only_sch": [{"uid":u, **all_sch[u]} for u in only_sch],
    "only_pcb": [{"uid":u, **all_pcb[u]} for u in only_pcb],
}
outp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                     "pcbsch_map.json")
with open(outp, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(f"\n已保存: {outp}")
