"""深入解析 PCB 文档：COMPONENT 结构、Designator 存储位置、与 SCH 映射。"""
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

# 取第一个有内容的 PCB
pcb_u = conn.execute(
    "SELECT uuid FROM documents WHERE docType=3 LIMIT 1").fetchone()[0]
pcb_text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (pcb_u,)).fetchone()[0])

recs = []
for ln in pcb_text.split("\n"):
    try:
        a = json.loads(ln)
        if isinstance(a, list): recs.append(a)
    except: pass

# ① 全部记录类型统计
kinds = collections.Counter(r[0] for r in recs if isinstance(r, list))
print(f"PCB 记录类型分布 ({len(recs)} 条):")
for k, v in kinds.most_common(20):
    print(f"  {k}: {v}")

# ② COMPONENT 完整 dump（前5个，不截断 attrs）
print("\n== PCB COMPONENT 前5个（完整 JSON） ==")
count = 0
for r in recs:
    if isinstance(r, list) and r and r[0] == "COMPONENT":
        print(json.dumps(r, ensure_ascii=False))
        count += 1
        if count >= 5:
            break

# ③ ATTR 记录的 parentId 分布——看哪些挂在 COMPONENT 上
print("\n== ATTR key 分布 ==")
attr_keys = collections.Counter()
for r in recs:
    if isinstance(r, list) and len(r) >= 5 and r[0] == "ATTR":
        attr_keys[r[3]] += 1
for k, v in attr_keys.most_common(20):
    print(f"  {k}: {v}")

# ④ 找 Designator 属性
print("\n== 含 Designator 的记录 ==")
count = 0
for r in recs:
    if not isinstance(r, list): continue
    s = json.dumps(r, ensure_ascii=False)
    if '"Designator"' in s:
        count += 1
        if count <= 5:
            print(f"  {s[:250]}")
print(f"总计: {count} 条含 Designator 的记录")

# ⑤ 检查 COMPONENT 的 inline attrs dict（index 7）
print("\n== COMPONENT index=7 (inline attrs dict) 非空的 ==")
count = 0
for r in recs:
    if isinstance(r, list) and len(r) >= 8 and r[0] == "COMPONENT":
        attrs = r[7]
        if isinstance(attrs, dict) and attrs:
            count += 1
            if count <= 5:
                print(f"  id={r[1]}: {json.dumps(attrs, ensure_ascii=False)[:200]}")
print(f"总计: {count} 个 COMPONENT 有非空 inline attrs")

conn.close()
