"""用户在 LCEDA 中对 CBB6 做了位号分配，重新读取 .eprj2 对比变化。
重点：找出分配后的位号存储位置。"""
import io, sys, sqlite3, json, base64, gzip
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)

# ① 基本状态
tables_with_data = []
for t in sorted(r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")):
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        if n:
            tables_with_data.append(f"{t}={n}")
    except Exception:
        pass
print("有数据的表:", ", ".join(tables_with_data))

# ② project_history 表的 key
for tbl in [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name LIKE 'project_history_%'")]:
    print(f"\n== {tbl} ==")
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info([{tbl}])")]
    for row in conn.execute(f"SELECT * FROM [{tbl}]"):
        d = dict(zip(cols, row))
        print(f"  uuid={str(d.get('uuid',''))[:20]} key={str(d.get('key',''))[:32]}")

# ③ history_data 行数与大小
print("\n== history_data ==")
for row in conn.execute("SELECT uuid, length(dataStr) FROM history_data ORDER BY id"):
    print(f"  {row[0][:24]}: {row[1]} bytes")

# ④ project_structures 行数
try:
    n = conn.execute("SELECT COUNT(*) FROM project_structures").fetchone()[0]
    print(f"project_structures: {n} 行")
except Exception:
    pass

# ⑤ 解密全部 blob 并搜 CBB 相关内容
branch_tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' "
    "AND name LIKE 'project_history_%'")]
key_map = {}
for tbl in branch_tables:
    for row in conn.execute(f"SELECT uuid, key FROM [{tbl}]"):
        if row[1]:
            key_map[row[0]] = row[1]

all_text = []
for buuid_full, bdata in conn.execute(
        "SELECT uuid, dataStr FROM history_data ORDER BY id"):
    if not bdata:
        continue
    buuid = buuid_full.split("-")[0]
    key_hex = key_map.get(buuid)
    if not key_hex:
        # 尝试所有 key
        for kh in key_map.values():
            try:
                blob = base64.b64decode(bdata)
                iv = bytes.fromhex(buuid[:32])
                key = bytes.fromhex(kh)
                aesgcm = AESGCM(key)
                compressed = aesgcm.decrypt(iv, blob, None)
                plaintext = gzip.decompress(compressed).decode("utf-8")
                all_text.append(plaintext)
                break
            except Exception:
                continue
        continue
    
    blob = base64.b64decode(bdata)
    iv = bytes.fromhex(buuid[:32])
    key = bytes.fromhex(key_hex)
    
    try:
        aesgcm = AESGCM(key)
        compressed = aesgcm.decrypt(iv, blob, None)
        plaintext = gzip.decompress(compressed).decode("utf-8")
        all_text.append(plaintext)
    except Exception:
        # 尝试其他 key
        for kh, kv in key_map.items():
            if kh == key_hex:
                continue
            try:
                blob2 = base64.b64decode(bdata)
                iv2 = bytes.fromhex(buuid[:32])
                k2 = bytes.fromhex(kv)
                aesgcm2 = AESGCM(k2)
                compressed = aesgcm2.decrypt(iv2, blob2, None)
                plaintext = gzip.decompress(compressed).decode("utf-8")
                all_text.append(plaintext)
                break
            except Exception:
                continue

conn.close()

merged = "\n".join(all_text)
print(f"\n解密后总文本: {len(merged)/1e6:.1f}M chars")

# ⑥ 搜索 INSTANCE_ATTR 和 CBB 位号相关记录
import re
inst_attrs = list(re.finditer(r'"INSTANCE_ATTR"', merged))
print(f"INSTANCE_ATTR 出现: {len(inst_attrs)} 次")

# 搜 CBB6 相关
cbb6_hits = list(re.finditer(r'CBB6', merged))
print(f"CBB6 出现: {len(cbb6_hits)} 次")

# 搜 U2 
u2_hits = list(re.finditer(r'"U2"', merged))
print(f'"U2" 出现: {len(u2_hits)} 次')

# 提取含 U2 的 INSTANCE_ATTR 行上下文
for m in u2_hits[:5]:
    start = max(0, m.start()-200)
    seg = merged[start:m.start()+100].replace("\n", "␤")
    print(f"  @{m.start()}: ...{seg[:280]}")

# 搜 INSTANCE 文档段
print("\n== INSTANCE docType 段 ==")
for m in list(re.finditer(r'"docType":\s*"INSTANCE"', merged))[:5]:
    seg = merged[m.start():m.start()+300].replace("\n", "␤")
    print(f"  @{m.start()}: {seg[:280]}")
