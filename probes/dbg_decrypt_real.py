"""用破解的解密算法验证 Piezo_Driver.eprj2 的 history_data。"""
import io, sys, sqlite3, base64, json, gzip
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)

# 读 project_histories 表的 key
cols = [r[1] for r in conn.execute("PRAGMA table_info(project_histories)")]
print("project_histories 列:", cols)
rows = list(conn.execute("SELECT * FROM project_histories"))
for r in rows[:3]:
    d = dict(zip(cols, r))
    print(f"  hist={d.get('uuid','?')[:16]} key={str(d.get('key',''))[:32]}...")

# 读 history_data blobs
blobs = list(conn.execute(
    "SELECT uuid, dataStr FROM history_data ORDER BY id"))
print(f"\nhistory_data: {len(blobs)} 行")

for buuid, ds in blobs:
    if not ds:
        continue
    blob = base64.b64decode(ds)
    # 找对应的 key（从 project_histories）
    key_hex = None
    for r in rows:
        d = dict(zip(cols, r))
        if d.get("uuid") == buuid or d.get("uuid", "").startswith(buuid.split("-")[0]):
            key_hex = d.get("key")
            break
    # 也尝试所有 key
    keys_to_try = []
    for r in rows:
        d = dict(zip(cols, r))
        k = d.get("key")
        if k:
            keys_to_try.append((d.get("uuid"), k))

    for ku, kh in keys_to_try:
        try:
            key = bytes.fromhex(kh)
            iv = bytes.fromhex(buuid)  # history_data.uuid 就是 IV
            aesgcm = AESGCM(key)
            # 最后 16 字节是 auth tag
            ct = blob[:-16]
            tag = blob[-16:]
            plaintext = aesgcm.decrypt(iv, ct + tag, None)
            # gunzip
            out = gzip.decompress(plaintext).decode("utf-8")
            print(f"\n✓ 解密成功! uuid={buuid[:20]} key={ku[:16]}")
            print(f"  明文长度: {len(out)} 字符, 头200:")
            print(f"  {out[:200]}")
            break
        except Exception as e:
            pass
    else:
        print(f"\n✗ blob {buuid[:20]} 所有 key 均解密失败")
