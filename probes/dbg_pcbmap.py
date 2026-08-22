"""PCB↔原理图元器件映射关系调查。
检查 .eprj2 和 .epro2 中 PCB 文档与 SCH 文档之间的器件关联机制。"""
import io, sys, json, sqlite3, collections, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ══════════════════════════════════════
# Part A: 旧版 .eprj2（涡流 V1.0）
# ══════════════════════════════════════
E = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)

print("=" * 60)
print("Part A: 旧版 .eprj2 (涡流 V1.0)")
print("=" * 60)

tables = sorted(r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"))

# PCB 文档
pcb_docs = list(conn.execute(
    "SELECT uuid, title, display_title, schematic_uuid FROM documents WHERE docType=3"))
print(f"\nPCB 文档 (docType=3): {len(pcb_docs)}")
for u, t, dt, s in pcb_docs[:5]:
    print(f"  uuid={u[:12]} title={str(t)[:30]} sch_uuid={str(s)[:12]}")

# 原理图文档
sch_docs = list(conn.execute(
    "SELECT uuid, schematic_uuid FROM documents WHERE docType=1 LIMIT 5"))
print(f"\nSCH_PAGE 文档 (docType=1): 前5")
for u, s in sch_docs:
    print(f"  uuid={u[:12]} sch_uuid={str(s)[:12]}")

# boards 表
try:
    boards = list(conn.execute("SELECT * FROM boards"))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(boards)")]
    print(f"\nboards 表: {len(boards)} 行")
    for b in boards[:5]:
        d = dict(zip(cols, b))
        print(f"  {json.dumps(d, ensure_ascii=False)[:200]}")
except Exception as e:
    print(f"  boards err: {e}")

# 检查 PCB 文档内容中的元件
if pcb_docs:
    pu = pcb_docs[0][0]
    ds = conn.execute("SELECT dataStr FROM documents WHERE uuid=?", (pu,)).fetchone()
    if ds:
        import base64, gzip
        raw = ds[0]
        if raw.startswith("base64"):
            raw = base64.b64decode(raw[6:])
            try:
                text = gzip.decompress(raw).decode("utf-8")
            except Exception:
                text = raw.decode("utf-8", errors="replace")
        else:
            text = raw
        
        # 统计记录类型
        import collections
        kinds = collections.Counter()
        for ln in text.split("\n"):
            try:
                a = json.loads(ln)
                if isinstance(a, list):
                    kinds[a[0]] += 1
            except:
                pass
        print(f"\nPCB 文档 {pu[:12]} 记录类型: {dict(kinds.most_common(15))}")
        
        # 找 COMPONENT 样例
        for ln in text.split("\n"):
            try:
                a = json.loads(ln)
                if isinstance(a, list) and a[0] == "COMPONENT":
                    print(f"  PCB COMPONENT 样例: {json.dumps(a, ensure_ascii=False)[:250]}")
                    break
            except:
                pass

conn.close()

# ══════════════════════════════════════
# Part B: 新版加密 .epro2 (Piezo)
# ══════════════════════════════════════
print("\n" + "=" * 60)
print("Part B: .epro2 (Piezo)")
print("=" * 60)

X = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro2"
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr
db = lr.Epro2DB(X)

# PCB 文档
pcbs = {}
for u, d in db._docs.items():
    if d["docType"] == "PCB":
        m = db._meta.get(u) or {}
        pcbs[u] = m
print(f"\nPCB 文档: {len(pcbs)}")

for u, m in list(pcbs.items())[:4]:
    print(f"  uuid={u[:12]} meta={json.dumps(m, ensure_ascii=False)[:180]}")

# PCB 内容采样
for u, m in list(pcbs.items())[:1]:
    lines = []
    for ln in db._iter_doc_lines(u):
        head, _, body = ln.partition("||")
        h = db._jl(head)
        if not h:
            continue
        t = h.get("type")
        lines.append(t)
    import collections
    print(f"\n  PCB {u[:12]} 记录类型: {dict(collections.Counter(lines).most_common(20))}")
    
    # 找 COMPONENT
    for ln in db._iter_doc_lines(u):
        head, _, body = ln.partition("||")
        h = db._jl(head)
        if h and h.get("type") == "COMPONENT":
            b = db._jl(body.rstrip("|"))
            if b:
                print(f"  COMPONENT 样例: id={h['id'][:14]} body={json.dumps(b, ensure_ascii=False)[:200]}")
                break

# 检查 PCB 与 SCH 的关联字段
print("\n== PCB 与 SCH 关联字段 ==")
for u, d in db._docs.items():
    if d["docType"] == "PCB":
        m = db._meta.get(u) or {}
        print(f"  PCB {u[:12]}: board={m.get('board','?')[:16]} "
              f"title={m.get('title','?')[:30]}")
