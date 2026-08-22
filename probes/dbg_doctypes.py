import io, sys, sqlite3, base64, json, gzip, re
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
bt = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'project_history_%'")]
km = {}
for tbl in bt:
    for row in conn.execute(f"SELECT uuid, key FROM [{tbl}]"):
        if row[1]:
            km[row[0]] = row[1]
dt = {}
for buuid, bdata in conn.execute("SELECT uuid, dataStr FROM history_data ORDER BY id"):
    if not bdata:
        continue
    bu = buuid.split("-")[0]
    kh = km.get(bu)
    if not kh:
        continue
    blob = base64.b64decode(bdata)
    iv = bytes.fromhex(bu[:32])
    key = bytes.fromhex(kh)
    aes = AESGCM(key)
    comp = aes.decrypt(iv, blob, None)
    pt = gzip.decompress(comp).decode("utf-8")
    for m in re.finditer(r'"docType":\s*"?(\w+)', pt):
        dt[m.group(1)] = dt.get(m.group(1), 0) + 1
print("解密后 docType 分布:", json.dumps(dt, indent=1))
print(f"总 docType 记录: {sum(dt.values())}")
conn.close()
