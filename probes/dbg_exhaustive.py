"""新版 .eprj2 全表穷举：确认是否存在 history_data 以外的内容存储。"""
import io, sys, sqlite3, json, base64
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)

# ① 全部表及行数（含系统表）
print("== 全部表行数 ==")
all_tables = sorted(r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"))
nonempty = []
for t in all_tables:
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        status = f"{n} 行" if n else "(空)"
        print(f"  {t}: {status}")
        if n:
            nonempty.append(t)
    except Exception as e:
        print(f"  {t}: ERR {e}")

# ② 非空表的完整 schema 和数据采样
print("\n== 非空表详细分析 ==")
for t in nonempty:
    cols = [(r[1], r[2]) for r in conn.execute(f"PRAGMA table_info([{t}])")]
    col_names = [c[0] for c in cols]
    print(f"\n[{t}] 列: {col_names}")
    
    # 每列的最大值长度
    for cn, ct in cols:
        try:
            mx = conn.execute(
                f"SELECT MAX(LENGTH([{cn}])) FROM [{t}]").fetchone()[0]
            if mx and mx > 100:
                print(f"  {cn}: max_len={mx}")
        except Exception:
            pass
    
    # 数据样例
    rows = list(conn.execute(f"SELECT * FROM [{t}] LIMIT 3"))
    for r in rows:
        d = dict(zip(col_names, r))
        # 截断长字段
        for k, v in d.items():
            if isinstance(v, str) and len(v) > 120:
                d[k] = v[:120] + f"...({len(v)} chars)"
        print(f"  行: {json.dumps(d, ensure_ascii=False, default=str)[:300]}")

# ③ history_data 的 blob 解密后是否覆盖了全部文档类型
print("\n\n== history_data 解密后文档类型覆盖检查 ==")
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

branch_tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' "
    "AND name LIKE 'project_history_%'")]
key_map = {}
for tbl in branch_tables:
    for row in conn.execute(f"SELECT uuid, key FROM [{tbl}]"):
        if row[1]:
            key_map[row[0]] = row[1]

doc_types = {}
for buuid_full, bdata in conn.execute(
        "SELECT uuid, dataStr FROM history_data ORDER BY id"):
    if not bdata:
        continue
    buuid = buuid_full.split("-")[0]
    key_hex = key_map.get(buuid)
    if not key_hex:
        continue
    
    blob = base64.b64decode(bdata)
    iv = bytes.fromhex(buuid[:32])
    key = bytes.fromhex(key_hex)
    
    aesgcm = AESGCM(key)
    compressed = aesgcm.decrypt(iv, blob, None)
    plaintext = gzip.decompress(compressed).decode("utf-8")
    
    import re
    for m in re.finditer(r'"docType":\s*"?(\w+)"?', plaintext):
        dt = m.group(1)
        doc_types[dt] = doc_types.get(dt, 0) + 1

print("解密后的 docType 分布:", json.dumps(doc_types, indent=1))

conn.close()
