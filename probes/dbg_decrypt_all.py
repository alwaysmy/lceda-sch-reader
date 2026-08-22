"""穷举解密：多种 key/iv 组合 + 编码变体。"""
import io, sys, sqlite3, base64, json, gzip
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)

# 读全部相关表
ph_cols = [r[1] for r in conn.execute("PRAGMA table_info(project_histories)")]
ph_rows = list(conn.execute("SELECT * FROM project_histories"))
hd_rows = list(conn.execute("SELECT uuid, history_uuid, dataStr FROM history_data"))

print("project_histories:")
for r in ph_rows:
    d = dict(zip(ph_cols, r))
    print(f"  uuid={d['uuid'][:24]} key={str(d['key'])[:32]} "
          f"parent={str(d['parent'])[:20]}")

print(f"\nhistory_data ({len(hd_rows)} 行):")
for u, hu, ds in hd_rows:
    print(f"  uuid={u[:28]} hist_uuid={hu[:20] if hu else 'None'} "
          f"data_len={len(ds) if ds else 0}")

# 收集所有可能的 key（hex 字符串）
all_keys = set()
for r in ph_rows:
    d = dict(zip(ph_cols, r))
    k = d.get("key")
    if k and isinstance(k, str) and len(k) >= 32:
        all_keys.add(k)
        # 也尝试前32字符（16字节）
        all_keys.add(k[:32])

# 收集所有可能的 IV 来源
all_ivs = set()
for u, hu, ds in hd_rows:
    if u:
        clean = u.split("-")[0]  # 去掉 -1 后缀
        if len(clean) >= 32:
            all_ivs.add(clean[:32])  # 前 16 字节
        if len(clean) >= 16:
            all_ivs.add(clean)  # 全部

# 加上 project UUID 和 branch UUID 作为候选
proj_uuid = conn.execute("SELECT uuid FROM projects").fetchone()[0]
all_keys.add(proj_uuid[:32])
branch = conn.execute("SELECT branch_uuid FROM projects").fetchone()
if branch and branch[0]:
    all_keys.add(branch[0][:32])

conn.close()

print(f"\n候选 key 数: {len(all_keys)}, 候选 IV 数: {len(all_ivs)}")

# 尝试解密第一个大 blob
blob_b64 = hd_rows[0][2]
blob = base64.b64decode(blob_b64)
ct = blob[:-16]
tag = blob[-16:]
print(f"blob: {len(blob)}B, ct={len(ct)}B, tag={len(tag)}B")

success = False
for kh in all_keys:
    try:
        key = bytes.fromhex(kh)
        if len(key) != 16:
            continue
        for ivh in all_ivs:
            try:
                iv = bytes.fromhex(ivh)
                if len(iv) != 12 and len(iv) != 16:
                    continue
                aesgcm = AESGCM(key)
                pt = aesgcm.decrypt(iv, ct + tag, None)
                out = gzip.decompress(pt).decode("utf-8")
                print(f"\n✓✓✓ 解密成功!")
                print(f"  key={kh[:32]} iv={ivh[:32]}")
                print(f"  明文 {len(out)} chars, 头200: {out[:200]}")
                success = True
                break
            except Exception:
                pass
            # 也试 12 字节 IV（GCM 标准 nonce 长度）
            try:
                iv = bytes.fromhex(ivh)[:12]
                aesgcm = AESGCM(key)
                pt = aesgcm.decrypt(iv, ct + tag, None)
                out = gzip.decompress(pt).decode("utf-8")
                print(f"\n✓✓✓ 解密成功(12B IV)!")
                print(f"  key={kh[:32]} iv={ivh[:24]}")
                print(f"  明文 {len(out)} chars, 头200: {out[:200]}")
                success = True
                break
            except Exception:
                pass
        if success:
            break
    except Exception:
        pass

if not success:
    print("\n所有组合均失败")
    # 打印更多调试信息
    print("\nkey 样例:")
    for k in list(all_keys)[:5]:
        print(f"  '{k[:40]}' (len={len(k)})")
    print("\nIV 样例:")
    for v in list(all_ivs)[:5]:
        print(f"  '{v[:40]}' (len={len(v)})")
