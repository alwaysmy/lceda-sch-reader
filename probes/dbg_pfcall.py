"""parseFull 调用点：输入预处理（解压/解密）定位。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\assets\pro-mgr"
           r"\3.2.169.1.daafe289\js\project-worker.js",
           encoding="utf-8", errors="replace").read()
# parseFull 定义在类里；搜 ".parseFull(" 调用
for m in list(re.finditer(r"\.parseFull\(", src))[:6]:
    seg = src[max(0, m.start()-500):m.start()+150].replace("\n", "␤")
    print(f"--- @{m.start()}:")
    print("  ", seg[:620])
    print()
