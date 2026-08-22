"""找 PA 模块（Wr(oi())）的 flowRead 实现——二进制→文本解码核心。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\assets\pro-mgr"
           r"\3.2.169.1.daafe289\js\project-worker.js",
           encoding="utf-8", errors="replace").read()

# 找 oi 函数定义
for m in re.finditer(r'function\s+oi\s*\(', src):
    print(f"== oi @{m.start()} ==")
    brace = src.index("{", m.start())
    depth = 0; k = brace
    while k < len(src) and k < brace + 3000:
        if src[k] == "{": depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0: break
        k += 1
    body = src[brace:k+1]
    print(body[:2000])
    print()

# 也搜 Wr 函数
for m in re.finditer(r'function\s+Wr\s*\(', src):
    print(f"== Wr @{m.start()} ==")
    seg = src[m.start():m.start()+200]
    print(seg)

# 直接搜所有包含 "flowRead" 的函数定义（非调用）
for m in re.finditer(r'flowRead\s*[=(]\s*async|flowRead\s*=\s*function|async\s+flowRead', src):
    ctx = src[max(0,m.start()-50):m.start()+500].replace("\n","␤")
    print(f"\n--- flowRead def @{m.start()}:")
    print(ctx[:520])
