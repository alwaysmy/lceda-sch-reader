"""精确输出 quadPizeoDriver_RevA 各页的 CBB 实例内部器件母图位号。"""
import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

X = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-22.epro2"
db = lr.Epro2DB(X)

# 找 quadPizeoDriver_RevA（无后缀）对应的 sch uuid
# 从 BOARD 文档 META 找
target_sch = None
for u, d in db._docs.items():
    if d["docType"] == "BOARD":
        m = db._meta.get(u) or {}
        if m.get("title") == "quadPizeoDriver_RevA":
            # 找对应的 SCH
            for su, sd in db._docs.items():
                if sd["docType"] == "SCH":
                    sm = db._meta.get(su) or {}
                    if sm.get("board") == u:
                        target_sch = su
                        break
            break

print(f"目标板 SCH uuid: {target_sch}")

# 找该 SCH 下的全部 INSTANCE 文档，按页分组
by_page = collections.defaultdict(list)
for u, d in db._docs.items():
    if d["docType"] != "INSTANCE":
        continue
    parts = u.split("_$")
    if len(parts) < 3 or not parts[0].startswith(target_sch[:12]):
        continue
    page_inst = parts[1].split("~", 1)
    page = page_inst[0]
    inst_cid = page_inst[1] if len(page_inst) > 1 else "?"
    
    members = []
    for ln in db._iter_doc_lines(u):
        if '"INSTANCE_ATTR"' not in ln[:24]:
            continue
        head, _, body = ln.partition("||")
        h = db._jl(head)
        b = db._jl(body.rstrip("|"))
        if h and b and isinstance(b, dict) and b.get("Designator"):
            members.append(b["Designator"])
    
    # 找模板页
    src_page = parts[2] if len(parts) > 2 else ""
    sm = db._meta.get(src_page) or {}
    src_title = sm.get("title") or src_page[:16]
    
    by_page[page].append({
        "inst_cid": inst_cid,
        "members": sorted(members),
        "src_page": src_page,
        "src_title": src_title
    })

# 输出
page_titles = {u: (db._meta.get(u) or {}).get("title", "?") 
               for u in by_page}

for page_uuid in sorted(by_page):
    pt = page_titles.get(page_uuid, "?")
    print(f"\n{'='*60}")
    print(f"母图页: {pt}")
    
    for inst in sorted(by_page[page_uuid], key=lambda x: x["inst_cid"]):
        src_t = inst["src_title"]
        print(f"\n  实例 cid={inst['inst_cid'][:12]} → 模板: {src_t}")
        print(f"  内部器件母图位号 ({len(inst['members'])} 个):")
        for m in inst["members"]:
            print(f"    {m}")
