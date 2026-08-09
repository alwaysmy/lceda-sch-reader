import sqlite3, json, base64, gzip

conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
rows = list(cur.execute("SELECT display_title, dataStr FROM documents WHERE docType=1"))
targets = {}
for title, ds in rows:
    s = ds[6:] if ds.startswith('base64') else ds
    text = gzip.decompress(base64.b64decode(s)).decode('utf-8')
    for ln in text.splitlines():
        try:
            arr = json.loads(ln)
        except Exception:
            continue
        if not isinstance(arr, list) or len(arr) < 2:
            continue
        if arr[0] == "COMPONENT":
            cid = arr[1]
        elif arr[0] == "ATTR" and len(arr) >= 5:
            cid, name = arr[2], arr[3]
            if cid in targets:
                val = arr[4]
                if isinstance(val, (str, int, float)):
                    targets[cid].append((name, str(val)))
    for comp in ["U18","U26","U27","U28","U24","U2","U3","U4","U5","X1","CN1","CN2","SW1","U1","U2"]:
        # only report the sheets we care about
        pass
