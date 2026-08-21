import io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

E1 = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
db = lr.EproDB(E1)

print("== Symbol 属性覆盖率（评估 COMPONENT a[2] 归一化是否丢信息） ==")
tot = has_sym = has_dev = 0
missing = []
for uuid, title, sch, dt in db.sheets():
    sheet = lr.parse_sheet(db, uuid)
    for c in sheet["components"]:
        tot += 1
        if c.get("symbol_uuid"):
            has_sym += 1
        else:
            missing.append((title, c.get("designator"), c.get("title")[:40]))
        if c.get("device_uuid"):
            has_dev += 1
print(f"实例总数={tot}, 有Symbol属性={has_sym} ({has_sym*100//max(tot,1)}%), "
      f"有Device={has_dev}")
print("无 Symbol 属性实例:", len(missing), missing[:8])

print("\n== 母图上 CBB 复用块实例的引脚参与情况 ==")
for uuid, title, sch, dt in db.sheets():
    if title.endswith("ControlDAC_A") and "RevA_1.1" in title:
        sheet = lr.parse_sheet(db, uuid)
        pinc = lr._collect_pinmap_data(db, sheet, uuid)
        cp, ws, pw, ep = pinc
        cbb_keys = [k for k in cp if k[0].startswith("CBB")]
        print(f"[{title}] comp_pins 中 CBB 键: {cbb_keys[:4]}")
        # CBB 实例的 symbol_type
        for c in sheet["components"]:
            if c.get("designator") and c["designator"].startswith("CBB"):
                sym = lr.symbol_of(db, c)
                sp = db.symbol_pins(sym) if sym else None
                print(f"  {c['designator']}: title={c.get('title')!r} "
                      f"symbol_type={sp.get('symbol_type') if sp else None} "
                      f"pins={len(sp['pins']) if sp else 0}")
        break

print("\n== DNP 短接符场景存在性 ==")
dnp_short = 0
tot_short = 0
for uuid, title, sch, dt in db.sheets():
    sheet = lr.parse_sheet(db, uuid)
    for c in sheet["components"]:
        sym = lr.symbol_of(db, c)
        sp = db.symbol_pins(sym) if sym else None
        if sp and sp.get("symbol_type") == 22:
            tot_short += 1
            if c.get("dnp"):
                dnp_short += 1
print(f"E1 短接符实例={tot_short}, 其中 DNP={dnp_short}")
# 涡流工程的短接符 DNP 情况
N = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
dbn = lr.LcedaDB(N)
ds = td = 0
for uuid, title, sch, dt in dbn.sheets():
    if dt != 1:
        continue
    sheet = lr.parse_sheet(dbn, uuid)
    for c in sheet["components"]:
        sym = lr.symbol_of(dbn, c)
        sp = dbn.symbol_pins(sym) if sym else None
        if sp and sp.get("symbol_type") == 22:
            td += 1
            if c.get("dnp"):
                ds += 1
print(f"涡流工程 短接符={td}, DNP={ds}")