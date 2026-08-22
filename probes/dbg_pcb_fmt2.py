"""探针2：V3 PCB ATTR/PAD_NET/NET body 格式 + .epcb 内容格式。"""
import io, sys, json, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

# ── V3 (.epro2) ──
P = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器_backup\涡流传感器_2026-08-10-14-47.epro2"
r = lr.detect_backend(P)
db = r(P)
pcb_u = [u for u, d in db._docs.items() if d["docType"] == "PCB"][0]
want = {"ATTR": 3, "PAD_NET": 3, "NET": 2, "LAYER": 2}
shown = {k: 0 for k in want}
for ln in db._iter_doc_lines(pcb_u):
    head, _, body = ln.partition("||")
    h = lr.Epro2DB._jl(head)
    if not h: continue
    t = h.get("type")
    if t in want and shown[t] < want[t]:
        shown[t] += 1
        b = lr.Epro2DB._jl(body.rstrip("|")) or {}
        print(f"[V3 {t}] head={json.dumps(h)[:80]}")
        print(f"  body={json.dumps(b, ensure_ascii=False)[:300]}")

# ── V2 (.epro) ──
print("\n== .epro PCB/*.epcb ==")
PE = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
z = zipfile.ZipFile(PE)
obj = json.loads(z.read("project.json"))
pcbs = obj.get("pcbs", {})
print(f"obj['pcbs'] 类型={type(pcbs).__name__}, 条数={len(pcbs)}")
items = list(pcbs.items())[:3]
for k, v in items:
    print(f"  {k}: {json.dumps(v, ensure_ascii=False)[:200]}")

name = [n for n in z.namelist() if n.startswith("PCB/") and n.endswith(".epcb")][0]
raw = z.read(name).decode("utf-8", errors="replace")
print(f"\n{name}: {len(raw)} chars")
for ln in raw.splitlines()[:25]:
    s = ln[:150]
    print(" ", s)
