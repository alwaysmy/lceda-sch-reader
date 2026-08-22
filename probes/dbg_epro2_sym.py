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

# 样本元件的属性与符号解析
c0 = next(c for c in sheet["components"] if c.get("designator") == "U41")
print("U41 attrs keys:", {k: str(v)[:30] for k, v in list(c0["attrs"].items())[:8]})
print("U41 title:", repr(c0.get("title")), "symbol_uuid:", repr(c0.get("symbol_uuid")))
sym = lr.symbol_of(db, c0)
print("symbol_of ->", repr(sym))
sp = db.symbol_pins(sym) if sym else None
print("symbol_pins:", "None" if not sp else f"pins={len(sp['pins'])} parts={sp['parts']}")

# 手动走 _collect 的判定链
des = lr._synth_designator(db, c0)
print("_synth_designator:", des)
if sp:
    title = c0.get("title") or ""
    parts = sp["parts"]
    print(f"title={title!r} in parts? {title in parts}, parts={parts[:3]}")

# CBB6 实例
c6 = next((c for c in sheet["components"]
           if (c.get("designator") or "") == "CBB6"), None)
if c6:
    print("\nCBB6 Symbol attr:", repr(c6.get("symbol_uuid")))
    print("cbb_symbol_board_map:", db.cbb_symbol_board_map())
    sp6 = db.symbol_pins(c6.get("symbol_uuid"))
    print("CBB6 symbol_pins:", None if not sp6 else
          f"type={sp6['symbol_type']} pins={len(sp6['pins'])} parts={sp6['parts']}")
