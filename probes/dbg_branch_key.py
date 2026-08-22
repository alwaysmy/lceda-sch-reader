"""检查分支特定的 project_history 表——密钥可能在这里！"""
import io, sys, sqlite3, base64, json, gzip
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)

# 分支特定表
tbl = "project_history_e42bedd6a9cd40529fb1345cce0e46f2"
cols = [r[1] for r in conn.execute(f"PRAGMA table_info([{tbl}])")]
print(f"{tbl} 列:", cols)
rows = list(conn.execute(f"SELECT * FROM [{tbl}]"))
for r in rows:
    d = dict(zip(cols, r))
    print(f"\n  行:")
    for k, v in d.items():
        val = str(v)[:60] if v else str(v)
        print(f"    {k}: {val}")

# 提取 key
keys = []
for r in rows:
    d = dict(zip(cols, r))
    if d.get("key"):
        keys.append((d.get("uuid"), d["key"]))
        
print(f"\n提取到 {len(keys)} 个 key")

# 读 blob 并尝试解密
hd = list(conn.execute("SELECT uuid, dataStr FROM history_data ORDER BY id"))

for buuid, bdata in hd:
    if not bdata:
        continue
    blob = base64.b64decode(bdata)
    ct = blob[:-16]
    tag = blob[-16:]
    
    for ku, kh in keys:
        for iv_src, iv_name in [
            (buuid.split("-")[0], "blob_uuid_nosuffix"),
            (buuid, "blob_uuid_full"),
            (ku, "key_uuid"),
        ]:
            try:
                key = bytes.fromhex(kh)
                iv = bytes.fromhex(iv_src[:32])
                if len(key) != 16 or len(iv) < 12:
                    continue
                aesgcm = AESGCM(key)
                pt = aesgcm.decrypt(iv[:12], ct + tag, None)
                out = gzip.decompress(pt).decode("utf-8")
                print(f"\n{'='*60}")
                print(f"✓✓✓ 解密成功!")
                print(f"  blob_uuid={buuid[:24]}")
                print(f"  key={kh[:32]} (from {ku[:16]})")
                print(f"  iv={iv_src[:32]} ({iv_name})")
                print(f"  明文 {len(out)} chars:")
                print(f"  头300: {out[:300]}")
                break
            except Exception:
                pass
        if success := False:
            break
