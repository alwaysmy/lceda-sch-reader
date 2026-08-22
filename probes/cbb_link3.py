import io, sys, json, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

E1 = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
db = lr.EproDB(E1)

print("== A) Power 页 CBB1 的原始记录（全部字段） ==")
for uuid, title, sch, dt in db.sheets():
    if title == "quadPizeoDriver_RevA::Power":
        recs = db.sheet_records(uuid)
        # 找 CBB1 实例的 COMPONENT 与其全部 ATTR
        cid = None
        for a in recs:
            if isinstance(a, list) and a[0] == "ATTR" and a[3] == "Designator" \
                    and str(a[4]) == "CBB1":
                cid = a[2]
                break
        print("CBB1 实例 cid =", cid)
        for a in recs:
            if isinstance(a, list) and len(a) > 2 and a[2] == cid:
                print("  ", json.dumps(a, ensure_ascii=False)[:220])
        break

print("\n== B) CBB 黑盒符号 esym 全文（找模板引用字段） ==")
sym = "cc6076feee4a4475b4bdecda1ff02235"
text = db.zip.read(f"SYMBOL/{sym}.esym").decode("utf-8", errors="replace")
for ln in text.splitlines():
    if '"ATTR"' in ln or '"HEAD"' in ln or "reuse" in ln.lower() \
            or "cbb" in ln.lower():
        print("  ", ln[:200])

print("\n== C) project.json: 母图板与 schematics 条目结构 ==")
b = db._boards.get("quadPizeoDriver_RevA", {})
print("boards[quadPizeoDriver_RevA]:", json.dumps(b, ensure_ascii=False)[:300])
sch_uuid = b.get("schematic")
sc = db._schematics.get(sch_uuid, {})
print(f"schematics[{sch_uuid}] 键:", list(sc.keys()) if isinstance(sc, dict) else sc)
if isinstance(sc, dict):
    for k, v in sc.items():
        if k != "sheets":
            print(f"   {k} = {json.dumps(v, ensure_ascii=False)[:200]}")

print("\n== D) 悬空 Device uuid 是否在 devices 表 ==")
for du in ("3a27eba539103946", "ddf3eb593d939478", "5a392f919c24590e"):
    print(f"  {du}: in devices={du in db._devices}",
          str(db._devices.get(du))[:120])

print("\n== E) zip 内是否有 REUSE/CBB 相关条目 ==")
hits = [n for n in db.zip.namelist()
         if "reuse" in n.lower() or "cbb" in n.lower()]
print("  ", hits[:10] or "无")

print("\n== F) config 全部键 ==")
print(" ", list(db.obj.get("config", {}).keys()))
