import io, sys, json, sqlite3, base64
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
cur = conn.cursor()

print("== history_data 魔数分析 ==")
row = cur.execute("SELECT dataStr FROM history_data LIMIT 1").fetchone()
raw = base64.b64decode(row[0])
print("  解码后长度:", len(raw), "前16字节:", raw[:16].hex())
print("  gzip?", raw[:2] == b"\x1f\x8b", "| zlib?", raw[:1] == b"\x78",
      "| zstd?", raw[:4] == b"\x28\xb5\x2f\xfd", "| zip?", raw[:2] == b"PK")
# 熵估计（加密数据高熵）
import collections, math
cnt = collections.Counter(raw[:65536])
ent = -sum(c / 65536 * math.log2(c / 65536) for c in cnt.values())
print(f"  前64KB香农熵: {ent:.2f} bits/byte (>7.9 基本可判定加密)")

print("\n== structure 全文（板树） ==")
row = cur.execute("SELECT structure FROM project_structures").fetchone()
st = json.loads(row[0])
print("  顶层键:", list(st.keys()))
for k, v in st.items():
    if isinstance(v, dict):
        print(f"  {k}: {len(v)} 项")
        for kk, vv in list(v.items())[:3]:
            print("    ", kk[:10], json.dumps(vv, ensure_ascii=False)[:120])

print("\n== 旧格式工程(涡流V1.0)的 CBB 相关结构 ==")
E2 = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
conn2 = sqlite3.connect(f"file:{E2}?mode=ro", uri=True)
cur2 = conn2.cursor()
try:
    n = cur2.execute("SELECT COUNT(*) FROM block_symbol_attributes").fetchone()[0]
    print("  block_symbol_attributes 行数:", n)
    for row in cur2.execute(
            "SELECT path, hash, attr FROM block_symbol_attributes LIMIT 5"):
        print("   path=", row[0][:60], "hash=", row[1], "attr=", str(row[2])[:200])
except Exception as e:
    print("  无此表:", e)
for row in cur2.execute("SELECT cbb_project, block_symbol_attrs_groups FROM projects"):
    print("  projects.cbb_project =", row[0],
          "| block_symbol_attrs_groups =", str(row[1])[:300])
