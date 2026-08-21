"""大小写不敏感重搜 + 提取上下文。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

D = r"C:\Program Files\lceda-pro\resources\app\assets\pro-mgr\3.2.169.1.daafe289\js"
FILES = ["project-worker.js", "pro-mgr.js", "cache-worker.js",
         "snapshots-worker.js", "preload.js", "ws-service.js",
         "lib-worker.js"]

for fn in FILES:
    src = open(D + "\\" + fn, encoding="utf-8", errors="replace").read()
    ms = list(re.finditer(r"history[_A-Za-z]*data|historyData|HistoryData",
                          src, re.I))
    print(f"===== {fn}: {len(ms)} 处 =====")
    for m in ms[:3]:
        seg = src[max(0, m.start()-250):m.start()+250].replace("\n", "␤")
        print(f"  @{m.start()}: {seg[:480]}")
    print()
