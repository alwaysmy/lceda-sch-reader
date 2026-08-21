"""假设验证：blob = 长度前缀 + deflate 块 的容器。"""
import io, sys, sqlite3, base64, zlib, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
raw = base64.b64decode(conn.execute(
    "SELECT dataStr FROM history_data").fetchone()[0])
print("总长:", len(raw))

# 尝试1: [u32 len][zlib/deflate data] 序列
for off in range(0, 64):
    for fmt in ("<I", ">I"):
        (ln,) = struct.unpack(fmt, raw[off:off+4])
        if 1000 < ln < len(raw):
            for wbits in (15, -15, 47):
                try:
                    out = zlib.decompressobj(wbits).decompress(
                        raw[off+4:off+4+ln])
                    if len(out) > 500:
                        print(f"  @{off} {fmt} wbits={wbits} len={ln} "
                              f"-> {len(out)}B: {out[:80]!r}")
                        break
                except Exception:
                    pass

# 尝试2: 整体 = XOR 某单字节后为 gzip (1f 8b)?
for k in range(256):
    if (raw[0] ^ k, raw[1] ^ k) == (0x1f, 0x8b):
        print(f"单字节 XOR key={k:#x} → gzip!")

# 尝试3: 头部可能是 [u32 magic][u32 version]... 后跟 deflate
# 暴力扫描所有偏移的 raw-deflate 起始（限制范围）
hits = 0
d = zlib.decompressobj(-15)
for off in range(0, min(2000, len(raw))):
    try:
        dd = zlib.decompressobj(-15)
        out = dd.decompress(raw[off:], 64)
        if len(out) >= 64:
            print(f"raw-deflate @{off}: {out[:64]!r}")
            hits += 1
            if hits >= 3:
                break
    except Exception:
        pass
print("扫描完成")
