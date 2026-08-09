import sqlite3, json, base64, gzip

conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
rows = list(cur.execute("SELECT display_title, dataStr, schematic_uuid FROM documents WHERE docType=1"))

want = set("U18 U26 U27 U28 U24 U3 U4 U5 U2 X1 CN1 CN2 SW1 USBC1 BUZZER1 U1 U29 U30 H1 H2 H3 H4 L1 L2 L3 L4 L5".split())

for title, ds, sch in rows:
    s = ds[6:] if ds.startswith('base64') else ds
    text = gzip.decompress(base64.b64decode(s)).decode('utf-8')
    desig = {}   # component id -> designator
    attrs = {}
    for ln in text.splitlines():
        try:
            arr = json.loads(ln)
        except Exception:
            continue
        if not isinstance(arr, list) or len(arr) < 2:
            continue
        if arr[0] == "COMPONENT":
            cid = arr[1]
            attrs.setdefault(cid, {})
        elif arr[0] == "ATTR" and len(arr) >= 5:
            cid, name, val = arr[2], arr[3], arr[4]
            if isinstance(val, str):
                attrs.setdefault(cid, {})[name] = val
            elif isinstance(val, (int, float)):
                attrs.setdefault(cid, {})[name] = str(val)
    print(f"########## {title} (sch {sch}) ##########")
    for cid, a in attrs.items():
        d = a.get("Designator", "")
        if d in want:
            print(f"  {d}: ", json.dumps(a, ensure_ascii=False)[:400])
