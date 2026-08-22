"""疑点定位：①MCU主控 epro2 缺失的 GPIO 网络；②示例工程元件 0。"""
import io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

F_E = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\V1.1版主控原理图\MCU主控-V1.1-2026.05.06.eprj2"
F_3 = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\V1.1版主控原理图\MCU主控-V1.1-2026.05.06_backup\MCU主控-V1.1-2026.05.06_2026-08-07-14-46.epro2"

def net_members(db, target):
    out = []
    for u, t, s, dt in db.sheets():
        if dt != 1:
            continue
        sh = lr.parse_sheet(db, u)
        if not sh:
            continue
        pinc = lr._collect_pinmap_data(db, sh, u)
        if not pinc:
            continue
        cp, ws, pw, ep = pinc
        dom = lr.resolve_nets_by_domain(db, sh, cp, ws, pw, ep)
        for (des, pin), v in dom.items():
            if target in [x for x in v.split(",") if x]:
                out.append((t.split("::")[-1], des, pin))
    return out

dbE = lr.detect_backend(F_E)(F_E)
db3 = lr.detect_backend(F_3)(F_3)

print("== MCU主控: PA8 在两侧的成员 ==")
print("  eprj2:", net_members(dbE, "PA8")[:8])
print("  epro2:", net_members(db3, "PA8")[:8])

# 找 eprj2 中 PA8 所在页，取该页同名引脚在 epro2 的解析
m = net_members(dbE, "PA8")
if m:
    pg, des, pin = m[0][0], m[0][1], m[0][2]
    print(f"\n  定位 {pg} {des}.{pin}，对比两侧该元件全部引脚：")
    for tag, db in (("eprj2", dbE), ("epro2", db3)):
        for u, t, s, dt in db.sheets():
            if dt != 1 or t.split("::")[-1] != pg:
                continue
            sh = lr.parse_sheet(db, u)
            pinc = lr._collect_pinmap_data(db, sh, u)
            cp, ws, pw, ep = pinc
            dom = lr.resolve_nets_by_domain(db, sh, cp, ws, pw, ep)
            pins = [(k[1], v) for k, v in sorted(dom.items())
                    if k[0] == des]
            print(f"    [{tag}] {des}: {len(pins)} 脚")
            for pn, v in pins[:10]:
                print(f"       {pn} -> {v[:36]}")
            break

# 该页两侧 wire 统计
print("\n== 该页 wire/NET 统计 ==")
for tag, db in (("eprj2", dbE), ("epro2", db3)):
    for u, t, s, dt in db.sheets():
        if dt != 1 or t.split("::")[-1] != pg:
            continue
        sh = lr.parse_sheet(db, u)
        named = [n["net"] for n in sh["nets"] if n["net"]]
        cnt = collections.Counter(named)
        print(f"  [{tag}] wire总数={len(sh['nets'])} 命名={len(named)} "
              f"唯一名={len(cnt)} top={cnt.most_common(5)}")
        break

# 示例工程_快速入门 元件 0
print("\n== 示例工程_快速入门 抽查 ==")
FQ = r"C:\Users\dell\Documents\LCEDA-Pro\example-projects\示例工程_快速入门.eprj2"
dbq = lr.detect_backend(FQ)(FQ)
import sqlite3
print("  documents 行:", list(dbq.cur.execute(
    "SELECT docType, COUNT(*) FROM documents GROUP BY docType")))
for u, t, s, dt in dbq.sheets():
    recs = dbq.sheet_records(u)
    kinds = collections.Counter(r[0] for r in (recs or []))
    print(f"  页 {t[:30]} docType={dt} 记录={dict(kinds)}")
