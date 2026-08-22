"""找 R8 模块的 flowRead 实现（二进制→文本解码核心）。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\assets\pro-mgr"
           r"\3.2.169.1.daafe289\js\project-worker.js",
           encoding="utf-8", errors="replace").read()

# 搜 R8 赋值
for m in re.finditer(r'\bR8\s*=', src):
    seg = src[max(0,m.start()-30):m.start()+100].replace("\n","␤")
    print(f"R8= @{m.start()}: {seg}")

# 搜所有 flowRead 的函数定义（不是调用）
for m in re.finditer(r'(?:async\s+)?function\s+flowRead|flowRead\s*[:=]\s*(?:async\s*)?(?:function|\()', src):
    print(f"\n== flowRead def @{m.start()} ==")
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

# 也搜 exports.flowRead 或 module.exports 含 flowRead
for m in re.finditer(r'flowRead', src):
    before = src[max(0,m.start()-20):m.start()]
    if 'exports' in before or 'module' in before:
        print(f"\n== export flowRead @{m.start()}:")
        print(src[m.start():m.start()+200])
