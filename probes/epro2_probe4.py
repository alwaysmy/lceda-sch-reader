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

docs = []          # (docType, uuid, meta)
cur_doc = None
type_dist = collections.Counter()
doc_type_dist = collections.Counter()
page_recs = collections.Counter()   # 记录类型在 SCHEMATIC 页内的分布
cbb_hits = []
wire_sample = None
comp_sample = None
iattr_sample = None
attr_sample = None

for ln in data.split("\n"):
    if not ln.strip():
        continue
    head, _, body = ln.partition("||")
    h = jloads(head)
    if h is None:
        continue
    b = jloads(body.rstrip("|"))
    t = h.get("type")
    type_dist[t] += 1
    if t == "DOCHEAD":
        dt = (b or {}).get("docType", "?")
        du = (b or {}).get("uuid", "?")
        cur_doc = (dt, du)
        doc_type_dist[dt] += 1
        docs.append(cur_doc)
        continue
    if not cur_doc:
        continue
    dt = cur_doc[0]
    if dt == "SCHEMATIC" or dt == "SCH":
        page_recs[t] += 1
        if t == "WIRE" and wire_sample is None:
            wire_sample = (h, b)
        if t == "COMPONENT" and comp_sample is None:
            comp_sample = (h, b)
        if t == "INSTANCE_ATTR" and iattr_sample is None:
            iattr_sample = (h, b)
        if t == "ATTR" and attr_sample is None:
            attr_sample = (h, b)
    s = json.dumps(b, ensure_ascii=False) if b else ""
    if "blockSymbol" in s or '"CBB' in s.upper()[:20]:
        cbb_hits.append((t, s[:150]))

print("docType 分布:", dict(doc_type_dist))
print("\nSCHEMATIC 页内记录类型分布:", dict(page_recs.most_common(25)))
print("\nWIRE 样本:", json.dumps(wire_sample, ensure_ascii=False)[:400])
print("\nCOMPONENT 样本:", json.dumps(comp_sample, ensure_ascii=False)[:400])
print("\nINSTANCE_ATTR 样本:", json.dumps(iattr_sample, ensure_ascii=False)[:300])
print("\nATTR 样本:", json.dumps(attr_sample, ensure_ascii=False)[:300])
print("\nblockSymbol/CBB 命中:", len(cbb_hits), cbb_hits[:3])
