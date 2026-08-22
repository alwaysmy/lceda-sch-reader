import io, sys, json, sqlite3, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
cur = conn.cursor()

print("== 1) 全部表结构 ==")
for (name, sql) in cur.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table'"):
    print(f"[{name}]")
    print("  ", (sql or "").replace("\n", " ")[:220])

print("\n== 2) 全库搜 reuse/cbb 关键字（表名列名） ==")
for (name, sql) in cur.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table'"):
    s = (sql or "").lower()
    if "reuse" in s or "cbb" in s or "block" in s:
        print(f"  表 {name} 命中关键字")

print("\n== 3) documents 表结构与 docType 分布 ==")
cols = [r[1] for r in cur.execute("PRAGMA table_info(documents)")]
print("  列:", cols)
for row in cur.execute("SELECT docType, COUNT(*) FROM documents GROUP BY docType"):
    print("  docType", row)

print("\n== 4) 找 quadPizeoDriver_RevA::Power 页，dump CBB1 实例全部记录 ==")
row = cur.execute(
    "SELECT uuid, dataStr FROM documents WHERE display_title=?",
    ("quadPizeoDriver_RevA::Power",)).fetchone()
if row is None:
    # eprj2 的标题可能不带板名前缀，模糊找
    rows = list(cur.execute(
        "SELECT uuid, display_title FROM documents WHERE docType=1"))
    cands = [r for r in rows if "Power" in (r[1] or "")]
    print("  候选页:", [(r[0][:8], r[1]) for r in cands][:10])
    tgt = [r for r in rows if (r[1] or "") == "Power"]
    row = cur.execute(
        "SELECT uuid, dataStr FROM documents WHERE uuid=?",
        (tgt[0][0],)).fetchone() if tgt else None
if row:
    import lceda_reader as lr
    sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
    text = lr.LcedaDB.decompress(row[1])
    cid = None
    recs = []
    for ln in text.splitlines():
        try:
            a = json.loads(ln)
        except Exception:
            continue
        recs.append(a)
        if isinstance(a, list) and len(a) >= 5 and a[0] == "ATTR" and \
                a[3] == "Designator" and str(a[4]) == "CBB1":
            cid = a[2]
    print("  CBB1 cid =", cid)
    for a in recs:
        if isinstance(a, list) and len(a) > 2 and a[2] == cid:
            print("  ", json.dumps(a, ensure_ascii=False)[:260])
    # COMPONENT 记录本身
    for a in recs:
        if isinstance(a, list) and a[0] == "COMPONENT" and cid and a[1] == cid:
            print("  COMPONENT:", json.dumps(a, ensure_ascii=False)[:260])

print("\n== 5) attributes 表 key 分布（找 reuse 类键） ==")
keys = {}
for (k,) in cur.execute("SELECT DISTINCT key FROM attributes"):
    keys[k] = keys.get(k, 0) + 1
reuse_keys = [k for k in keys if k and ("reuse" in k.lower() or "cbb" in k.lower()
                                        or "block" in k.lower())]
print("  reuse/cbb/block 相关键:", reuse_keys)

print("\n== 6) components 表 HEAD/symbolType=17 符号，看有无模板引用字段 ==")
r = cur.execute(
    "SELECT uuid, dataStr FROM components WHERE dataStr LIKE '%\"symbolType\":17%' "
    "OR dataStr LIKE '%symbolType%17%' LIMIT 3").fetchall()
import lceda_reader as lr
for uuid, ds in r:
    text = lr.LcedaDB.decompress(ds)
    print(f"  symbol {uuid[:12]}:")
    for ln in text.splitlines():
        if '"HEAD"' in ln or '"ATTR"' in ln and (
                "reuse" in ln.lower() or "block" in ln.lower()):
            print("   ", ln[:200])
