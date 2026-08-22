"""完整版：SCH↔PCB 映射 + 仅SCH/仅PCB 清单。"""
import io, sys, os, json, sqlite3, base64, gzip, collections
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

all_sch = {}
all_pcb = {}

for u, title, dt in conn.execute(
        "SELECT uuid, title, docType FROM documents ORDER BY docType"):
    if dt not in (1, 3): continue
    text = decompress(conn.execute(
        "SELECT dataStr FROM documents WHERE uuid=?", (u,)).fetchone()[0])
    if not text: continue
    
    abp = {}
    for ln in text.split("\n"):
        try: a = json.loads(ln)
        except: continue
        if not isinstance(a, list): continue
        if a[0] == "COMPONENT" and len(a) >= 8:
            cid = str(a[1])
            if isinstance(a[7], dict):
                uid = a[7].get("Unique ID", "")
                if uid: abp.setdefault(cid, {})["_iu"] = uid
        elif a[0] == "ATTR" and len(a) >= 5:
            pid = a[2] if isinstance(a[2], str) else ""
            key = str(a[3]); val = str(a[4]) if a[4] is not None else ""
            if pid and key in ("Designator","Device","Unique ID","Manufacturer Part"):
                abp.setdefault(pid, {})[key] = val
            if len(a) >= 9 and isinstance(a[7], str) and a[7] in ("Designator","Device"):
                p2 = str(a[3])
                abp.setdefault(p2, {})[a[7]] = val
    
    for pid, at in abp.items():
        uid = at.get("_iu") or at.get("Unique ID")
        d = at.get("Designator")
        dev = at.get("Device") or at.get("Manufacturer Part") or ""
        if uid and d:
            entry = {"designator": d, "device": dev[:40], "page": title}
            if dt == 1: all_sch[uid] = entry
            elif dt == 3: all_pcb[uid] = entry

conn.close()

common = set(all_sch) & set(all_pcb)
only_sch = set(all_sch) - set(all_pcb)
only_pcb = set(all_pcb) - set(all_sch)

print(f"SCH UID={len(all_sch)}  PCB UID={len(all_pcb)}  交集={len(common)}")
print(f"仅SCH(未布局到PCB): {len(only_sch)}  仅PCB(SCH中无): {len(only_pcb)}")

diff = []
same = 0
for uid in sorted(common):
    s = all_sch[uid]["designator"]
    p = all_pcb[uid]["designator"]
    if s != p:
        diff.append((uid, s, p, all_sch[uid].get("device",""), 
                     all_sch[uid].get("page","")))
    else:
        same += 1

print(f"位号一致: {same}  位号不同(PCB反标): {len(diff)}")
for u, s, p, dev, pge in sorted(diff, key=lambda x: x[1]):
    dev_s = all_sch[u].get("device","") or all_pcb[u].get("device","")
    print(f"  SCH:{s:8s} → PCB:{p:8s} 器件={dev_s[:25]}")

print(f"\n仅SCH有(未布局到PCB) {len(only_sch)} 个:")
for uid in sorted(only_sch)[:15]:
    e = all_sch[uid]
    print(f"  {e['designator']:8s} {e['device'][:30]} [{e['page'][:20]}]")
