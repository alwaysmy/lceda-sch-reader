"""探针：页文档与符号文档中的 FONTSTYLE / TEXT / ATTR 显示属性格式。"""
import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

E = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
db = lr.LcedaDB(E)

# ── 页文档 ──
page_u = None
for u, t, s, dt in db.sheets():
    if dt == 1 and t and "激励输出" in t:
        page_u = u
        break
text = db.sheet_text(page_u)
fs_n = tx_n = 0
attr_show = collections.Counter()
for ln in text.splitlines():
    try: a = json.loads(ln)
    except: continue
    if not isinstance(a, list): continue
    if a[0] == "FONTSTYLE" and fs_n < 6:
        fs_n += 1
        print(f"[页 FONTSTYLE] {json.dumps(a)[:180]}")
    elif a[0] == "TEXT" and tx_n < 4:
        tx_n += 1
        print(f"[页 TEXT] {json.dumps(a)[:200]}")
    elif a[0] == "ATTR":
        # 统计 ATTR 长度分布与 Designator 样例（看显示位字段）
        if len(a) >= 5 and a[3] == "Designator" and attr_show["des"] < 3:
            attr_show["des"] += 1
            print(f"[页 ATTR-Designator len={len(a)}] {json.dumps(a)[:240]}")

# ── 符号文档 ──
print("\n== 符号 ==")
sh = lr.parse_sheet(db, page_u)
seen = set()
fsym = 0
for c in sh["components"]:
    sym = lr.symbol_of(db, c)
    if not sym or sym in seen: continue
    seen.add(sym)
    row = db.cur.execute("SELECT dataStr FROM components WHERE uuid=?",
                         (sym,)).fetchone()
    if not row: continue
    stext = db.decompress(row[0])
    for ln in stext.splitlines():
        try: a = json.loads(ln)
        except: continue
        if not isinstance(a, list): continue
        if a[0] == "FONTSTYLE" and fsym < 8:
            fsym += 1
            print(f"[符 FONTSTYLE] {json.dumps(a)[:180]}")
    if fsym >= 8: break

# ── LINESTYLE 分布 ──
print("\n== 页 LINESTYLE ==")
n = 0
for ln in text.splitlines():
    try: a = json.loads(ln)
    except: continue
    if isinstance(a, list) and a and a[0] == "LINESTYLE" and n < 6:
        n += 1
        print(f"[页 LINESTYLE] {json.dumps(a)[:160]}")
