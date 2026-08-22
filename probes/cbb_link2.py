import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

E1 = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
db = lr.EproDB(E1)

print("== config.cbbProject ==")
print(json.dumps(db.obj.get("config", {}).get("cbbProject"),
                 ensure_ascii=False, indent=1)[:800])

print("\n== CBB1-5 的 Device 型号 ==")
dmap = db.device_map()
for du in ("3a27eba539103946", "ddf3eb593d939478", "5a392f919c24590e"):
    print(f"  {du}: {dmap.get(du, ('?','?','?'))}")

print("\n== CBB 黑盒符号的 PIN 名（与模板页 NetPort 对应） ==")
for sym, tag in (("1cc4f0d4e74cf584", "CBB6/7(18p)"),
                 ("f52e546ce1a1a07b", "CBB10-15(6p)"),
                 ("cc6076feee4a4475b4bdecda1ff02235", "CBB1(4p)"),
                 ("9d8e412cce3444e4b105fb64dde2f921", "CBB2/3(4p)"),
                 ("19844b9cc0d9461488996b4c8bc1386d", "CBB4/5(4p)")):
    sp = db.symbol_pins(sym)
    if sp:
        pins = [(p["name"], p["number"]) for p in sp["pins"]]
        print(f"  {tag}: {pins}")

print("\n== 各 CBB 模板页的 NetPort（页面端口） ==")
for uuid, title, sch, dt in db.sheets():
    if not title.startswith("_CBB_") or "_old" in title:
        continue
    sheet = lr.parse_sheet(db, uuid)
    ports = []
    for c in sheet["components"]:
        t = c.get("title") or ""
        d = c.get("designator")
        sym = lr.symbol_of(db, c)
        sp = db.symbol_pins(sym) if sym else None
        st = sp.get("symbol_type") if sp else None
        if st == 19 and not d:   # NetPort
            ports.append(t)
    print(f"[{title}] 端口: {ports}")
