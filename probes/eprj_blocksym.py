import io, sys, json, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
cur = conn.cursor()
st = json.loads(cur.execute("SELECT structure FROM project_structures").fetchone()[0])

print("== blockSymbols 完整条目 ==")
for bs in st["blockSymbols"].values():
    print(json.dumps(bs, ensure_ascii=False))

print("\n== sheets 树中各 CBB 板的页 ==")
board_by_uuid = {b["uuid"]: b["title"] for b in st["boards"].values()}
for s in st["sheets"].values():
    bn = board_by_uuid.get(s.get("board"), "?")
    if "_CBB_" in bn:
        print(f"  sheet {s['uuid']} | {bn} :: {s['title']}")

print("\n== source uuid 与 sheets/schematics 对照 ==")
for bs in st["blockSymbols"]:
    srcs = str(bs.get("source", "")).split("|")
    print(f"  {bs['title']}:")
    for s in srcs:
        hit_sheet = st["sheets"].get(s)
        hit_sch = st["schematics"].get(s)
        if hit_sheet:
            print(f"    {s} -> sheet: {hit_sheet['title']}")
        elif hit_sch:
            print(f"    {s} -> schematic: {hit_sch['name']}")
        else:
            print(f"    {s} -> (未命中树)")

print("\n== .epro project.json 是否含 blockSymbols/source ==")
import zipfile
EP = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
z = zipfile.ZipFile(EP)
pj = z.read("project.json").decode("utf-8", errors="replace")
print("  'blockSymbol' 出现:", pj.count("blockSymbol"),
      "| '\"source\"' 出现:", pj.count('"source"'))
obj = json.loads(pj)
for name in z.namelist():
    if name.endswith(".esch"):
        data = z.read(name).decode("utf-8", errors="replace")
        if "blockSymbol" in data or '"source"' in data:
            print(f"  {name}: 含 blockSymbol/source 字样")
