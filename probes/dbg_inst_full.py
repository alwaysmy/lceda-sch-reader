"""从解密后的 epru 中提取全部 INSTANCE_ATTR 记录（含完整上下文）。
并按母图页分组展示，标注对应的模板页。"""
import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes\full_decrypted.epru",
           encoding="utf-8", errors="replace").read()
lines = src.split("\n")

# 解析全部文档段
docs = []  # {uuid, docType, meta, attrs, instance_attrs}
cur = None
for ln in lines:
    head, sep, body = ln.partition("||")
    body = body.rstrip("|")
    try:
        h = json.loads(head)
    except Exception:
        continue
    t = h.get("type")
    
    if t == "DOCHEAD":
        # 关闭上一个
        if cur:
            docs.append(cur)
        b = None
        try: b = json.loads(body)
        except: pass
        cur = {"uuid": (b or {}).get("uuid",""),
               "docType": (b or {}).get("docType",""),
               "meta": None, "attrs": [], "inst_attrs": []}
        continue
    
    if not cur:
        continue
    
    try:
        b = json.loads(body)
    except Exception:
        continue
    
    if t == "META":
        cur["meta"] = b
    elif t == "INSTANCE_ATTR":
        cur["inst_attrs"].append(b)
    elif t == "ATTR":
        cur["attrs"].append(b)

if cur:
    docs.append(cur)

# 筛选 INSTANCE 文档
print("=" * 70)
print("全部 INSTANCE 文档（CBB 实例的母图位号映射）")
print("=" * 70)

# 也收集 BOARD/SCH/PAGE 标题用于交叉引用
board_titles = {}
sch_titles = {}
page_info = {}
for d in docs:
    if d["docType"] == "BOARD" and d["meta"]:
        board_titles[d["uuid"]] = d["meta"].get("title", "?")
    elif d["docType"] == "SCH" and d["meta"]:
        sch_titles[d["uuid"]] = d["meta"]
    elif d["docType"] == "SCH_PAGE" and d["meta"]:
        page_info[d["uuid"]] = d["meta"]

for d in docs:
    if d["docType"] != "INSTANCE":
        continue
    uuid = d["uuid"]
    parts = uuid.split("_$")
    sch_uuid = parts[0]
    page_inst = parts[1].split("~", 1) if len(parts) > 1 else ["", ""]
    page_uuid = page_inst[0]
    inst_cid = page_inst[1] if len(page_inst) > 1 else ""
    src_page_uuid = parts[2] if len(parts) > 2 else ""
    
    # 获取标题
    sch_m = None
    for dd in docs:
        if dd["uuid"] == sch_uuid and dd["docType"] == "SCH":
            sch_m = dd["meta"]
            break
    sch_name = (sch_m or {}).get("name") or sch_uuid[:16]
    board_name = "?"
    for bu, bt in board_titles.items():
        pass  # 需要板↔SCH 映射
    
    page_meta = None
    for dd in docs:
        if dd["uuid"] == page_uuid and dd["docType"] == "SCH_PAGE":
            page_meta = dd["meta"]
            break
    page_title = (page_meta or {}).get("title") or page_uuid[:12]
    
    src_meta = None
    for dd in docs:
        if dd["uuid"] == src_page_uuid and dd["docType"] == "SCH_PAGE":
            src_meta = dd["meta"]
            break
    src_title = (src_meta or {}).get("title") or src_page_uuid[:12] or "(外部)"
    
    print(f"\n{'─'*60}")
    print(f"SCH: {sch_name}")
    print(f"母图页: {page_title}")
    print(f"实例 cid: {inst_cid[:20]}")
    print(f"模板页: {src_title} ({src_page_uuid[:16]})")
    print(f"成员数: {len(d['inst_attrs'])}")
    
    desigs = sorted([a.get("Designator","") for a in d["inst_attrs"] 
                     if a.get("Designator")])
    print(f"母图位号: {', '.join(desigs)}")

# 也列出全部 BOARD 标题
print(f"\n{'='*60}")
print("全部板:")
for u, t in sorted(board_titles.items(), key=lambda x: x[1]):
    print(f"  {t}")

# SCH↔BOARD 映射
print("\nSCH→Board 映射:")
for su, sm in sorted(sch_titles.items()):
    b_uuid = sm.get("board")
    bt = board_titles.get(b_uuid, "?")
    print(f"  {bt:30s} ← {sm.get('name','?')}")
