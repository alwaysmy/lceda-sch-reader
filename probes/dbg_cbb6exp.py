import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
cands = [(u, t) for u, t, s, dt in db.sheets()
         if "controldac_a" in t.lower()]
print("候选页:", cands[:4])
page = cands[0][0]
sh = lr.parse_sheet(db, page)
c6 = next((c for c in sh["components"]
           if c.get("designator") == "CBB6"), None)
if c6:
    print("CBB6 symbol_uuid:", repr(c6.get("symbol_uuid")))
    m = db.cbb_symbol_board_map()
    print("map 命中:", m.get(c6.get("symbol_uuid")))
    sp = db.symbol_pins(c6.get("symbol_uuid"))
    print("symbol_pins:", None if not sp else
          f"type={sp['symbol_type']} pins={len(sp['pins'])}")
else:
    print("该页无 CBB6；组件位号样例:",
          [c.get("designator") for c in sh["components"]][:15])
