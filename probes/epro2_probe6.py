import io, sys, json, zipfile, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
z = zipfile.ZipFile(E)
data = z.read("Piezo_Driver.epru").decode("utf-8", errors="replace")

def jl(s):
    try:
        return json.loads(s)
    except Exception:
        return None

# 第一遍：文档边界 + 目标页选取
doc_ranges = {}   # uuid -> [docType, start_idx]
order = []
lines = data.split("\n")
for i, ln in enumerate(lines):
    if '"DOCHEAD"' not in ln[:30]:
        continue
    h = jl(ln.partition("||")[0])
    b = jl(ln.partition("||")[2].rstrip("|")) if h else None
    if h and h.get("type") == "DOCHEAD" and b:
        u = b.get("uuid")
        doc_ranges[u] = [b.get("docType"), i]
        order.append(u)

print("文档总数:", len(doc_ranges))

# 找一个有内容的 SCH_PAGE（取 ControlDAC_A）与它的 DOCHEAD/META
target = None
sch_meta = []
page_meta = {}
inst_heads = []
sym17 = []
dev_meta = None
for i, ln in enumerate(lines):
    if '"DOCHEAD"' not in ln[:30]:
        continue
    h = jl(ln.partition("||")[0])
    b = jl(ln.partition("||")[2].rstrip("|"))
    if not b:
        continue
    if b.get("docType") == "SCH_PAGE":
        page_meta[b["uuid"]] = None   # 待填 META
    elif b.get("docType") == "INSTANCE":
        inst_heads.append(b)

# 第二遍：收集 META 与关键样本
cur = None
attr_keys = collections.Counter()
wire_groups = collections.defaultdict(list)
net_attr = None
pin_attr_sample = None
comp_full = None
sym_meta_sample = None
part_ids = set()
sym_uuids = set()
for i, ln in enumerate(lines):
    head, _, body = ln.partition("||")
    h = jl(head)
    if h is None:
        continue
    b = jl(body.rstrip("|"))
    t = h.get("type")
    if t == "DOCHEAD":
        cur = (b or {}).get("docType"), (b or {}).get("uuid")
        continue
    if b is None:
        continue
    dt, du = cur if cur else (None, None)
    if dt == "SCH_PAGE":
        if t == "META":
            page_meta[du] = b
        elif t == "ATTR":
            attr_keys[b.get("key")] += 1
            if b.get("key") in ("NET", "Global Net Name") and net_attr is None:
                net_attr = (du, h.get("id"), b)
        elif t == "COMPONENT" and comp_full is None:
            comp_full = (du, h.get("id"), b)
        elif t == "LINE":
            g = b.get("lineGroup")
            if g:
                wire_groups[g].append((h.get("id"), b))
    elif dt == "SYMBOL":
        if t == "META" and sym_meta_sample is None:
            sym_meta_sample = (du, b)
        if t == "PART":
            part_ids.add(h.get("id"))
        sym_uuids.add(du)
        if t == "PIN" and pin_attr_sample is None:
            pin_attr_sample = (du, h.get("id"), b)
    elif dt == "DEVICE" and dev_meta is None and t == "META":
        dev_meta = (du, b)

print("\n== SCH_PAGE META 样本（找标题/父级） ==")
n = 0
for u, m in page_meta.items():
    if m and n < 6:
        print(f"  {u[:12]}: {json.dumps(m, ensure_ascii=False)[:220]}")
        n += 1

print("\n== SCH_PAGE 内 ATTR key 分布 top ==")
for k, v in attr_keys.most_common(18):
    print(f"   {k}: {v}")

print("\n== NET 属性样本（挂在 WIRE 上?） ==")
print(" ", json.dumps(net_attr, ensure_ascii=False)[:350] if net_attr else "无")

print("\n== WIRE 几何(LINE lineGroup 分组) 样本 ==")
g = next(iter(wire_groups)) if wire_groups else None
if g:
    print(f"  wire id={g}, 段数={len(wire_groups[g])}")
    for lid, b in wire_groups[g][:3]:
        print(f"    LINE {lid}: startX={b.get('startX')} startY={b.get('startY')} "
              f"endX={b.get('endX')} endY={b.get('endY')}")

print("\n== COMPONENT 完整样本 ==")
print(" ", json.dumps(comp_full, ensure_ascii=False)[:400])

print("\n== SYMBOL META 样本（symbolType?） ==")
print(" ", json.dumps(sym_meta_sample, ensure_ascii=False)[:300])
print("  partId 命名空间样例:", list(part_ids)[:4])
print("  SYMBOL doc uuid 样例:", [u[:16] for u in list(sym_uuids)[:4]])

print("\n== PIN 样本 ==")
print(" ", json.dumps(pin_attr_sample, ensure_ascii=False)[:250])

print("\n== DEVICE META 样本 ==")
print(" ", json.dumps(dev_meta, ensure_ascii=False)[:350])

print("\n== INSTANCE DOCHEAD 样本 ==")
for b in inst_heads[:3]:
    print("  ", json.dumps(b, ensure_ascii=False)[:250])