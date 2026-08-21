import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db = lr.Epro2DB(V3)
page = next(u for u, t, s, dt in db.sheets()
            if t == "quadPizeoDriver_RevA::ControlDAC_A")
sheet = lr.parse_sheet(db, page)
c6 = next(c for c in sheet["components"]
          if c.get("designator") == "CBB6")
sp = db.symbol_pins(c6.get("symbol_uuid"))
pts = []
for n in sheet["nets"]:
    for px, py in n["points"]:
        pts.append((px, py, n["net"]))

def near(ax, ay, k=2):
    lst = sorted(((ax - px) ** 2 + (ay - py) ** 2, str(n), px, py)
                 for px, py, n in pts)
    return [(round(d, 1), n, px, py) for d, n, px, py in lst[:k]]

for p in sp["pins"][:5]:
    rx, ry = p["x"], p["y"]
    ax, ay = c6["x"] + rx, c6["y"] + ry
    print(f"pin {p['name']}: abs=({ax},{ay}) near={near(ax, ay)}")

print("\nCBB 黑盒 PIN 原始记录:")
for ln in db._iter_doc_lines(c6.get("symbol_uuid")):
    if '"PIN"' in ln[:14]:
        b = db._jl(ln.partition("||")[2].rstrip("|"))
        print("  ", json.dumps(b, ensure_ascii=False)[:220])
        break
# 母图上 CBB6 的原始 COMPONENT
for ln in db._iter_doc_lines(page):
    if '"COMPONENT"' not in ln[:20]:
        continue
    head, _, body = ln.partition("||")
    h = db._jl(head)
    b = db._jl(body.rstrip("|"))
    if b and b.get("partId") == "4a3d804b79162a2f":
        print("CBB6 COMPONENT:", h.get("id"), json.dumps(b, ensure_ascii=False)[:200])
        break
