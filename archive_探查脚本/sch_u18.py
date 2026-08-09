import sqlite3, json, base64, gzip

conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
row = cur.execute("SELECT dataStr FROM documents WHERE display_title='板载温度'").fetchone()
s = row[0][6:] if row[0].startswith('base64') else row[0]
text = gzip.decompress(base64.b64decode(s)).decode('utf-8')
lines = text.splitlines()
# find COMPONENT/ATTR pairs for U18 and dump net names near
arrs = []
for ln in lines:
    try:
        arrs.append(json.loads(ln))
    except Exception:
        pass
# Dump all unique record kinds
kinds = {}
for a in arrs:
    kinds[a[0]] = kinds.get(a[0], 0) + 1
print("KINDS:", kinds)
print()
# dump ATTRIBUTE (or ATTR) that has pin name & net name, focus U18
for a in arrs:
    if a[0] == "ATTR" and len(a) >= 5:
        print(a[:5])
