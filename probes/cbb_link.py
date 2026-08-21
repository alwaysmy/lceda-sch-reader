import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

E1 = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
db = lr.EproDB(E1)

print("== 1) boards 字典键（list 的'板'来源） ==")
print(list(db._boards.keys()))

print("\n== 2) quadPizeoDriver_RevA 的 CBB 实例及其属性 ==")
target_board = None
for bname in db._boards:
    if bname == "quadPizeoDriver_RevA":
        target_board = bname
print("目标板:", target_board)
cbb_inst = []
for uuid, title, sch, dt in db.sheets():
    if not title.startswith(target_board + "::"):
        continue
    sheet = lr.parse_sheet(db, uuid)
    for c in sheet["components"]:
        d = c.get("designator") or ""
        if d.startswith("CBB"):
            sym = lr.symbol_of(db, c)
            sp = db.symbol_pins(sym) if sym else None
            # 全部属性
            attrs = {k: str(v)[:50] for k, v in c.get("attrs", {}).items()
                     if k not in ("Unique ID",)}
            cbb_inst.append((title.split("::")[-1], d, sym,
                             sp.get("symbol_type") if sp else None,
                             len(sp["pins"]) if sp else 0, attrs))
for pg, d, sym, st, np_, attrs in cbb_inst:
    print(f"\n[{pg}] {d} symbol_type={st} pins={np_}")
    print("   attrs:", json.dumps(attrs, ensure_ascii=False)[:400])

print("\n== 3) CBB 符号定义内容（找指向 CBB 页的链接） ==")
seen = set()
for pg, d, sym, st, np_, attrs in cbb_inst[:3]:
    if sym in seen or not sym:
        continue
    seen.add(sym)
    fname = f"SYMBOL/{sym}.esym"
    if fname in db._names:
        text = db.zip.read(fname).decode("utf-8", errors="replace")
        for ln in text.splitlines()[:6]:
            print(f"  {d} {sym[:12]}: {ln[:150]}")

print("\n== 4) project.json 里 CBB/reuse 相关结构 ==")
obj_keys = list(db.obj.keys())
print("project.json 顶层键:", obj_keys)
for k in obj_keys:
    v = db.obj[k]
    if isinstance(v, dict):
        kk = [x for x in v.keys() if "cbb" in str(x).lower() or "reuse" in str(x).lower()]
        if kk:
            print(f"  {k} 含 CBB/reuse 键:", kk[:6])
# boards 条目结构
b0 = db._boards.get("_CBB_MAX5318_2L") or next(iter(db._boards.values()))
print("boards['_CBB_MAX5318_2L'] 键:", list(b0.keys()) if isinstance(b0, dict) else b0)
print(json.dumps(b0, ensure_ascii=False)[:300])

print("\n== 5) 各板位号唯一性（含跨页） ==")
board_des = collections.defaultdict(lambda: collections.defaultdict(set))
for uuid, title, sch, dt in db.sheets():
    bname = title.split("::")[0]
    sheet = lr.parse_sheet(db, uuid)
    for c in sheet["components"]:
        d = c.get("designator")
        if d:
            board_des[bname][d].add(title.split("::")[-1])
for bname, des in board_des.items():
    dup = {d: pgs for d, pgs in des.items() if len(pgs) > 1}
    print(f"[{bname}] 位号数={len(des)}, 板内跨页重号={len(dup)}",
          {k: sorted(v) for k, v in list(dup.items())[:3]})