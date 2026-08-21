import io, sys, json, zipfile, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

EP = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
z = zipfile.ZipFile(EP)
pj = json.loads(z.read("project.json"))

print("== symbols 字典中 CBB 黑盒条目（uuid→title） ==")
targets = {
    "f52e546ce1a1a07b": "CBB10-15",
    "1cc4f0d4e74cf584": "CBB6/7",
    "19844b9cc0d9461488996b4c8bc1386d": "CBB4/5",
    "9d8e412cce3444e4b105fb64dde2f921": "CBB2/3",
    "cc6076feee4a4475b4bdecda1ff02235": "CBB1",
}
syms = pj.get("symbols", {})
for u, tag in targets.items():
    ent = syms.get(u)
    print(f"  {tag} {u[:14]}: title={ent.get('title')!r} "
          f"keys={list(ent.keys()) if isinstance(ent, dict) else type(ent)}")

print("\n== 全 project.json 搜这些 uuid 的其他出现位置 ==")
raw = z.read("project.json").decode("utf-8", errors="replace")
for u, tag in targets.items():
    print(f"  {tag}: 出现 {raw.count(u)} 次")

print("\n== esym 文件全文（CBB1 黑盒，找链接字段） ==")
txt = z.read("SYMBOL/cc6076feee4a4475b4bdecda1ff02235.esym").decode(
    "utf-8", errors="replace")
print("  行数:", len(txt.splitlines()))
for ln in txt.splitlines():
    print("  ", ln[:180])

print("\n== boards/schematics 条目全键 ==")
for bu, b in list(pj.get("boards", {}).items())[:3]:
    print(f"  board {bu[:12]}: {json.dumps(b, ensure_ascii=False)[:150]}")
for su, s in list(pj.get("schematics", {}).items())[:3]:
    print(f"  sch   {su[:12]}: keys={list(s.keys()) if isinstance(s, dict) else s}")
