import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

E1 = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
db = lr.EproDB(E1)
dmap = db.device_map()

print("== E1 全部 CBB 页 ==")
for uuid, title, sch, dt in db.sheets():
    if "_CBB_" in title:
        sheet = lr.parse_sheet(db, uuid)
        comps = [c for c in sheet["components"]]
        desigs = sorted((c.get("designator") or "?") for c in comps)
        print(f"\n[{title}] 元件 {len(comps)} 个")
        print("  位号:", ",".join(desigs))
        # 型号抽样
        samples = []
        for c in comps[:8]:
            du = c.get("device_uuid") or ""
            dev = dmap.get(du, ("", "", ""))[1] if du else ""
            samples.append(f"{c.get('designator')}={dev or c.get('title')}")
        print("  型号:", "; ".join(samples))
        # pinmap 是否可用
        pinc = lr._collect_pinmap_data(db, sheet, uuid)
        cp, ws, pw, ep = pinc
        dom = lr.resolve_nets_by_domain(db, sheet, cp, ws, pw, ep)
        named = sum(1 for v in dom.values() if v)
        print(f"  pinmap 引脚数={len(dom)}, 有网络名={named}")

print("\n== CBB 在母图中的实例（Reuse Block 引用方式） ==")
# 找母图里引用 CBB 的实例：title 或属性含 CBB 名
for uuid, title, sch, dt in db.sheets():
    if "_CBB_" in title or "废案" in title:
        continue
    recs = db.sheet_records(uuid)
    if not recs:
        continue
    hits = []
    for a in recs:
        if isinstance(a, list) and len(a) >= 5 and a[0] == "ATTR":
            v = str(a[4])
            if "CBB" in v.upper() and a[3] in ("Name", "Designator", "Value"):
                hits.append((a[3], v[:60]))
    if hits:
        print(f"[{title}] CBB 引用:", hits[:4])
