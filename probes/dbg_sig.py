import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
sig = lr._cbb_sig(db)
hits = [(u, ti) for u, (p, f, ti) in sig.items()
        if "max5318" in ti.lower()]
print("sig 中 max5318 条目:", hits)
print("sheets() 标题样例:")
for u, t, s, dt in list(db.sheets())[:6]:
    print("  ", t[:50])
# SCH board 值 vs BOARD uuid
buuids = {u for u, _, _ in db._boards}
print("\nSCH.board 样例与命中:")
for u, s in list(db._schs.items())[:6]:
    print(f"   sch {u[:12]} board={s['board'][:16] if s['board'] else '(空)'}"
          f" 命中={s['board'] in buuids} title={s['title'][:30]}")
