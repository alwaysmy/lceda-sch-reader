import io, sys, json, sqlite3, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
cur = conn.cursor()
st = json.loads(cur.execute("SELECT structure FROM project_structures").fetchone()[0])

boards = st["boards"]
schems = st["schematics"]
sheets = st["sheets"]

print("== source 各段 uuid 对照结构树 ==")
for bs in st["blockSymbols"].values():
    print(f"{bs['title']}:")
    for seg in str(bs.get("source", "")).split("|"):
        hit = None
        if seg in boards:
            hit = f"board: {boards[seg]['title']}"
        elif seg in schems:
            hit = f"schematic: {schems[seg]['name']}"
        elif seg in sheets:
            hit = f"sheet: {sheets[seg]['title']}"
        print(f"   {seg} -> {hit or '未命中(外部工程引用?)'}")

print("\n== sheets 树全量（板名::页名） ==")
for s in sheets.values():
    b = boards.get(s.get("board"), {})
    print(f"   {b.get('title','?')} :: {s['title']}  (sheet uuid={s['uuid']})")

print("\n== .epro 的 boards/schematics uuid 是否与 structure 一致 ==")
EP = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
obj = json.loads(zipfile.ZipFile(EP).read("project.json"))
epro_sch = set(obj.get("schematics", {}).keys())
for name, sch in list(obj.get("schematics", {}).items())[:3]:
    print("  .epro schematic uuid 样例:", name[:16], "keys:", list(sch.keys())[:6])
overlap = epro_sch & set(schems.keys())
print(f"  .epro schematics 与 structure 交集: {len(overlap)}/{len(epro_sch)}")
