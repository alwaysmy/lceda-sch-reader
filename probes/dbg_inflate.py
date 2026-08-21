"""project-worker.js 中 inflate 调用点上下文（找 history_data blob 解压）。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\assets\pro-mgr"
           r"\3.2.169.1.daafe289\js\project-worker.js",
           encoding="utf-8", errors="replace").read()
for m in list(re.finditer(r"inflateSync\(|\.inflate\(", src))[:10]:
    seg = src[max(0, m.start()-260):m.start()+260].replace("\n", "␤")
    print(f"--- @{m.start()}:")
    print("  ", seg[:480])
    print()
