"""找 PA 模块的 flowRead 实现（二进制解码核心）。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\assets\pro-mgr"
           r"\3.2.169.1.daafe289\js\project-worker.js",
           encoding="utf-8", errors="replace").read()

# PA=Wr(oi()) — 找 oi 函数和 Wr 包装器
# 先搜所有 flowRead 定义（可能有多个）
for m in re.finditer(r'flowRead\s*[=(]', src):
    ctx = src[max(0,m.start()-100):m.start()+300].replace("\n","␤")
    print(f"--- flowRead @{m.start()}:")
    print("  ", ctx[:360])
    print()

# 搜 Bn 类（iu regex 附近定义的类，有 static get 方法）
m = re.search(r'Bn=class\s+\w+\{', src)
if m:
    brace = src.index("{", m.start())
    depth = 0; k = brace
    while k < len(src) and k < brace + 8000:
        if src[k] == "{": depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0: break
        k += 1
    body = src[brace:k+1]
    print(f"== Bn 类 ({len(body)} chars) ==")
    # 找 flowRead 或 decode 方法
    for method_name in ("flowRead", "decode", "decompress", "read"):
        pos = body.find(method_name)
        if pos >= 0:
            print(f"\n  -- {method_name} @{pos}:")
            print("  ", body[pos:pos+600].replace("\n", "␤"))
