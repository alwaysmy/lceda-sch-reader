"""核对推断项：① V3 NO_CONNECT 匹配规则 ② OffPage(25) 实例行为
③ port_net 主路径覆盖率（fallback 触发率）。"""
import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db = lr.Epro2DB(V3)

print("== ① V3 NO_CONNECT：raw parentId 形态 vs 工具匹配 ==")
raw_nc = []   # (page, parentId, val)
for u, d in db._docs.items():
    if d["docType"] != "SCH_PAGE":
        continue
    for ln in db._iter_doc_lines(u):
        if '"NO_CONNECT"' not in ln:
            continue
        b = db._jl(ln.partition("||")[2].rstrip("|"))
        if b:
            raw_nc.append((u, b.get("parentId"), b.get("value")))
print(f"raw NO_CONNECT 数: {len(raw_nc)}")
print("  parentId 样例:", [p[1] for p in raw_nc[:6]])
print("  value 分布:", collections.Counter(str(p[2]) for p in raw_nc))
# parentId 是否 = 某元件cid+某PIN id 复合？取一页验证
page_cids = {}
u0 = raw_nc[0][0]
comp_ids = set()
pin_ids = set()
for ln in db._iter_doc_lines(u0):
    head, _, body = ln.partition("||")
    h = db._jl(head)
    if not h:
        continue
    if h.get("type") == "COMPONENT":
        comp_ids.add(h.get("id"))
    elif h.get("type") == "PIN":
        pin_ids.add(h.get("id"))
hits = sum(1 for p in raw_nc if p[0] == u0)
print(f"  页 {u0[:10]}: NO_CONNECT {hits} 条；"
      f"parentId 前缀命中元件? 逐条检查：")
ok = bad = 0
for p in raw_nc:
    if p[0] != u0:
        continue
    pid = p[1] or ""
    # 复合规则：找 cid 使得 cid+pinid == pid（V2 规则），或 pid 本身是引脚级 id
    m = [c for c in comp_ids if pid.startswith(c)]
    if m:
        ok += 1
    else:
        bad += 1
        if bad <= 3:
            print(f"     未命中复合规则: parentId={pid[:24]}")
print(f"   复合规则命中 {ok}, 未命中 {bad}")

# 工具解析出的 not_connected 数
total_nc = 0
for u, t, s, dt in db.sheets():
    if dt != 1:
        continue
    sh = lr.parse_sheet(db, u)
    if not sh:
        continue
    pinc = lr._collect_pinmap_data(db, sh, u)
    if not pinc:
        continue
    cp = pinc[0]
    for k, plist in cp.items():
        total_nc += sum(1 for p in plist if p.get("no_connect"))
print(f"  工具解析 not_connected 总数: {total_nc} (raw {len(raw_nc)})")

print("\n== ② OffPage(docType=25) 实例调查 ==")
offpage_syms = {u: (db._meta.get(u) or {}).get("title")
                for u, d in db._docs.items()
                if d["docType"] == "SYMBOL"
                and (db._meta.get(u) or {}).get("docType") == 25}
print("  OffPage 符号:", offpage_syms)
uses = 0
for u, d in db._docs.items():
    if d["docType"] != "SCH_PAGE":
        continue
    for ln in db._iter_doc_lines(u):
        if '"COMPONENT"' not in ln[:20]:
            continue
        b = db._jl(ln.partition("||")[2].rstrip("|"))
        if b and b.get("partId") in offpage_syms:
            uses += 1
print(f"  页上 OffPage 实例数: {uses}")

print("\n== ③ port_net 主路径覆盖率（模板端口 dom 命中率） ==")
# 以 MAX5318 模板页为例
tmpl = next(u for u, t, s, dt in db.sheets()
            if t == "_CBB_MAX5318_2L::P1")
t_sheet = lr.parse_sheet(db, tmpl)
t_pinc = lr._collect_pinmap_data(db, t_sheet, tmpl)
cp, ws, pw, ep = t_pinc
t_dom = lr.resolve_nets_by_domain(db, t_sheet, cp, ws, pw, ep,
                                  _cbb_depth=1)
ports = [c for c in t_sheet["components"]
         if not c.get("designator")
         and (c.get("attrs") or {}).get("Name")]
hit = miss = 0
missed = []
for c in ports:
    nm = c["attrs"]["Name"]
    key = (f"PORT{c['cid']}", None)
    plist = cp.get((f"PORT{c['cid']}", c["cid"]))
    if not plist:
        miss += 1
        missed.append(nm)
        continue
    got = False
    for p in plist:
        v = t_dom.get((f"PORT{c['cid']}", p.get("key") or p.get("pin")), "")
        if v:
            got = True
            break
    if got:
        hit += 1
    else:
        miss += 1
        missed.append(nm)
print(f"  模板端口 {len(ports)}: dom 主路径命中 {hit}, 未命中 {miss} {missed[:6]}")
