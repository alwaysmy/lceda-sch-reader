"""找 encodeConsistency 类定义：compressFull 的完整实现。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe\sch-main.js",
           encoding="utf-8", errors="replace").read()
print("长度:", len(src))

# 找 compressFull 定义
for m in re.finditer(r"compressFull\(", src):
    # 回溯到函数定义开头
    start = max(0, m.start()-100)
    # 找函数名
    ctx = src[max(0,m.start()-50):m.start()+80]
    print(f"@{m.start()}: {ctx[:120]}")
    print()

# 搜 encodeConsistency 类名
for m in list(re.finditer(r"encodeConsistency", src))[:5]:
    seg = src[max(0, m.start()-60):m.start()+60].replace("\n","␤")
    print(f"EC @{m.start()}: {seg}")
