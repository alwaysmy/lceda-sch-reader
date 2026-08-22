"""Dump 原始 PCB 记录格式，确定 COMPONENT/ATTR/PAD_NET 字段布局。"""
import io, sys, json, sqlite3, base64, gzip
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)

def decompress(ds):
    if not ds: return ""
    if ds.startswith("base64"):
        raw = base64.b64decode(ds[6:])
        try: return gzip.decompress(raw).decode("utf-8")
        except: return raw.decode("utf-8", errors="replace")
    return ds

pcb_u = conn.execute(
    "SELECT uuid FROM documents WHERE docType=3 ORDER BY length(dataStr) DESC LIMIT 1"
).fetchone()[0]
text = decompress(conn.execute(
    "SELECT dataStr FROM documents WHERE uuid=?", (pcb_u,)).fetchone()[0])
conn.close()

shown = {"COMPONENT": 0, "ATTR": 0, "PAD_NET": 0, "NET": 0}
LIMIT = 4
for ln in text.split("\n"):
    try: a = json.loads(ln)
    except: continue
    if not isinstance(a, list) or not a: continue
    k = a[0]
    if k in shown and shown[k] < LIMIT:
        shown[k] += 1
        print(f"--- {k} (len={len(a)}) ---")
        for i, v in enumerate(a):
            s = json.dumps(v, ensure_ascii=False)
            if len(s) > 160: s = s[:160] + "...TRUNC"
            print(f"  [{i}] {s}")
        print()
