import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

EP = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db2 = lr.EproDB(EP)
db3 = lr.Epro2DB(V3)

page2 = next(u for u, t, s, dt in db2.sheets()
             if t == "quadPizeoDriver_RevA::ControlDAC_A")
page3 = next(u for u, t, s, dt in db3.sheets()
             if t == "quadPizeoDriver_RevA::ControlDAC_A")

sh2 = lr.parse_sheet(db2, page2)
c2 = next(c for c in sh2["components"] if c.get("designator") == "CBB6")
sp2 = db2.symbol_pins(c2.get("symbol_uuid"))
p = sp2["pins"][0]
print(f".epro  CBB6 pos=({c2['x']},{c2['y']}) pin {p['name']} raw=({p['x']},{p['y']})")
ax, ay = c2["x"] + p["x"], c2["y"] + p["y"]
pts2 = [(px, py, n["net"]) for n in sh2["nets"] for px, py in n["points"]]
lst = sorted(((ax-px)**2+(ay-py)**2, n, px, py) for px, py, n in pts2)[:2]
print(f"  abs=({ax},{ay}) 最近: {[(round(d,1), n, px, py) for d,n,px,py in lst]}")

sh3 = lr.parse_sheet(db3, page3)
c3 = next(c for c in sh3["components"] if c.get("designator") == "CBB6")
sp3 = db3.symbol_pins(c3.get("symbol_uuid"))
p3 = sp3["pins"][0]
print(f"epro2  CBB6 pos=({c3['x']},{c3['y']}) pin {p3['name']} raw=({p3['x']},{p3['y']})")
ax3, ay3 = c3["x"] + p3["x"], c3["y"] + p3["y"]
pts3 = [(px, py, n["net"]) for n in sh3["nets"] for px, py in n["points"]]
lst3 = sorted(((ax3-px)**2+(ay3-py)**2, n, px, py) for px, py, n in pts3)[:2]
print(f"  abs=({ax3},{ay3}) 最近: {[(round(d,1), n, px, py) for d,n,px,py in lst3]}")

# .epro 命中端点在 epro2 翻转坐标里的对应点
if lst:
    d, n, ex, ey = lst[0]
    print(f"\n.epro 命中点 ({ex},{ey}) -> epro2 应在 ({ex},{-ey})")
    hit3 = [(px, py, n3) for px, py, n3 in pts3
            if abs(px-ex) <= 1 and abs(py+ey) <= 1]
    print("  epro2 中该点存在?", hit3[:3])
