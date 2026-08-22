"""探针：V2 符号文档图形记录类型（渲染器输入格式）。"""
import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

E = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
db = lr.LcedaDB(E)

kinds_all = collections.Counter()
sample = {}
# 取一页的元件符号，看图形原语
for u, title, s, dt in list(db.sheets()):
    if dt != 1 or "激励输出" not in (title or ""):
        continue
    sh = lr.parse_sheet(db, u)
    seen_sym = set()
    for c in sh["components"]:
        sym = lr.symbol_of(db, c)
        if not sym or sym in seen_sym:
            continue
        seen_sym.add(sym)
        row = db.cur.execute(
            "SELECT dataStr FROM components WHERE uuid=?", (sym,)).fetchone()
        if not row:
            continue
        text = db.decompress(row[0])
        for ln in text.splitlines():
            try: a = json.loads(ln)
            except: continue
            if isinstance(a, list) and a:
                kinds_all[a[0]] += 1
                if a[0] in ("LINE", "RECT", "POLY", "ARC", "PATH", "PIN",
                            "TEXT", "ELLIPSE", "BEZIER") and a[0] not in sample:
                    sample[a[0]] = json.dumps(a)[:260]
    break

print("符号文档记录类型分布:", dict(kinds_all.most_common()))
for k, v in sample.items():
    print(f"\n[{k}] {v}")
