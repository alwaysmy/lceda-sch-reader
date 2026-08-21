"""project-worker.js 中 history_data/历史表 读写上下文。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\assets\pro-mgr"
           r"\3.2.169.1.daafe289\js\project-worker.js",
           encoding="utf-8", errors="replace").read()
ms = list(re.finditer(r"history", src, re.I))
print("history 总数:", len(ms))
seen = set()
for m in ms:
    seg = src[max(0, m.start()-150):m.start()+200].replace("\n", "␤")
    key = seg[:80]
    if key in seen:
        continue
    seen.add(key)
    print(f"--- @{m.start()}:")
    print("  ", seg[:330])
    if len(seen) >= 10:
        break
