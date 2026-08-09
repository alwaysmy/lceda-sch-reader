import sqlite3, json, re
conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
rows = list(cur.execute("SELECT display_title, dataStr FROM documents WHERE docType=1"))
for title, ds in rows:
    print("="*20, title, "="*20)
    try:
        data = json.loads(ds)
    except Exception as e:
        print("parse error", e)
        continue
    def walk(node, depth=0):
        if isinstance(node, dict):
            t = node.get('type') or node.get('name')
            if t in ('component','COMPONENT','SYMBOL'):
                attrs = {}
                def get_attr(v):
                    if isinstance(v, dict):
                        if 'text' in v and isinstance(v['text'], str):
                            return v['text']
                        for k2 in ('content','textString'):
                            if k2 in v and isinstance(v[k2], str):
                                return v[k2]
                    return None
                for k, v in node.items():
                    s = get_attr(v)
                    if s: attrs[k] = s
                print(json.dumps({k: node.get(k) for k in ('id','uuid','component','deviceName','title','value')}, ensure_ascii=False)[:200])
                if attrs:
                    print("   attrs:", json.dumps(attrs, ensure_ascii=False)[:300])
            for v in node.values():
                walk(v, depth+1)
        elif isinstance(node, list):
            for v in node:
                walk(v, depth+1)
    walk(data)
