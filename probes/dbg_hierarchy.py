"""层级数据侦察：板↔原理图↔页↔PCB 关联在三格式中的存储与完备性。"""
import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

print("== ① LcedaDB (.eprj2 旧版 涡流传感器-V1.0) ==")
F1 = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
db = lr.LcedaDB(F1)
tables = {r[0] for r in db.cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")}
print("  有 boards 表:", "boards" in tables,
      "| 行数:", list(db.cur.execute("SELECT COUNT(*) FROM boards"))[0][0]
      if "boards" in tables else "-")
if "boards" in tables:
    cols = [r[1] for r in db.cur.execute("PRAGMA table_info(boards)")]
    print("  boards 列:", cols)
    for row in list(db.cur.execute("SELECT * FROM boards LIMIT 8")):
        print("   ", str(row)[:110])
# PCB 文档的 schematic_uuid
print("  docType=3 的 schematic_uuid:",
      [(r[0][:10], (r[1] or "")[:12]) for r in db.cur.execute(
          "SELECT uuid, schematic_uuid FROM documents WHERE docType=3")])
print("  schematics 表:", list(db.cur.execute(
    "SELECT uuid, name FROM schematics"))[:8])

print("\n== ② EproDB (.epro Piezo) ==")
EP = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
db2 = lr.EproDB(EP)
pj = db2.obj
print("  project.json 顶层键:", list(pj.keys()))
pcbs = pj.get("pcbs", {})
print(f"  pcbs: {len(pcbs)} 项")
for u, p in list(pcbs.items())[:4]:
    print("   ", u[:12], json.dumps(p, ensure_ascii=False)[:120])
schs = pj.get("schematics", {})
no_board = [u for u, s in schs.items()
            if not any((b.get("schematic") == u) for b in db2._boards.values())]
print(f"  未被任何板引用的 SCH: {len(no_board)}",
      [db2._schematics.get(u, {}).get('name', u)[:20] for u in no_board[:6]])
pcb_no_board = [u for u in pcbs
                if not any((b.get("pcb") == u) for b in db2._boards.values())]
print(f"  未被任何板引用的 PCB: {len(pcb_no_board)}")

print("\n== ③ Epro2DB (.epro2 Piezo) ==")
V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db3 = lr.Epro2DB(V3)
pcb_docs = {}
for u, d in db3._docs.items():
    if d["docType"] == "PCB":
        m = db3._meta.get(u) or {}
        pcb_docs[u] = m
print(f"  PCB 文档: {len(pcb_docs)}")
for u, m in list(pcb_docs.items())[:5]:
    print("   ", u[:12], json.dumps(m, ensure_ascii=False)[:150])
# SCH 无 board 的（游离/CBB）
free_sch = [u for u, s in db3._schs.items() if not s["board"]]
print(f"  无 board 的 SCH: {len(free_sch)}")
