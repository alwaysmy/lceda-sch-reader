"""sch-main.js: 追踪 Yke 解密函数的调用者 + Vke 类初始化。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe\sch-main.js",
           encoding="utf-8", errors="replace").read()

# Yke 调用点
for m in re.finditer(r"Yke\(", src):
    seg = src[max(0, m.start()-500):m.start()+200].replace("\n", "␤")
    print(f"--- Yke 调用 @{m.start()}:")
    print("  ", seg[:680])
    print()

# Vke 类定义（加密工具类）
for m in list(re.finditer(r"class\s+\w+\{[^}]*decrypt", src))[:3]:
    print(f"--- class with decrypt @{m.start()}:")
    print(src[m.start():m.start()+300])
    print()

# 搜 getSourceCodeId / sourceCodeId 相关（handler 有这些方法）
print("== sourceCodeIdMap 使用 ==")
for m in list(re.finditer(r"sourceCodeId", src))[:5]:
    seg = src[max(0, m.start()-200):m.start()+200].replace("\n", "␤")
    print(f"  @{m.start()}: {seg[:360]}")
