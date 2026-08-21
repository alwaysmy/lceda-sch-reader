"""定位导出包中 resolve 崩溃页 + savedData.attr 结构。"""
import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
for u, t, s, dt in db.sheets():
    if dt != 1:
        continue
    sh = lr.parse_sheet(db, u)
    if not sh:
        continue
    try:
        pinc = lr._collect_pinmap_data(db, sh, u)
        if not pinc:
            continue
        cp, ws_, pw, ep = pinc
        lr.resolve_nets_by_domain(db, sh, cp, ws_, pw, ep)
    except Exception as e:
        print(f"崩溃页: {t} ({u[:12]}) -> {type(e).__name__}: {str(e)[:80]}")
        # 检查该页合成记录里的异常坐标
        recs = db.sheet_records(u)
        bad = []
        for r in recs:
            if r[0] == "COMPONENT" and (len(r) < 7 or
                    not all(isinstance(v, (int, float))
                            for v in (r[3], r[4]))):
                bad.append(r[:6])
            if r[0] == "WIRE":
                for seg in r[2]:
                    for v in seg:
                        if not isinstance(v, (int, float)):
                            bad.append(("WIRE-bad", seg))
        print("  异常记录:", bad[:4], "总数", len(bad))
        break
