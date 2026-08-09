import sqlite3, json, base64, gzip

conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()

dev = {}
for r in cur.execute("SELECT uuid, title, display_title, description, source, version FROM devices"):
    dev[r[0]] = (r[1], r[2], r[3], r[4], r[5])

# gather symbol uuids seen in bom and resolve
uuids = set()
rows = list(cur.execute("SELECT display_title, dataStr FROM documents WHERE docType=1"))
for title, ds in rows:
    s = ds[6:] if ds.startswith('base64') else ds
    try:
        text = gzip.decompress(base64.b64decode(s)).decode('utf-8')
    except Exception:
        continue
    for ln in text.splitlines():
        try:
            arr = json.loads(ln)
        except Exception:
            continue
        if isinstance(arr, list) and len(arr) >= 5 and arr[0] == "ATTR" and arr[3] == "Symbol":
            uuids.add(arr[4])

print("=== device resolution for symbol uuids ===")
for u in sorted(uuids):
    if u in dev:
        print(u[:8], "->", dev[u])
    else:
        # check components table
        r = cur.execute("SELECT title, display_title, description, source FROM components WHERE uuid=?", (u,)).fetchone()
        if r:
            print(u[:8], "-> COMP:", r)
        else:
            print(u[:8], "-> NOT FOUND")
