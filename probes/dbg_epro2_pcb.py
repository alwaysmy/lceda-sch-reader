"""探针：.epro2 / 解密新版 .eprj2 的 docType 分布 + PCB 文档结构。"""
import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

FILES = [
    (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro2", "Piezo epro2"),
    (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器_backup\涡流传感器_2026-08-10-14-47.epro2", "涡流 epro2"),
]

def probe(db, tag):
    docs = db._docs
    dist = collections.Counter(d["docType"] for d in docs.values())
    print(f"\n== {tag}: 文档数 {len(docs)}, docType 分布: {dict(dist)}")
    # 找 PCB 类文档
    pcb_uuids = [u for u, d in docs.items()
                 if str(d["docType"]).upper() in ("PCB", "3")]
    print(f"PCB 文档 uuid: {[u[:12] for u in pcb_uuids]}")
    for u in pcb_uuids[:2]:
        m = db._meta.get(u) or {}
        print(f"  META: {json.dumps({k: v for k, v in m.items() if k != '_t'}, ensure_ascii=False)[:200]}")
        lines = list(db._iter_doc_lines(u))
        print(f"  行数: {len(lines)}")
        types = collections.Counter()
        for ln in lines[:20000]:
            h = lr.Epro2DB._jl(ln.partition("||")[0])
            if h: types[h.get("type")] += 1
        print(f"  记录类型(前2万行): {dict(types.most_common(20))}")
        # 样例 COMPONENT
        shown = 0
        for ln in lines:
            head, _, body = ln.partition("||")
            h = lr.Epro2DB._jl(head)
            if h and h.get("type") == "COMPONENT":
                b = lr.Epro2DB._jl(body.rstrip("|")) or {}
                print(f"  COMPONENT 样例: head={json.dumps(h, ensure_ascii=False)[:100]}")
                print(f"    body keys={list(b.keys())}")
                print(f"    body={json.dumps(b, ensure_ascii=False)[:400]}")
                shown += 1
                if shown >= 2: break

for p, tag in FILES:
    try:
        db = lr.detect_backend(p)
        if db == "DECRYPT_NEW":
            tmp = lr._decrypt_new_eprj2(p)
            db = lr.Epro2DB(tmp)
            tag += " (解密)"
        else:
            db = db(p)
        probe(db, tag)
    except Exception as e:
        print(f"{tag}: {type(e).__name__}: {e}")
