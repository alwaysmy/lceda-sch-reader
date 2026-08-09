import sqlite3, json, base64, gzip, re

conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
schmap = {r[0]: r[1] for r in cur.execute("SELECT uuid, name FROM schematics")}
rows = list(cur.execute("SELECT display_title, dataStr, schematic_uuid, docType FROM documents"))

targets = re.compile(r'ad5749|dac8760|dac8562|dac7562|ads8331|ltc2485|adt7310|w25q128|at24c256|ch343|ltc6655|tlv757|tps7a20|opa2192|opa2333|x3225', re.I)

for title, ds, sch, dt in rows:
    if dt != 1 or not ds:
        continue
    s = ds[6:] if ds.startswith('base64') else ds
    try:
        text = gzip.decompress(base64.b64decode(s)).decode('utf-8')
    except Exception:
        continue
    names = []
    board = page = ''
    for ln in text.splitlines():
        try:
            a = json.loads(ln)
        except Exception:
            continue
        if isinstance(a, list) and len(a) >= 5 and a[0] == "ATTR" and a[3] in ("@Board Name", "@Page Name"):
            if a[3] == "@Board Name": board = a[4]
            else: page = a[4]
    hits = set(m.group(0).upper() for m in targets.finditer(text))
    if hits:
        print(f"[{schmap.get(sch,'?'):10s}] {title:18s} board={board:10s} page={page:12s} hits={sorted(hits)}")
