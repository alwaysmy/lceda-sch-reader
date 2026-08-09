import sqlite3, json, base64, gzip

conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
schmap = {r[0]: r[1] for r in cur.execute("SELECT uuid, name FROM schematics")}
rows = list(cur.execute("SELECT display_title, dataStr, schematic_uuid, docType FROM documents"))
for title, ds, sch, dt in rows:
    info = {}
    if dt == 1 and ds:
        s = ds[6:] if ds.startswith('base64') else ds
        try:
            text = gzip.decompress(base64.b64decode(s)).decode('utf-8')
            for ln in text.splitlines():
                try:
                    a = json.loads(ln)
                except Exception:
                    continue
                if isinstance(a, list) and len(a) >= 5 and a[0] == "ATTR" and a[3] in ("@Board Name", "@Page Name", "@Schematic Name", "Version", "Description"):
                    info[a[3]] = a[4]
        except Exception:
            pass
    print(f"[sch={schmap.get(sch,'?'):12s} docType={dt}] {title:20s} {info}")
