"""定位 history_data 的加解密逻辑：提取 pro-mgr js 中关键词上下文。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

D = r"C:\Program Files\lceda-pro\resources\app\assets\pro-mgr\3.2.169.1.daafe289\js"
FILES = ["project-worker.js", "pro-mgr.js", "cache-worker.js",
         "snapshots-worker.js", "preload.js"]

for fn in FILES:
    src = open(D + "\\" + fn, encoding="utf-8", errors="replace").read()
    print(f"===== {fn} (len={len(src)}) =====")
    for m in list(re.finditer(r"history_data", src))[:4]:
        seg = src[max(0, m.start()-300):m.start()+300]
        seg = seg.replace("\n", "␤")
        print(f"--- @{m.start()}:")
        print("  ", seg[:560])
    print()
