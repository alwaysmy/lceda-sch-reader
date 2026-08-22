"""提取 app.js L8566 行 col≈74040 附近代码（gunzip 调用处）。"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\app.js",
           encoding="utf-8", errors="replace").read()
lines = src.split("\n")
line = lines[8565]  # 0-indexed
col = 74040
start = max(0, col - 600)
seg = line[start:col + 400]
print("L8566 col~74000-74400:")
print(seg)
