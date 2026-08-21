import io, sys, json, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
cur = conn.cursor()

print("== project_structures ==")
for row in cur.execute("SELECT * FROM project_structures"):
    d = dict(zip([c[0] for c in cur.description], row))
    for k, v in d.items():
        s = str(v)
        print(f"  {k} = {s[:300]}")

print("\n== history_data 行概览 ==")
for row in cur.execute(
        "SELECT uuid, history_uuid, LENGTH(dataStr) FROM history_data"):
    print("  uuid=", row[0][:16], "hist=", row[1][:16], "len=", row[2])

print("\n== history_data[0] dataStr 头部 ==")
row = cur.execute("SELECT dataStr FROM history_data LIMIT 1").fetchone()
ds = row[0]
print("  前200字符:", ds[:200])
try:
    j = json.loads(ds)
    print("  JSON 类型:", type(j).__name__)
    if isinstance(j, dict):
        print("  键:", list(j.keys())[:20])
    elif isinstance(j, list):
        print("  长度:", len(j), "首元素:", str(j[0])[:150])
except Exception as e:
    print("  非 JSON:", e)
