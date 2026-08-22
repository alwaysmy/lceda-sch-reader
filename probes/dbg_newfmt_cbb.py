"""从新版 .epro2 提取全部 CBB 实例的母图位号映射。"""
import io, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

X = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-22.epro2"
db = lr.Epro2DB(X)

inst = db.cbb_instances()
print(f"INSTANCE 映射数: {len(inst)}")

# 获取页标题
page_titles = {}
for u, p in db._pages.items():
    page_titles[u] = p.get("title", "?")

# 获取模板标题
tmpl_titles = {}
for u, d in db._docs.items():
    if d["docType"] == "SYMBOL":
        m = db._meta.get(u) or {}
        if m.get("docType") == 17:
            tmpl_titles[u] = m.get("title", "?")

# 按模板分组展示全部实例
by_tmpl = {}
for (page_uuid, inst_cid), info in sorted(inst.items()):
    src = info.get("src") or info.get("_src") or ""
    members = info.get("members") or {}
    # 找模板名
    tmpl_name = tmpl_titles.get(src_page if isinstance(src_page, str) else "", "?")
    by_tmpl.setdefault(tmpl_name, []).append({
        "page": page_titles.get(page_uuid, page_uuid[:12]),
        "cid": inst_cid,
        "members": members
    })

for tmpl_name, insts in sorted(by_tmpl.items()):
    print(f"\n{'='*60}")
    print(f"模板: {tmpl_name}")
    print(f"实例数: {len(insts)}")
    for inst in insts:
        print(f"\n  页: {inst['page']}")
        print(f"  实例 cid: {inst['cid'][:16]}")
        print(f"  母图成员位号:")
        for mcid, mdes in sorted(inst["members"].items(), key=lambda x: x[1]):
            print(f"    {mdes}")

# 同时用 netlist 验证展开结果
print("\n" + "="*60)
print("netlist 展开条目验证")
p = __import__('subprocess').run(
    [sys.executable, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py",
     "--eprj", X, "--json", "netlist"],
    capture_output=True, text=True, encoding="utf-8")
rows = json.loads(p.stdout)

cbb_members = collections.defaultdict(set)
for r in rows:
    for c in r["components"]:
        if "." in c:
            prefix, member = c.split(".", 1)
            if prefix.startswith("CBB"):
                cbb_members[prefix].add(member)

for prefix in sorted(cbb_members):
    print(f"\n  {prefix} ({len(cbb_members[prefix])} 成员): "
          f"{', '.join(sorted(cbb_members[prefix]))}")
