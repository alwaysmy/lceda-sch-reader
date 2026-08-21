import base64, gzip, io, json, sqlite3, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"

conn = sqlite3.connect(f"file:{NEW}?mode=ro", uri=True)
cur = conn.cursor()

def decompress(ds):
    s = ds[6:] if isinstance(ds, str) and ds.startswith("base64") else ds
    data = base64.b64decode(s)
    try:
        return gzip.decompress(data).decode("utf-8")
    except Exception:
        return data.decode("utf-8", errors="replace")

def parse(text):
    arrs = []
    for ln in text.splitlines():
        try:
            arrs.append(json.loads(ln))
        except Exception:
            continue
    return arrs

def sheet_stats(recs):
    comps, attrs, wires = [], [], []
    net_of = {}
    des_attr = {}
    for a in recs:
        if not isinstance(a, list) or len(a) < 2:
            continue
        if a[0] == 'COMPONENT' and len(a) >= 3:
            comps.append((a[1], a[2]))
        elif a[0] == 'ATTR' and len(a) >= 5 and a[3] == 'Designator':
            des_attr[a[2]] = a[4]
        elif a[0] == 'ATTR' and len(a) >= 5 and a[3] in ('NET', 'Global Net Name'):
            net_of[a[2]] = a[4]
        elif a[0] == 'WIRE':
            wires.append(a[1])
    desigs = set()
    for cid, title in comps:
        d = des_attr.get(cid)
        if d:
            desigs.add(d)
    return len(comps), len(desigs), set(wires), set(net_of.values())

for page in ["激励输出和AD采集", "DA输出", "P1", "对外连接"]:
    print(f"\n===== {page} =====")
    rows = list(cur.execute(
        "SELECT schematic_uuid, dataStr FROM documents WHERE display_title=? AND docType=1", (page,)))
    for sch_uuid, ds in rows:
        sch_name = cur.execute("SELECT name FROM schematics WHERE uuid=?", (sch_uuid,)).fetchone()[0]
        text = decompress(ds)
        recs = parse(text)
        ncomp, ndes, wires, nets = sheet_stats(recs)
        print(f"  {sch_name}: COMPONENT={ncomp} 位号={ndes} WIRE记录={len(wires)} 网络名={len(nets)}")
        if nets:
            print(f"    网络样例: {sorted(x for x in nets if x)[:10]}")

conn.close()