"""探针：Buck .epro 页的 ATTR 公式值 / showKey 分布 / FONTSTYLE 对齐 / MARK 件。"""
import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

P = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples"
     r"\ProPrj_TPS56C230_Buck_12Vto5V_6A_2026-08-13.epro")
db = lr.EproDB(P)
page = None
for u, t, s, dt in db.sheets():
    if dt == 1 and t and t.endswith("::P1"):
        page = u
        break
print("页:", page)
recs = db.sheet_records(page)

n_formula = 0
n_showkey = 0
print("== 含公式的 ATTR（value 含 {）==")
for a in recs:
    if not (isinstance(a, list) and a and a[0] == "ATTR" and len(a) >= 11):
        continue
    v = a[4]
    if isinstance(v, str) and "{" in v:
        n_formula += 1
        if n_formula <= 15:
            print(f"  parent={a[2]} key={a[3]!r} value={v!r} "
                  f"showK={a[5]} showV={a[6]} pos=({a[7]},{a[8]})")
print("公式 ATTR 总数:", n_formula)

print("\n== showKey=1 的 ATTR 样例 ==")
for a in recs:
    if not (isinstance(a, list) and a and a[0] == "ATTR" and len(a) >= 11):
        continue
    if a[5] in (1, True):
        n_showkey += 1
        if n_showkey <= 10:
            print(f"  parent={a[2]} key={a[3]!r} value={str(a[4])[:30]!r} "
                  f"pos=({a[7]},{a[8]})")
print("showKey=1 总数:", n_showkey)

print("\n== MARK 件 ==")
sh = lr.parse_sheet(db, page)
for c in sh["components"]:
    if c.get("designator") and "MARK" in str(c.get("designator")):
        print(f"  {c['designator']} title={c['title']} pos=({c['x']},{c['y']}) "
              f"attrs keys={list(c['attrs'].keys())[:8]}")
        for k, v in c["attrs"].items():
            if k in ("Designator", "Value", "Comment", "Name"):
                print(f"    {k} = {v!r}")

print("\n== FONTSTYLE 对齐值分布 ==")
for a in recs:
    if isinstance(a, list) and a and a[0] == "FONTSTYLE":
        print(f"  {a[1]}: size={a[5]} italic={a[6]} bold={a[7]} "
              f"valign={a[10] if len(a)>10 else None} "
              f"halign={a[11] if len(a)>11 else None}")
