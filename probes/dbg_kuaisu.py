import io, sys, sqlite3, base64, gzip
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
FQ = r"C:\Users\dell\Documents\LCEDA-Pro\example-projects\示例工程_快速入门.eprj2"
conn = sqlite3.connect(f"file:{FQ}?mode=ro", uri=True)
rows = list(conn.execute(
    "SELECT uuid, docType, length(dataStr), substr(dataStr,1,40) "
    "FROM documents"))
for u, dt, ln, head in rows:
    print(f"doc {u[:12]} docType={dt} len={ln} head={head!r}")
ds = conn.execute(
    "SELECT dataStr FROM documents WHERE docType=1").fetchone()[0]
if ds:
    raw = base64.b64decode(ds[6:]) if ds.startswith("base64") else None
    if raw is not None:
        print("解码后前8字节:", raw[:8].hex(), "| gzip?", raw[:2] == b"\x1f\x8b")
        try:
            txt = gzip.decompress(raw).decode("utf-8")
            print("gzip 解压 OK，前 300 字符:")
            print(txt[:300])
        except Exception as e:
            print("gzip 失败:", e)
