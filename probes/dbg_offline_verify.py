"""新版加密 .eprj2 完整独立解密验证——不依赖 LCEDA 运行。
从 SQLite 直接读取 → AES-128-GCM 解密 → gzip 解压 → V3 epru 明文。"""
import io, sys, sqlite3, base64, json, gzip, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)

# Step 1: 找分支历史表获取密钥
branch_tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' "
    "AND name LIKE 'project_history_%'")]
key_map = {}
for tbl in branch_tables:
    for row in conn.execute(f"SELECT uuid, key FROM [{tbl}]"):
        if row[1]:
            key_map[row[0]] = row[1]

# Step 2: 解密全部 blob
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
    compressed = aesgcm.decrypt(iv, blob, None)  # 整个 blob 含 tag
    plaintext = gzip.decompress(compressed).decode("utf-8")
    all_text.append(plaintext)

conn.close()
merged = "\n".join(all_text)

# Step 3: 验证内容完整性
doc_count = sum(1 for ln in merged.split("\n") if '"DOCHEAD"' in ln[:30])
print(f"解密完成: {len(merged)/1e6:.1f}M chars, {doc_count} 个 DOCHEAD")

# Step 4: 打包为 .epro2 让 Epro2DB 读取
import zipfile
stem = os.path.splitext(os.path.basename(E))[0]
outpath = os.path.join(os.path.dirname(E), stem + "_offline.epro2")
with zipfile.ZipFile(outpath, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("project2.json", json.dumps({"title": stem}))
    zf.writestr(stem + ".epru", merged)
print(f"打包: {outpath}")

# Step 5: 用工具读取验证
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr
db = lr.Epro2DB(outpath)
sheets = [s for s in db.sheets() if s[3] == 1]
print(f"\nEpro2DB 验证: {len(sheets)} 页, {len(db._boards)} 板")

# 统计元件
ncomp = 0
for u, t, s, dt in sheets:
    sh = lr.parse_sheet(db, u)
    if sh:
        ncomp += len(sh["components"])
print(f"总元件数: {ncomp}")
