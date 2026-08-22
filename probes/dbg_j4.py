"""找 j4 类（加密类）的 .decrypt( 调用与实例化。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\app.js",
           encoding="utf-8", errors="replace").read()

# 搜 j4 相关
for pat in (r'\bj4\b', r'new j4', r'j4\.decrypt'):
    ms = list(re.finditer(pat, src))
    print(f"== {pat}: {len(ms)} 处 ==")
    for m in ms[:5]:
        seg = src[max(0, m.start()-250):m.start()+250].replace("\n", "␤")
        print(f"  @{m.start()}: {seg[:480]}")
    print()

# 搜 .decrypt( 全文（排除类定义本身）
pos = 2590023  # 加密类位置
for m in re.finditer(r"\.decrypt\(", src):
    if abs(m.start() - pos) < 500:
        continue  # 跳过类定义自身
    seg = src[max(0, m.start()-350):m.start()+150].replace("\n", "␤")
    print(f"--- .decrypt @{m.start()}:")
    print("  ", seg[:480])
    print()
