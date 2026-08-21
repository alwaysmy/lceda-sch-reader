import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
for u, t, s, dt in db.sheets():
    if dt != 1:
        continue
    sh = lr.parse_sheet(db, u)
    if not sh:
        continue
    try:
        pinc = lr._collect_pinmap_data(db, sh, u)
        if not pinc:
            continue
        cp, ws_, pw, ep = pinc
        dom = lr.resolve_nets_by_domain(db, sh, cp, ws_, pw, ep)
        n = sum(1 for v in dom.values()
                if "DAC0_SCLK_A" in [x for x in v.split(",")
                                     if x] or v == "DAC0_SCLK_A")
        gnd = sum(1 for v in dom.values() if "GND" in v.split(","))
        if n or gnd > 50:
            print(f"{t[:44]:46s} DAC0_SCLK_A={n} GND成员={gnd}")
    except Exception as e:
        print(f"{t[:44]:46s} EXC {type(e).__name__}")
