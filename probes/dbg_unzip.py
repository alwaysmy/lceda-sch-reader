"""project-worker.js: 应用级解压/容器读取调用点。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\assets\pro-mgr"
           r"\3.2.169.1.daafe289\js\project-worker.js",
           encoding="utf-8", errors="replace").read()
for pat in (r"unzipSync", r"ungzip", r"\.unzip\(", r"inflateSync\(",
            r"gunzipSync"):
    ms = list(re.finditer(pat, src))
    if not ms:
        continue
    print(f"== {pat}: {len(ms)} ==")
    for m in ms[:4]:
        seg = src[max(0, m.start()-250):m.start()+200].replace("\n", "␤")
        print(f"  @{m.start()}:", seg[:430])
        print()
