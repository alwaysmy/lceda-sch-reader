"""精确核对：从 full_decrypted.epru 提取 INSTANCE_ATTR 的完整映射，
对照 netlist 中 CBB6/CBB7 展开条目的位号，验证母图位号是否正确。"""
import io, sys, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes\full_decrypted.epru",
           encoding="utf-8", errors="replace").read()
lines = src.split("\n")

# 解析全部 INSTANCE 文档（正确处理 uuid 编码格式）
inst_docs = []
cur = None  # (uuid, attrs)
for ln in lines:
    if '"DOCHEAD"' in ln[:30]:
        # 关闭上一个
        if cur and cur[2]:
            inst_docs.append(cur)
        cur = None
    if '"INSTANCE"' in ln[:20] or '"docType":"INSTANCE"' in ln:
        head, _, body = ln.partition("||")
        try:
            b = json.loads(body.rstrip("|"))
            if b.get("docType") == "INSTANCE":
                cur = [b.get("uuid",""), {}, "INSTANCE"]
                continue
        except: pass
    elif '"INSTANCE_ATTR"' in ln[:24] and cur:
        try:
            body = ln.partition("||")[2].rstrip("|")
            b = json.loads(body)
            if isinstance(b, dict) and b.get("Designator"):
                cur[1][b["Designator"]] = True  # 母图位号列表
        except: pass
    # 也检查是否有普通 ATTR 带 Designator key
    elif '"Designator"' in ln and cur:
        head, _, body = ln.partition("||")
        try:
            h = json.loads(head)
            b = json.loads(body.rstrip("|"))
            if b.get("key") == "Designator":
                cur[1][h.get("id","?")] = b.get("value","?")
        except: pass

if cur and cur[2]:
    inst_docs.append(cur)

print(f"INSTANCE 文档总数: {len(inst_docs)}")

# 解析 uuid 获取映射
for uuid, desigs, _ in inst_docs:
    parts = uuid.split("_$")
    sch = parts[0]
    page_inst = parts[1].split("~", 1) if len(parts) > 1 else ["",""]
    page = page_inst[0]
    inst_cid = page_inst[1] if len(page_inst) > 1 else ""
    src_page = parts[2] if len(parts) > 2 else ""
    
    print(f"\n== INSTANCE ==")
    print(f"  sch={sch[:16]}")
    print(f"  母图页={page[:16]}")  
    print(f"  实例cid={inst_cid[:16]}")
    print(f"  模板页={src_page[:16]}")
    
    # 获取模板页标题
    # 在 epru 中找该 uuid 的 META title
    
    print(f"  成员母图位号 ({len(desigs)} 个): {sorted(desigs.keys(), key=lambda x: (len(x), x))}")

# 现在对比 CBB6 展开结果
print("\n" + "="*60)
print("CBB6 展开条目 vs INSTANCE_ATTR 母图位号对比")
print("="*60)

# 从 netlist 获取 CBB6 的展开成员
import subprocess
R = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py"
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
p = subprocess.run([sys.executable, R, "--eprj", E, "--json", "netlist"],
                   capture_output=True, text=True, encoding="utf-8")
rows = json.loads(p.stdout)

cbb6_nets = {}   # member → nets
for r in rows:
    for c in r["components"]:
        if c.startswith("CBB6."):
            member = c.split(".", 1)[1]
            cbb6_nets.setdefault(member, []).append(r["net"])

print(f"\nCBB6 展开成员 ({len(cbb6_nets)}):")
for m in sorted(cbb6_nets):
    print(f"  {m}")

cbb7_nets = {}
for r in rows:
    for c in r["components"]:
        if c.startswith("CBB7."):
            member = c.split(".", 1)[1]
            cbb7_nets.setdefault(member, []).append(r["net"])
print(f"\nCBB7 展开成员 ({len(cbb7_nets)}):")
for m in sorted(cbb7_nets):
    print(f"  {m}")
