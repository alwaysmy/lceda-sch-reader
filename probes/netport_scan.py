import base64, collections, gzip, io, json, sqlite3, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
conn = sqlite3.connect(f"file:{NEW}?mode=ro", uri=True)

def decompress(ds):
    if not ds:
        return ""
    s = ds[6:] if isinstance(ds, str) and ds.startswith("base64") else ds
    try:
        data = base64.b64decode(s)
    except Exception:
        return ""
    try:
        return gzip.decompress(data).decode("utf-8")
    except Exception:
        return data.decode("utf-8", errors="replace")

# 符号 docType -> 类型名
sym = {}
for u, dt, t, desc in conn.execute(
        "SELECT uuid, docType, title, description FROM components").fetchall():
    sym[u] = (dt, t, desc)
TYPE = {2: "Part", 4: "Ftype", 17: "Block", 18: "NetFlag",
        19: "NetPort", 20: "Sheet", 21: "NoneElec", 22: "Short"}

# 页内无 title 的 COMPONENT 实例统计
comp_inst = collections.Counter()
for u, t, dt, ds in conn.execute(
        "SELECT uuid, display_title, docType, dataStr FROM documents WHERE docType=1").fetchall():
    text = decompress(ds)
    comps = {}
    for ln in text.splitlines():
        if not ln.startswith('["COMPONENT"'):
            continue
        try:
            a = json.loads(ln)
            comps[a[1]] = {"title": a[2] if len(a) > 2 else ""}
        except Exception:
            pass
        if ln.startswith('["ATTR"'):
            try:
                a = json.loads(ln)
                if a[3] == "Symbol" and a[2] in comps:
                    comps[a[2]]["sym"] = a[4]
            except Exception:
                pass
    for cid, c in comps.items():
        if not c.get("title"):
            dt2, name, desc = sym.get(c.get("sym"), (None, "?", "?"))
            comp_inst[TYPE.get(dt2, f"type{dt2}")] += 1
print("== 页内无 title 实例的符号类型分布 ==")
for k, n in comp_inst.most_common():
    print(f"  {k:10s} {n}")

# Global Net Name 挂在什么实例上（parentId -> 实例类型）
gnn = collections.Counter()
gnn_sample = []
for u, t, dt, ds in conn.execute(
        "SELECT uuid, display_title, docType, dataStr FROM documents WHERE docType=1").fetchall():
    comps = {}
    syms = {}
    for ln in decompress(ds).splitlines():
        try:
            a = json.loads(ln)
        except Exception:
            continue
        if a[0] == "COMPONENT":
            comps[a[1]] = a[2] if len(a) > 2 else ""
        elif a[0] == "ATTR" and len(a) >= 5:
            if a[3] == "Symbol" and a[2] in comps:
                syms[a[2]] = a[4]
            elif a[3] in ("NET", "Global Net Name"):
                parent = a[2]
                is_comp = parent in comps
                if is_comp:
                    st = sym.get(syms.get(parent), (None,))[0]
                    gnn[f"COMPONENT/{TYPE.get(st, st)}"] += 1
                else:
                    gnn["non-comp"] += 1
                if len(gnn_sample) < 6:
                    gnn_sample.append((a[3], a[4], parent, "comp" if is_comp else "wire/other"))
print("\n== NET/Global Net Name 挂载对象 ==")
for k, n in gnn.most_common():
    print(f"  {k:20s} {n}")
for s in gnn_sample:
    print("  sample:", s)

conn.close()
