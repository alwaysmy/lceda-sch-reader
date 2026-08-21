"""project-worker.js: 追踪 onLine 上游——blob→行 的转换点。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\assets\pro-mgr"
           r"\3.2.169.1.daafe289\js\project-worker.js",
           encoding="utf-8", errors="replace").read()
print("文件长度:", len(src))
# onLine 调用点
for m in list(re.finditer(r"\.onLine\(", src))[:6]:
    seg = src[max(0, m.start()-300):m.start()+200].replace("\n", "␤")
    print(f"--- @{m.start()}:")
    print("  ", seg[:480])
# split("||")
print("\n== '||' 分割 ==")
for m in list(re.finditer(r'split\(["\']\|\|["\']\)', src))[:4]:
    seg = src[max(0, m.start()-200):m.start()+150].replace("\n", "␤")
    print(f"  @{m.start()}:", seg[:320])
