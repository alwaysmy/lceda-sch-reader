import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
print("cbb_symbol_board_map:", db.cbb_symbol_board_map())
page = next(u for u, t, s, dt in db.sheets()
            if t == "quadPizeoDriver_RevA::ControlDAC_A")
sh = lr.parse_sheet(db, page)
c6 = next(c for c in sh["components"]
          if c.get("designator") == "CBB6")
print("CBB6 symbol_uuid:", repr(c6.get("symbol_uuid")))
sp = db.symbol_pins(c6.get("symbol_uuid"))
print("symbol_pins:", None if not sp else
      f"type={sp['symbol_type']} pins={len(sp['pins'])}")
pinc = lr._collect_pinmap_data(db, sh, page)
cp = pinc[0]
cbb6 = cp.get(("CBB6", c6["cid"]))
print("CBB6 引脚数:", len(cbb6) if cbb6 else 0)
