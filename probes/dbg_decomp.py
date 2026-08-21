import io, sys, sqlite3, base64, zlib, bz2, lzma, gzip
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
raw = base64.b64decode(conn.execute(
    "SELECT dataStr FROM history_data").fetchone()[0])
print("blob:", len(raw), "头:", raw[:12].hex())

for name, fn in (("lzma-xz", lambda d: lzma.decompress(d)),
                 ("lzma-raw-alone", lambda d: lzma.LZMADecompressor(
                     format=lzma.FORMAT_ALONE).decompress(d)),
                 ("bz2", lambda d: bz2.decompress(d)),
                 ("auto", lambda d: lzma.decompress(d, format=lzma.FORMAT_AUTO))):
    try:
        out = fn(raw)
        print(f"{name}: 成功 {len(out)} 字节 头: {out[:120]!r}")
        break
    except Exception as e:
        print(f"{name}: {str(e)[:60]}")

# 分段 raw-deflate 扫描（每偏移尝试，找可解压流）
print("\n分段 deflate 扫描（前 5000 偏移采样）:")
found = 0
for off in range(0, min(len(raw)-64, 200000), 97):
    try:
        d = zlib.decompressobj(-15)
        out = d.decompress(raw[off:], 400)
        if len(out) > 200:
            try:
                txt = out.decode("utf-8")
                if "DOCHEAD" in txt or "{" in txt[:5]:
                    print(f"  @{off}: 解出 {len(out)}B: {txt[:100]!r}")
                    found += 1
            except Exception:
                pass
    except Exception:
        pass
    if found >= 3:
        break
print("扫描完成, 命中:", found)
