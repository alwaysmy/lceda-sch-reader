import sqlite3, json, base64, gzip, zlib

conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
row = cur.execute("SELECT dataStr FROM documents WHERE display_title='高速AD' LIMIT 1").fetchone()
ds = row[0]
s = ds[6:] if ds.startswith('base64') else ds
data = base64.b64decode(s)
print("magic:", data[:4])
for name, fn in [("gzip", gzip.decompress), ("zlib", zlib.decompress)]:
    try:
        r = fn(data)
        print(name, "ok, len", len(r))
        print(r[:500])
        break
    except Exception as e:
        print(name, "fail", e)
