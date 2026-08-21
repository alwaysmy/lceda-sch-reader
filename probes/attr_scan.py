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

# 1) ATTR key 分布（网络相关 + 全部 top20）
key_count = collections.Counter()
for u, t, dt, ds in conn.execute(
        "SELECT uuid, display_title, docType, dataStr FROM documents WHERE docType=1").fetchall():
    for ln in decompress(ds).splitlines():
        if not ln.startswith('["ATTR"'):
            continue
        try:
            a = json.loads(ln)
            if len(a) >= 5:
                key_count[a[3]] += 1
        except Exception:
            pass
print("== ATTR key 分布 top 30 ==")
for k, n in key_count.most_common(30):
    print(f"  {k:28s} {n}")

print("\n== 网络相关 key ==")
for k, n in sorted(key_count.items()):
    if any(s in k for s in ("NET", "Net", "net", "Name", "NAME")):
        print(f"  {k:28s} {n}")

# 2) components 表 docType/child_tag 分布（找 symbol 文档）
print("\n== components 表 docType 分布 ==")
for r in conn.execute("SELECT docType, COUNT(*) FROM components GROUP BY docType").fetchall():
    print("  docType", r[0], "=", r[1])
print("== components 表 child_tag 分布 ==")
for r in conn.execute(
        "SELECT child_tag, COUNT(*) FROM components GROUP BY child_tag ORDER BY 2 DESC LIMIT 10").fetchall():
    print("  ", r[0], "=", r[1])
print("== devices 表 docType 分布 ==")
for r in conn.execute("SELECT docType, COUNT(*) FROM devices GROUP BY docType").fetchall():
    print("  docType", r[0], "=", r[1])

# 3) 符号类型分布：从 symbols 相关内容查 symbol_type
#    resources 表 filename
print("\n== resources 表 ==")
for r in conn.execute("SELECT filename, LENGTH(dataStr) FROM resources").fetchall():
    print("  ", r[0], r[1], "bytes")

# 4) INSTANCE/VARIANT 相关表是否存在
print("\n== 变体/实例相关 ==")
tbls = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
for t in tbls:
    if any(s in t.lower() for s in ("variant", "instance", "group")):
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n} rows")

conn.close()
