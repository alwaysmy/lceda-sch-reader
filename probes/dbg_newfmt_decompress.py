import io, sys, sqlite3, base64, zlib, gzip
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
row = conn.execute("SELECT dataStr FROM history_data LIMIT 1").fetchone()
raw = base64.b64decode(row[0])
print("长度:", len(raw), "头16:", raw[:16].hex())

tries = {
    "raw-deflate": lambda d: zlib.decompressobj(-15).decompress(d),
    "zlib": lambda d: zlib.decompress(d),
    "gzip": lambda d: gzip.decompress(d),
}
for name, fn in tries.items():
    try:
        out = fn(raw)
        print(f"{name}: 解压成功! {len(out)} 字节，头200:")
        print(out[:200])
        break
    except Exception as e:
        print(f"{name}: 失败 {str(e)[:60]}")
