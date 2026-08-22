"""从 full_decrypted.epru 提取 INSTANCE 文档的母图位号映射。"""
import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes\full_decrypted.epru",
           encoding="utf-8", errors="replace").read()

lines = src.split("\n")

# 找全部 INSTANCE 文档段
inst_docs = []   # (uuid, [INSTANCE_ATTR dicts])
cur_uuid = None
cur_attrs = {}
in_instance = False

for ln in lines:
    if '"DOCHEAD"' in ln[:30]:
        # 新文档开始
        if in_instance and cur_attrs:
            inst_docs.append((cur_uuid, cur_attrs))
        in_instance = False
        cur_attrs = {}
        try:
            head, _, body = ln.partition("||")
            h = json.loads(head)
            b = json.loads(body.rstrip("|"))
            if b.get("docType") == "INSTANCE":
                in_instance = True
                cur_uuid = b.get("uuid", "?")
        except Exception:
            pass
    elif in_instance and '"INSTANCE_ATTR"' in ln[:24]:
        try:
            body = ln.partition("||")[2].rstrip("|")
            b = json.loads(body)
            if b.get("Designator"):
                cur_attrs[len(cur_attrs)] = {"id": len(cur_attrs),
                                              "Designator": b["Designator"]}
        except Exception:
            pass

if in_instance and cur_attrs:
    inst_docs.append((cur_uuid, cur_attrs))

print(f"INSTANCE 文档总数: {len(inst_docs)}")

# 解析 uuid 获取映射关系
parsed = []
for uuid, attrs in inst_docs:
    parts = uuid.split("_$")
    sch = parts[0]
    page = parts[1].split("~")[0] if "~" in parts[1] else ""
    inst_cid = parts[1].split("~")[1] if "~" in parts[1] else ""
    src_page = parts[2] if len(parts) > 2 else ""
    
    members = list(attrs.values())
    parsed.append({
        "sch": sch, "page": page,
        "inst_cid": inst_cid, "src": src_page,
        "members": members
    })

# 按 (sch, page) 分组输出 quadPizeoDriver_RevA_1.1 的 ControlDAC_A
target_sch = "quadPizeoDriver_RevA_1.1"
for p in parsed:
    if not p["members"]:
        continue
    # 查母图页标题
    print(f"\nsch={p['sch'][:20]}")
    print(f"  page={p['page'][:12]}")
    print(f"  src={p['src'][:16]}")
    print(f"  成员数={len(p['members'])}")
    for m in p["members"][:15]:
        print(f"    {m['Designator']}")

# 也统计每个模板页的成员分布
print("\n== 按模板页分组的实例 ==")
by_src = collections.defaultdict(list)
for p in parsed:
    by_src[p["src"]].append(p)
for src_p, ps in sorted(by_src.items()):
    total_members = sum(len(x["members"]) for x in ps)
    print(f"  {src_p[:16]}: {len(ps)} 实例, 共{total_members}成员")
