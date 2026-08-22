"""提取全部 INSTANCE 文档的成员位号，按母图页分组，标注模板来源。"""
import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes\full_decrypted.epru",
           encoding="utf-8", errors="replace").read()
lines = src.split("\n")

# 解析全部文档（保留上下文关系）
docs = {}
doc_order = []
cur_uuid = None
for ln in lines:
    head, sep, body = ln.partition("||")
    body = body.rstrip("|")
    try:
        h = json.loads(head)
    except Exception:
        continue
    t = h.get("type")
    try:
        b = json.loads(body)
    except Exception:
        b = None
    
    if t == "DOCHEAD" and b:
        cur_uuid = b.get("uuid","")
        dt = b.get("docType","")
        if cur_uuid not in docs:
            docs[cur_uuid] = {"docType": dt, "meta": None, "inst_attrs": [], "lines": []}
        docs[cur_uuid]["lines"].append(ln)
    elif cur_uuid and cur_uuid in docs:
        if t == "META" and b:
            old = docs[cur_uuid].get("meta")
            if not old or h.get("ticket",0) >= 0:
                docs[cur_uuid]["meta"] = b
        elif t == "INSTANCE_ATTR" and b:
            docs[cur_uuid]["inst_attrs"].append(b)
    
for u in docs:
    if not docs[u].get("meta"):
        # 从行里找 META
        for ln in docs[u]["lines"]:
            if '"META"' in ln[:16]:
                try:
                    b = json.loads(ln.partition("||")[2].rstrip("|"))
                    docs[u]["meta"] = b
                except:
                    pass
                break

# 获取标题映射
def get_title(uuid):
    m = docs.get(uuid, {}).get("meta")
    return (m or {}).get("title") or uuid[:12]

# BOARD uuid→title
board_map = {}
for u, d in docs.items():
    if d["docType"] == "BOARD" and d["meta"]:
        board_map[u] = d["meta"].get("title","")

# 找全部 INSTANCE 并解析
print("=" * 70)
print("CBB 实例的母图位号（从解密后的 epru 提取）")
print("=" * 70)

for u, d in sorted(docs.items()):
    if d["docType"] != "INSTANCE" or not d["inst_attrs"]:
        continue
    
    parts = u.split("_$")
    sch_uuid = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    page_inst = rest.split("~", 1)
    page_uuid = page_inst[0]
    inst_cid = page_inst[1] if "~" in parts[1] else ""
    src_page = parts[2] if len(parts) > 2 else ""
    
    sch_title = get_title(sch_uuid)
    src_title = get_title(src_page)
    page_meta = docs.get(page_uuid, {}).get("meta") or {}
    page_title = page_meta.get("title") or "?"
    
    desigs = sorted([a.get("Designator","") for a in d["inst_attrs"]
                     if a.get("Designator")])
    
    print(f"\n板: {sch_title}")
    print(f"  页: {page_title}")
    print(f"  模板: {src_title}")
    print(f"  成员 ({len(desigs)}):")
    for dsg in desigs:
        print(f"    {dsg}")
