import io, sys, json, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db = lr.Epro2DB(V3)
sym = "1cc4f0d4e74cf584"
print("== CBB 符号文档全部非 ATTR/POLY 记录 ==")
for ln in db._iter_doc_lines(sym):
    head, _, body = ln.partition("||")
    h = db._jl(head)
    if not h:
        continue
    t = h.get("type")
    if t in ("ATTR", "ELE_PLACEHOLDER"):
        continue
    b = db._jl(body.rstrip("|"))
    s = json.dumps(b, ensure_ascii=False)[:200] if b else ""
    print(f"  [{t}] id={str(h.get('id'))[:16]}: {s}")

print("\n== 对照 .epro esym HEAD/PART/PIN ==")
EP = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
z = zipfile.ZipFile(EP)
txt = z.read("SYMBOL/1cc4f0d4e74cf584.esym").decode("utf-8", errors="replace")
for ln in txt.splitlines():
    if ln.startswith('["HEAD"') or ln.startswith('["PART"') or \
            ln.startswith('["PIN"'):
        print("  ", ln[:160])
