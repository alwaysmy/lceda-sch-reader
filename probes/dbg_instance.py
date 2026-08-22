"""INSTANCE 文档深挖：CBB 实例→模板页唯一映射 + 成员母图位号映射。"""
import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db = lr.Epro2DB(V3)

# 收集全部 INSTANCE 文档
inst_docs = []
for u, d in db._docs.items():
    if d["docType"] != "INSTANCE":
        continue
    attrs = []
    for ln in db._iter_doc_lines(u):
        if '"INSTANCE_ATTR"' not in ln[:24]:
            continue
        h = db._jl(ln.partition("||")[0])
        b = db._jl(ln.partition("||")[2].rstrip("|"))
        if h and b:
            attrs.append((h.get("id"), b))
    inst_docs.append((u, attrs))

print(f"INSTANCE 文档数: {len(inst_docs)}")
print("\n== uuid 解码（<sch>_$<page>~<instId>_$<srcPage>） ==")
parsed = []
for u, attrs in inst_docs:
    parts = u.split("_$")
    sch = parts[0]
    page_inst = parts[1].split("~") if len(parts) > 1 else ["", ""]
    page = page_inst[0]
    inst_cid = page_inst[1] if len(page_inst) > 1 else ""
    src = parts[2] if len(parts) > 2 else ""
    parsed.append((sch, page, inst_cid, src, attrs))
for p in parsed[:5]:
    print(f"  sch={p[0][:12]} page={p[1][:12]} inst={p[2][:12]} "
          f"src={p[3][:12]} 成员数={len(p[4])}")

print("\n== 单个 INSTANCE 的 INSTANCE_ATTR 明细 ==")
u, attrs = inst_docs[0]
for aid, b in attrs[:8]:
    print(f"   id={aid}: {json.dumps(b, ensure_ascii=False)[:120]}")

print("\n== INSTANCE_ATTR.id 是否为模板页内元件 cid ==")
# 取 srcPage 的模板页元件 cid 集合对比
src_pages = collections.Counter(p[3] for p in parsed)
print("srcPage 分布:", {k[:12]: v for k, v in src_pages.items()})
for u, attrs in inst_docs:
    parts = u.split("_$")
    src = parts[2] if len(parts) > 2 else ""
    if not src or src not in db._docs:
        continue
    tmpl_cids = set()
    for ln in db._iter_doc_lines(src):
        if '"COMPONENT"' in ln[:20]:
            h = db._jl(ln.partition("||")[0])
            if h:
                tmpl_cids.add(h.get("id"))
    attr_ids = {aid for aid, _ in attrs}
    inter = attr_ids & tmpl_cids
    print(f"  src={src[:12]}: INSTANCE_ATTR ids={len(attr_ids)}, "
          f"模板元件={len(tmpl_cids)}, 交集={len(inter)}")
    if inter:
        # 抽一个交集成员对照位号
        aid = next(iter(inter))
        desig = dict((a, b) for a, b in attrs).get(aid, {})
        print(f"    例: {aid} -> {json.dumps(desig, ensure_ascii=False)[:100]}")
    break

print("\n== inst_cid 是否等于母图上 CBBn 实例的 COMPONENT id ==")
# 母图 ControlDAC_A 上 CBB6 的 cid=c5f6beafb1e88061（已知）
hit = [p for p in parsed if p[2] == "c5f6beafb1e88061"]
print("  c5f6beafb1e88061 命中:", [(p[0][:10], p[1][:10], p[3][:10],
      len(p[4])) for p in hit])
