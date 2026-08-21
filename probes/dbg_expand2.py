import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db = lr.Epro2DB(V3)
page = next(u for u, t, s, dt in db.sheets()
            if t == "quadPizeoDriver_RevA::ControlDAC_A")
sheet = lr.parse_sheet(db, page)
pinc = lr._collect_pinmap_data(db, sheet, page)
cp, ws, pw, ep = pinc

# 手动执行 _expand_cbb 前置步骤
insts = {}
for key, plist in cp.items():
    des = key if isinstance(key, str) else key[0]
    for p in plist:
        if p.get("sym_type") == 17:
            insts.setdefault(des, set()).add(p.get("pin"))
print("CBB 实例:", {k: len(v) for k, v in insts.items()})

sig = lr._cbb_sig(db)
print("sig 页数:", len(sig))
tmpl = lr._resolve_cbb_target(db, sig, "_CBB_MAX5318_2L")
print("_resolve_cbb_target(_CBB_MAX5318_2L) ->", tmpl)

if tmpl:
    t_dom = lr._cbb_dom(db, tmpl)
    print("t_dom 引脚:", len(t_dom), "有名:",
          sum(1 for v in t_dom.values() if v))
    # 模板端口
    t_sheet = lr.parse_sheet(db, tmpl)
    port_titles = {f"PORT{c['cid']}": c["title"]
                   for c in t_sheet["components"]
                   if not c.get("designator") and c.get("title")}
    print("模板 PORT 数:", len(port_titles),
          list(port_titles.values())[:4])
    port_net = {}
    for (tdes, tpin), net in t_dom.items():
        t = port_titles.get(tdes)
        if t:
            for tok in net.split(","):
                if tok:
                    port_net.setdefault(t, set()).add(tok)
    print("port_net 样例:", dict(list(port_net.items())[:4]))

    # 实例父网络
    pin_parent = {}
    for key, plist in cp.items():
        des = key if isinstance(key, str) else key[0]
        if des != "CBB6":
            continue
        dom = lr.resolve_nets_by_domain(db, sheet, cp, ws, pw, ep)
        for p in plist:
            k = p.get("key") or p.get("pin")
            toks = {t for t in dom.get((des, k), "").split(",") if t}
            if toks:
                pin_parent[p["pin"]] = toks
    print("CBB6 pin_parent:", {k: sorted(v) for k, v in
                               list(pin_parent.items())[:4]})
