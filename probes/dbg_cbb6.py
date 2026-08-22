import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db = lr.Epro2DB(V3)
page = None
for u, t, s, dt in db.sheets():
    if t == "quadPizeoDriver_RevA::ControlDAC_A":
        page = u
        break
sheet = lr.parse_sheet(db, page)
c6 = next(c for c in sheet["components"] if c.get("designator") == "CBB6")
print(f"CBB6 pos=({c6['x']},{c6['y']}) rot={c6['rot']} mirror={c6['mirror']} "
      f"title={c6.get('title')!r}")
sp = db.symbol_pins(c6.get("symbol_uuid"))
print("symbol_type:", sp.get("symbol_type"), "pins:", len(sp["pins"]))
for p in sp["pins"][:4]:
    print(f"   pin {p['name']}: raw=({p['x']},{p['y']}) rot={p['rot']} "
          f"part={p['part']}")

# 手动算前几个引脚绝对坐标，找最近 wire 端点
pts = []
for n in sheet["nets"]:
    for px, py in n["points"]:
        pts.append((px, py, n["net"]))
def near(ax, ay, k=3):
    lst = sorted(((ax-px)**2+(ay-py)**2, n, px, py) for px, py, n in pts)
    return [(round(d2,1), n, px, py) for d2, n, px, py in lst[:k]]
for p in sp["pins"][:4]:
    rx, ry = p["x"], p["y"]
    if c6.get("mirror"):
        rx = -rx
    rot = (c6.get("rot") or 0) % 360
    for _ in range(int(rot // 90)):
        rx, ry = -ry, rx
    ax, ay = c6["x"] + rx, c6["y"] + ry
    print(f"  pin {p['name']} abs=({ax},{ay}) near={near(ax, ay)}")
