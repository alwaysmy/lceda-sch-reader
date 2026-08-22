"""提取 compressFull 完整实现 + uEe 类定义。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe\sch-main.js",
           encoding="utf-8", errors="replace").read()

# compressFull 完整函数体
m = re.search(r'compressFull\(i=\{\}\)\{', src)
if m:
    start = m.start()
    depth = 0
    j = src.index("{", start)
    k = j
    while k < len(src):
        if src[k] == "{": depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0: break
        k += 1
    body = src[start:k+1]
    print(f"== compressFull ({len(body)} chars) ==")
    print(body[:2500])
    print("\n... (截断)" if len(body) > 2500 else "")

# uEe 类定义
for mm in re.finditer(r'class\s*\w*\s*\{', src):
    # 检查这个类是否有 compressFull 方法
    chunk = src[mm.start():mm.start()+200]
    if "uEe" not in chunk:
        continue
print("\n== uEe 变量赋值 ==")
for mm in list(re.finditer(r'\buEe\b', src))[:5]:
    seg = src[max(0, mm.start()-40):mm.start()+60].replace("\n","␤")
    print(f"  @{mm.start()}: {seg}")
