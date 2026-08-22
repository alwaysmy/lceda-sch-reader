import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

X = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver_export.epro2"
db = lr.Epro2DB(X)
n_found = 0
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
        dom = lr.resolve_nets_by_domain(db, sh, cp, ws_, pw, ep)
        for (des, pin), v in dom.items():
            toks = set(lr.net_tokens(v))
            if "DAC0_SCLK_A" in toks and des.startswith("C"):
                print(f"{t[:30]:32s} {des}.{pin} -> {v[:60]}")
                n_found += 1
                if n_found >= 6:
                    sys.exit(0)
    except Exception:
        pass
print("合计:", n_found)
