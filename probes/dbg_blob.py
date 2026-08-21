"""blob 内容特征：搜 DOCHEAD/SCH_PAGE/二进制结构标记。"""
import io, sys, sqlite3, base64, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
rows = list(conn.execute(
    "SELECT uuid, length(dataStr) FROM history_data"))
print("history_data 行:", rows)
raw_all = []
for (u,) in conn.execute("SELECT dataStr FROM history_data"):
    raw_all.append(base64.b64decode(u))
blob = b"".join(raw_all)
print("合并长度:", len(blob))
for marker in (b"DOCHEAD", b"SCH_PAGE", b"SYMBOL", b"DEVICE", b"BOARD",
               b"COMPONENT", b"ATTR", b"ticket", b"docType"):
    print(f"  {marker.decode():10s}: {blob.count(marker)}")
# 字节频率 top
cnt = collections.Counter(blob[:200000])
top = cnt.most_common(8)
print("字节 top:", [(hex(b), c) for b, c in top])
