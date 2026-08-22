"""用正确密钥解密 history_data blob → 明文 epru。"""
import io, sys, sqlite3, base64, json, gzip
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)

# ① 从分支特定表读 key（uuid→key 映射）
# 表名模式: project_history_<branch_uuid>
branch_tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'project_history_%'")]
print("分支历史表:", branch_tables)

key_map = {}  # uuid → hex_key
for tbl in branch_tables:
    for row in conn.execute(f"SELECT uuid, key FROM [{tbl}]"):
        if row[1]:
            key_map[row[0]] = row[1]
            print(f"  key[{row[0][:20]}] = {row[1][:32]}...")

# ② 读 blob 并解密
blobs = list(conn.execute(
    "SELECT uuid, dataStr FROM history_data ORDER BY id"))
conn.close()

for buuid_full, bdata in blobs:
    if not bdata:
        continue
    # 去掉分片后缀得到基础 uuid
    buuid = buuid_full.split("-")[0] if "-" in buuid_full else buuid_full
    
    # 找对应 key
    key_hex = key_map.get(buuid)
    if not key_hex:
        # 尝试模糊匹配
        for ku, kv in key_map.items():
            if buuid.startswith(ku[:16]):
                key_hex = kv
                break
    
    if not key_hex:
        print(f"✗ 未找到 {buuid[:24]} 的密钥")
        continue
    
    blob = base64.b64decode(bdata)
    
    # IV = 基础 uuid 的 hex → bytes（16 字节）
    iv = bytes.fromhex(buuid[:32])
    key = bytes.fromhex(key_hex)
    
    # GCM: 最后 16 字节是 auth tag
    ct = blob[:-16]
    tag = blob[-16:]
    
    try:
        aesgcm = AESGCM(key)
        compressed = aesgcm.decrypt(iv, ct + tag, None)
        plaintext = gzip.decompress(compressed).decode("utf-8")
        
        print(f"\n{'='*60}")
        print(f"✓ 解密成功! blob={buuid_full[:28]}")
        print(f"  key={key_hex[:32]}")
        print(f"  iv={buuid[:32]}")
        print(f"  明文 {len(plaintext)} chars ({len(plaintext)/1e6:.1f}M)")
        print(f"  头300字符:")
        print(f"  {plaintext[:300]}")
        print(f"  ...")
        print(f"  尾200字符:")
        print(f"  {plaintext[-200:]}")
        
        # 保存解密结果
        outp = os.path.join(
            r"D:\WorkDesigns\3_WorkTools\sch_review_tool"
            r"\lceda_sch_reader\probes",
            f"decrypted_{buuid[:12]}.epru")
        with open(outp, "w", encoding="utf-8") as f:
            f.write(plaintext)
        print(f"  已保存: {outp}")
        
    except Exception as e:
        print(f"\n✗ 解密失败 {buuid_full[:28]}: {type(e).__name__}: {str(e)[:100]}")
        # 调试：尝试不同 IV 长度
        for iv_len in (12, 16):
            try:
                iv_short = bytes.fromhex(buuid[:iv_len*2])
                aesgcm = AESGCM(key)
                pt = aesgcm.decrypt(iv_short, ct + tag, None)
                out = gzip.decompress(pt).decode("utf-8")
                print(f"  ✓ 用 {iv_len}B IV 成功! {out[:100]}")
                break
            except Exception:
                pass
