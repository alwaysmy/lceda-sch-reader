import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

def vicinity(db, page_title, cx, cy, r=120):
    page = next(u for u, t, s, dt in db.sheets()
                if t == page_title)
    sheet = lr.parse_sheet(db, page)
    pts = []
    for n in sheet["nets"]:
        for px, py in n["points"]:
            if abs(px - cx) <= r and abs(py - cy) <= r:
                pts.append((px, py, n["net"]))
    return len(sheet["nets"]), sorted(pts)

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
EP = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
db3 = lr.Epro2DB(V3)
db2 = lr.EproDB(EP)

for tag, db in (("epro2", db3), ("epro", db2)):
    tot, pts = vicinity(db, "quadPizeoDriver_RevA::ControlDAC_A", 625, -840)
    print(f"[{tag}] 页wire总数={tot}, CBB6附近±120端点数={len(pts)}")
    for p in pts[:10]:
        print("   ", p)
