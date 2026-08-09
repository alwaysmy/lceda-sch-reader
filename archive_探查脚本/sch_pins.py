import sqlite3, json, base64, gzip

conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
row = cur.execute("SELECT dataStr FROM documents WHERE display_title='板载温度'").fetchone()
s = row[0][6:] if row[0].startswith('base64') else row[0]
text = gzip.decompress(base64.b64decode(s)).decode('utf-8')
lines = text.splitlines()
for i, ln in enumerate(lines):
    try:
        a = json.loads(ln)
    except Exception:
        continue
    if a[0] in ("PIN", "NET", "PORT"):
        print(i, a[:10])
