import sqlite3, json, base64, gzip

conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
rows = list(cur.execute("SELECT display_title, dataStr FROM documents WHERE docType=1"))

def decompress(ds):
    s = ds[6:] if ds.startswith('base64') else ds
    return gzip.decompress(base64.b64decode(s)).decode('utf-8')

out = []
for title, ds in rows:
    try:
        lines = decompress(ds).splitlines()
    except Exception as e:
        out.append(f"## {title}: FAIL {e}")
        continue
    comps = {}   # id -> {designator, value, shape, etc}
    order = []
    for ln in lines:
        try:
            arr = json.loads(ln)
        except Exception:
            continue
        if not isinstance(arr, list) or len(arr) < 2:
            continue
        kind = arr[0]
        if kind == "COMPONENT":
            cid = arr[1]
            comps[cid] = {"type": arr[2] if len(arr)>2 else ""}
            order.append(cid)
        elif kind == "ATTR" and len(arr) >= 5:
            cid, name, val = arr[2], arr[3], arr[4]
            if cid in comps and name in ("Designator","Value","Name","Symbol","Manufacturer Part Number","Manufacturer"):
                if name not in comps[cid]:
                    comps[cid][name] = val
    out.append(f"## {title}")
    for cid in order:
        c = comps[cid]
        if c.get("Designator") is None:
            continue
        des = c.get("Designator","")
        val = c.get("Value","") or c.get("Name","")
        sym = c.get("Symbol","")
        out.append(f"{des}\t{val}\t{sym}")

open(r'C:\Users\dell\AppData\Local\Temp\opencode\sch_bom.txt','w',encoding='utf-8').write('\n'.join(out))
print("done")
