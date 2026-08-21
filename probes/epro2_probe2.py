import io, sys, json, zipfile, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
z = zipfile.ZipFile(E)

print("== project2.json ==")
pj = json.loads(z.read("project2.json"))
def walk(o, prefix="", depth=0):
    if depth > 2:
        return
    if isinstance(o, dict):
        for k, v in list(o.items())[:12]:
            t = type(v).__name__
            n = len(v) if isinstance(v, (dict, list)) else str(v)[:60]
            print(f"  {prefix}{k} ({t}) {n if isinstance(v,(dict,list)) else ''}")
            walk(v, prefix + "  ", depth + 1)
walk(pj)
print(json.dumps({k: v for k, v in pj.items() if not isinstance(v, (dict, list))},
                 ensure_ascii=False)[:300])

print("\n== epru 记录类型分布（流式扫描 header.type） ==")
data = z.read("Piezo_Driver.epru").decode("utf-8", errors="replace")
types = collections.Counter()
doctypes = collections.Counter()
lines = data.split("\n")
print("总行数:", len(lines))
sch_sample = None
for ln in lines:
    if not ln.strip():
        continue
    head, _, body = ln.partition("||")
    try:
        h = json.loads(head)
    except Exception:
        types["<bad>"] += 1
        continue
    types[h.get("type", "?")] += 1
    if h.get("type") == "DOCHEAD":
        try:
            b = json.loads(body)
            doctypes[b.get("docType", "?")] += 1
        except Exception:
            pass
print("header.type 分布:", dict(types.most_common(30)))
print("DOCHEAD.docType 分布:", dict(doctypes.most_common(30)))
