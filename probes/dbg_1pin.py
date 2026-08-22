import io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db = lr.Epro2DB(V3)
titles = collections.Counter()
for u, d in db._docs.items():
    if d["docType"] != "SYMBOL":
        continue
    npin = sum(1 for ln in db._iter_doc_lines(u) if '"PIN"' in ln[:14])
    m = db._meta.get(u) or {}
    titles[(npin, m.get("title"), m.get("docType"))] += 1
for (n, t, dt), c in sorted(titles.items()):
    if n <= 2:
        print(f"pins={n} docType={dt} title={t!r} x{c}")
