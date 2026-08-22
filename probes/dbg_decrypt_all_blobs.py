"""完整解密验证：所有 blob 的明文统计。"""
import io, sys, sqlite3, base64, json, gzip, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)

# 找分支历史表
branch_tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' "
    "AND name LIKE 'project_history_%'")]

# 构建 uuid→key 映射
key_map = {}
for tbl in branch_tables:
    for row in conn.execute(f"SELECT uuid, key FROM [{tbl}]"):
        if row[1]:
            key_map[row[0]] = row[1]

# 解密全部 blob 并统计文档类型
doc_types = {}
total_lines = 0
all_text = []

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
    compressed = aesgcm.decrypt(iv, blob[:-16] + blob[-16:], None)
    plaintext = gzip.decompress(compressed).decode("utf-8")
    all_text.append(plaintext)
    
    # 统计文档类型
    for ln in plaintext.split("\n"):
        if '"DOCHEAD"' in ln[:30]:
            body = ln.partition("||")[2].rstrip("|")
            try:
                b = json.loads(body)
                dt = b.get("docType", "?")
                doc_types[dt] = doc_types.get(dt, 0) + 1
                total_lines += 1
            except Exception:
                pass
    
    print(f"  blob {buuid[:16]}: {len(plaintext)/1e6:.1f}M chars")

conn.close()

print(f"\n总明文: {sum(len(t) for t in all_text)/1e6:.1f}M chars")
print(f"文档类型分布: {json.dumps(doc_types, indent=1)}")

# 合并保存完整解密文本
merged = "\n".join(all_text)
outp = os.path.join(
    r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes",
    "full_decrypted.epru")
with open(outp, "w", encoding="utf-8") as f:
    f.write(merged)
print(f"\n完整解密文本已保存: {outp} ({len(merged)/1e6:.1f}M chars)")
