import io, sys, json, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
conn = sqlite3.connect(
    r"file:D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2?mode=ro",
    uri=True)
row = conn.execute(
    "SELECT uuid FROM documents WHERE docType=1 LIMIT 1").fetchone()
import base64, gzip
ds = conn.execute("SELECT dataStr FROM documents WHERE uuid=?",
                  (row[0],)).fetchone()[0]
raw = base64.b64decode(ds[6:])
text = gzip.decompress(raw).decode("utf-8")
n = 0
for ln in text.split("\n"):
    if ln.startswith('["TEXT"'):
        print(ln[:200])
        n += 1
        if n >= 5:
            break
