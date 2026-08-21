import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe\sch-main.js",
           encoding="utf-8", errors="replace").read()
m = re.search(r'ZY\s*=\s*"[^"]*"', src)
print("ZY 定义:", src[m.start():m.start()+40] if m else "未找到直接定义")
# 从 Ta 源码反推：i.includes(ZY) ? i : i+ZY+e —— 找 includes(ZY)
m2 = re.search(r'.{80}includes\(ZY\).{40}', src)
print("上下文:", m2.group(0) if m2 else "无")
