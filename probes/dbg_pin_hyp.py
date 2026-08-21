import io, sys, math
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
pts = [(px, py) for n in sheet["nets"] for px, py in n["points"]]

def mind(ax, ay):
    return min((ax - px) ** 2 + (ay - py) ** 2 for px, py in pts)

sumA = sumB = 0
print("pin            A:d2(base)   B:d2(base+len)")
for p in sp["pins"]:
    L = p.get("_len") or 10
    axA, ayA = c6["x"] + p["x"], c6["y"] + p["y"]
    rad = math.radians(p["rot"] or 0)
    axB = c6["x"] + p["x"] + L * math.cos(rad)
    ayB = c6["y"] + p["y"] - L * math.sin(rad)
    dA, dB = mind(axA, ayA), mind(axB, ayB)
    sumA += dA
    sumB += dB
    print(f"{p['name']:14s} {dA:8.1f}   {dB:8.1f}")
print("合计:", round(sumA, 1), round(sumB, 1))
