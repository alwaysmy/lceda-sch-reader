"""找 flowRead 实现 + iu 正则（二进制识别模式）。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\assets\pro-mgr"
           r"\3.2.169.1.daafe289\js\project-worker.js",
           encoding="utf-8", errors="replace").read()

# 1) 找 flowRead 函数定义
for m in re.finditer(r'(?:function\s+)?flowRead\s*\(', src):
    print(f"== flowRead @{m.start()} ==")
    brace = src.index("{", m.start())
    depth = 0; k = brace
    while k < len(src) and k < brace + 5000:
        if src[k] == "{": depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0: break
        k += 1
    body = src[brace:k+1]
    print(body[:3000])
    print()

# 2) 找 iu 正则定义
for m in re.finditer(r'\biu\s*=\s*/', src):
    seg = src[m.start():m.start()+100]
    print(f"iu regex: {seg}")
