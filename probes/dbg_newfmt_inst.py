"""新版 .epro2 的 CBB 实例完整映射 + netlist 验证。"""
import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

X = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-22.epro2"
db = lr.Epro2DB(X)

# ① INSTANCE 映射（从 cbb_instances()）
inst = db.cbb_instances()
print("== cbb_instances() 返回 ==")
print(f"映射数: {len(inst)}")

# ② 直接遍历 _docs 中的 INSTANCE 文档
print("\n== INSTANCE 文档详情 ==")
for u, d in sorted(db._docs.items()):
    if d["docType"] != "INSTANCE":
        continue
    parts = u.split("_$")
    sch = parts[0]
    page = parts[1].split("~")[0] if len(parts) > 1 and "~" in parts[1] else "?"
    inst_cid = parts[1].split("~")[1] if len(parts) > 1 and "~" in parts[1] else "?"
    src_page = parts[2] if len(parts) > 2 else "?"
    
    # 获取页标题
    pm = db._meta.get(page) or {}
    pt = pm.get("title") or "?"
    
    # 收集成员
    members = {}
    for ln in db._iter_doc_lines(u):
        if '"INSTANCE_ATTR"' not in ln[:24]:
            continue
        head, _, body = ln.partition("||")
        h = db._jl(head)
        b = db._jl(body.rstrip("|"))
        if h and b and isinstance(b, dict):
            mid_val = h.get("id", "")
            desig = b.get("Designator", "")
            if desig:
                members[mid_val] = desig
    
    # 找模板页标题
    sm = db._meta.get(src_page) or {}
    src_title = sm.get("title") or src_page[:16]
    
    print(f"\n  页={pt} ({page[:12]})")
    print(f"  实例 cid={inst_cid[:12]}")
    print(f"  模板页 uuid={src_page[:16]} title={src_title}")
    print(f"  成员 ({len(members)}): {', '.join(sorted(members.values()))}")

# ③ netlist 验证
import subprocess
p = subprocess.run([sys.executable,
                    r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py",
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

print("\n== netlist CBB 展开成员 ==")
for prefix in sorted(cbb_members):
    print(f"  {prefix}: {', '.join(sorted(cbb_members[prefix]))}")
