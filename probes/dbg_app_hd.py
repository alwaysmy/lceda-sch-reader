"""app.js 中 history_data 全部出现位置与上下文。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\app.js",
           encoding="utf-8", errors="replace").read()
ms = list(re.finditer(r"history_data", src, re.I))
print("总数:", len(ms))
for m in ms:
    seg = src[max(0, m.start()-400):m.start()+400].replace("\n", "␤")
    print(f"--- @{m.start()}:")
    print("  ", seg[:700])
