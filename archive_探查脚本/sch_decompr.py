import sqlite3, json, base64, gzip

conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
rows = list(cur.execute("SELECT display_title, dataStr FROM documents WHERE docType=1"))

def decompress(ds):
    s = ds
    if s.startswith('base64'):
        s = s[6:]
    data = base64.b64decode(s)
    # try gzip
    try:
        return json.loads(gzip.decompress(data).decode('utf-8'))
    except Exception:
        pass
    try:
        return json.loads(data.decode('utf-8'))
    except Exception as e:
        return None

out = []
for title, ds in rows:
    data = decompress(ds)
    if data is None:
        out.append(f"## {title}: FAILED TO PARSE")
        continue
    comps = []
    def walk(node):
        if isinstance(node, dict):
            t = (node.get('type') or node.get('name') or '').lower()
            if t in ('component', 'symbol'):
                # EasyEDA pro: components have "title" and "customPrefix"/"displayTitle"
                info = {}
                for k in ('title','displayTitle','customPrefix','prefix','designator','value','description'):
                    if k in node:
                        v = node[k]
                        if isinstance(v, dict):
                            v = v.get('text') or v.get('content') or ''
                        info[k] = v
                if info:
                    comps.append(info)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(data)
    out.append(f"## {title}")
    for c in comps:
        out.append(json.dumps(c, ensure_ascii=False))

open(r'C:\Users\dell\AppData\Local\Temp\opencode\sch_comps.txt','w',encoding='utf-8').write('\n'.join(out))
print("done", len(out))
