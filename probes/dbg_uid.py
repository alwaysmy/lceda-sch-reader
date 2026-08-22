"""核对 PCB 与 SCH 的器件映射机制：Unique ID 是否跨文档共享。"""
import io, sys, json, sqlite3, base64, gzip, collections
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

# ① 找一个有元件的 SCH 页和一个 PCB 页
sch_uuid = conn.execute(
    "SELECT uuid FROM documents WHERE docType=1 LIMIT 1").fetchone()[0]
pcb_uuid = conn.execute(
    "SELECT uuid FROM documents WHERE docType=3 LIMIT 1").fetchone()[0]

print(f"SCH page: {sch_uuid[:16]}")
print(f"PCB page: {pcb_uuid[:16]}")

# ② 解压两页内容
sch_text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (sch_uuid,)).fetchone()[0])
pcb_text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (pcb_uuid,)).fetchone()[0])

# ③ 提取两页的 Unique ID
import re
def extract_uids(text, label):
    uids = {}
    for m in re.finditer(r'"Unique ID"\s*[,:]\s*"([^"]+)"', text):
        uid = m.group(1)
        # 找附近的 Designator
        before = text[max(0,m.start()-300):m.end()+100]
        des_m = re.search(r'"Designator"\s*[,:]\s*"([^"]+)"', before[::-1][:300][::-1])
        desig = None
        # 更好的方式：找包含此 UID 的记录块
        blk_start = text.rfind("\n[", 0, m.start())
        blk_end = text.find("\n[", m.end())
        if blk_start < 0: blk_start = 0
        if blk_end < 0: blk_end = len(text)
        block = text[blk_start:blk_end]
        
        dsg = re.findall(r'"(?:Designator|designator)"\s*[,:]\s*"([^"]+)"', block)
        if dsg:
            desig = dsg[-1]
        uids[uid] = desig or "?"
    
    print(f"\n  {label} Unique ID 数: {len(uids)}")
    for u, d in list(uids.items())[:10]:
        print(f"    {u}: {d}")
    return uids

# 简单方法：直接搜所有含 Unique ID 的行及其上下文
print("\n== SCH 页 Unique ID ==")
uid_count = len(re.findall(r'"Unique ID"', sch_text))
print(f"  出现次数: {uid_count}")
for m in list(re.finditer(r'"Unique ID"\s*,\s*"([^"]+)"', sch_text))[:6]:
    print(f"    UID: {m.group(1)}")

print("\n== PCB 页 Unique ID ==")
uid_pcb = len(re.findall(r'"Unique ID"', pcb_text))
print(f"  出现次数: {uid_pcb}")

# ④ 检查 PCB COMPONENT 的完整属性
print("\n== PCB COMPONENT 完整记录 ==")
for ln in pcb_text.split("\n"):
    try:
        a = json.loads(ln)
        if isinstance(a, list) and a[0] == "COMPONENT":
            print(json.dumps(a, ensure_ascii=False)[:400])
            break
    except:
        pass

# ⑤ 检查 SCH COMPONENT 的完整记录
print("\n== SCH COMPONENT 完整记录 ==")
count = 0
for ln in sch_text.split("\n"):
    try:
        a = json.loads(ln)
        if isinstance(a, list) and a[0] == "COMPONENT":
            print(json.dumps(a, ensure_ascii=False)[:400])
            count += 1
            if count >= 2: break
    except:
        pass

conn.close()
