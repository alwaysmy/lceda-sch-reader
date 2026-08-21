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

# 1) 格式抽样：第一页原始行格式
docs = conn.execute(
    "SELECT uuid, display_title, docType, dataStr FROM documents WHERE docType=1 "
    "ORDER BY sheet_id LIMIT 3").fetchall()
print("== dataStr 行格式抽样 ==")
u0, t0, dt0, ds0 = docs[0]
text = decompress(ds0)
lines = text.splitlines()
print(f"页: {t0} ({u0[:8]})  共 {len(lines)} 行")
for ln in lines[:6]:
    print("  ", ln[:140])
print("  最后2行:")
for ln in lines[-2:]:
    print("  ", ln[:140])

# 2) 全工程图元类型统计（所有原理图页）
print("\n== 全工程图元类型统计 ==")
kind_count = collections.Counter()
sample = {}
for u, t, dt, ds in conn.execute(
        "SELECT uuid, display_title, docType, dataStr FROM documents WHERE docType=1").fetchall():
    text = decompress(ds)
    for ln in text.splitlines():
        if "||" in ln:
            try:
                outer = json.loads(ln.split("||", 1)[0])
                kind_count[outer.get("type")] += 1
            except Exception:
                pass
        else:
            try:
                arr = json.loads(ln)
                if isinstance(arr, list) and arr:
                    kind_count[arr[0]] += 1
            except Exception:
                pass
for k, n in kind_count.most_common():
    print(f"  {k:16s} {n}")

# 3) 非原理图文档类型
print("\n== 非原理图文档 (docType != 1) ==")
for u, t, dt, ds in conn.execute(
        "SELECT uuid, display_title, docType, dataStr FROM documents WHERE docType!=1").fetchall():
    print(f"  docType={dt}  {t}  ({len(ds or '')} bytes)")

# 4) 总线/BUS 相关
text_all = ""
for u, t, dt, ds in conn.execute(
        "SELECT uuid, display_title, docType, dataStr FROM documents WHERE docType=1").fetchall():
    text_all += decompress(ds) + "\n"
print("\n== BUS/BUSENTRY/NET 关键词 ==")
for kw in ("BUS", "BUSENTRY", "NetFlag", "NetPort", "TABLE", "OBJ"):
    print(f"  {kw}: {text_all.count(chr(34)+kw+chr(34))} 次")

conn.close()
