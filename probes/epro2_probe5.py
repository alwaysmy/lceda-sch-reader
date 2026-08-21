import io, sys, json, zipfile, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
z = zipfile.ZipFile(E)
data = z.read("Piezo_Driver.epru").decode("utf-8", errors="replace")

def jloads(s):
    try:
        return json.loads(s)
    except Exception:
        return None

dist = {dt: collections.Counter() for dt in
        ("BOARD", "SCH", "SCH_PAGE", "INSTANCE", "DEVICE", "SYMBOL")}
samples = {}
meta_samples = []

for ln in data.split("\n"):
    if not ln.strip():
        continue
    head, _, body = ln.partition("||")
    h = jloads(head)
    if h is None:
        continue
    b = jloads(body.rstrip("|"))
    t = h.get("type")
    if t == "DOCHEAD":
        cur_dt = (b or {}).get("docType", "?")
        cur_uuid = (b or {}).get("uuid", "?")
        continue
    if cur_dt in dist:
        dist[cur_dt][t] += 1
        key = (cur_dt, t)
        if key not in samples and b is not None:
            samples[key] = (h.get("id"), b)
    if t == "META" and cur_dt in ("SCH", "SCH_PAGE", "BOARD", "INSTANCE"):
        meta_samples.append((cur_dt, cur_uuid[:12], b))

for dt in dist:
    print(f"[{dt}] 记录类型:", dict(dist[dt].most_common(18)))

print("\n== SCH_PAGE 关键样本 ==")
for key in (("SCH_PAGE", "COMPONENT"), ("SCH_PAGE", "WIRE"),
            ("SCH_PAGE", "ATTR"), ("SCH_PAGE", "INSTANCE_ATTR")):
    if key in samples:
        i, b = samples[key]
        print(f"  {key[1]} id={i}: {json.dumps(b, ensure_ascii=False)[:350]}")

print("\n== BOARD/SCH/INSTANCE META 样本 ==")
for dt, u, b in meta_samples[:14]:
    print(f"  [{dt}] {u}: {json.dumps(b, ensure_ascii=False)[:220]}")

print("\n== INSTANCE 文档内记录样本 ==")
for (d, t), (i, b) in samples.items():
    if d == "INSTANCE":
        print(f"  {t} id={i}: {json.dumps(b, ensure_ascii=False)[:250]}")
