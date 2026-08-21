import io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader")
import lceda_reader as lr

V3 = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
db = lr.Epro2DB(V3)
page = None
for u, t, s, dt in db.sheets():
    if t == "quadPizeoDriver_RevA::ControlDAC_A":
        page = u
        break

# U41 的全部原始 ATTR（含所有 key）
print("== U41 (cid?) 原始 ATTR ==")
cid = None
for r in db.sheet_records(page):
    if r[0] == "ATTR" and len(r) >= 5 and r[3] == "Designator" and r[4] == "U41":
        cid = r[2]
        break
print("cid =", cid)
for r in db.sheet_records(page):
    if r[0] == "ATTR" and len(r) >= 5 and r[2] == cid:
        print(f"   {r[3]} = {str(r[4])[:50]!r}")

# 全页组件：有/无 Name attr 统计
recs = db.sheet_records(page)
name_ids = {r[2] for r in recs if r[0] == "ATTR" and len(r) >= 5 and r[3] == "Name"}
comp_ids = [r[1] for r in recs if r[0] == "COMPONENT"]
no_name = [c for c in comp_ids if c not in name_ids]
print(f"\n组件 {len(comp_ids)}, 有 Name attr {len(name_ids)}, 无 Name {len(no_name)}")

# 无 Name 的组件的 Designator 与 partId
des_of = {}
partid_of = {}
for r in recs:
    if r[0] == "ATTR" and len(r) >= 5 and r[3] == "Designator":
        des_of[r[2]] = r[4]
for r in recs:
    if r[0] == "COMPONENT" and r[1] in no_name:
        partid_of[r[1]] = r[6] if False else None
# COMPONENT partId 在合成记录里没存——直接看原始行
raw_partid = {}
for ln in db._iter_doc_lines(page):
    if '"COMPONENT"' not in ln[:20]:
        continue
    head, _, body = ln.partition("||")
    h = db._jl(head)
    b = db._jl(body.rstrip("|"))
    if h and b:
        raw_partid[h.get("id")] = b.get("partId")
for c in no_name[:6]:
    print(f"   无Name组件 {des_of.get(c, '?')} partId={raw_partid.get(c)}")

# partId 是否全局唯一映射到 PART？
pid_sample = raw_partid.get(no_name[0]) if no_name else None
if pid_sample:
    hits = []
    for ln in db._lines_of():
        if pid_sample in ln and '"PART"' not in ln[:12]:
            continue
    # 在符号文档里搜该 partId
    sym_u = None
    for r in recs:
        if r[0] == "ATTR" and len(r) >= 5 and r[2] == no_name[0] and r[3] == "Symbol":
            sym_u = r[4]
            break
    print(f"   无Name组件 Symbol={sym_u}")
    sp = db.symbol_pins(sym_u)
    print(f"   符号 parts={sp['parts'] if sp else None}")

# Device uuid 形态 vs DEVICE 文档 uuid
dev_attrs = [r[4] for r in recs if r[0] == "ATTR" and len(r) >= 5 and r[3] == "Device"]
dev_doc_uuids = {u for u, d in db._docs.items() if d["docType"] == "DEVICE"}
inter = set(dev_attrs) & dev_doc_uuids
print(f"\n实例 Device 值样例: {dev_attrs[:3]}")
print(f"DEVICE 文档 uuid 样例: {list(dev_doc_uuids)[:3]}")
print(f"直接交集: {len(inter)}/{len(dev_attrs)}")
