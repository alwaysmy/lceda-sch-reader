"""提取 uEe 类的 compressFull 方法（改进版括号配平）。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe\sch-main.js",
           encoding="utf-8", errors="replace").read()

# uEe 类体
start = src.index("uEe=class extends vO{", 452000)
j = src.index("{", start)
depth = 0; k = j
while k < len(src):
    if src[k] == "{": depth += 1
    elif src[k] == "}":
        depth -= 1
        if depth == 0: break
    k += 1
uee_body = src[start:k+1]

# 找 compressFull 方法签名
sig_pos = uee_body.find("compressFull(")
if sig_pos >= 0:
    # 从签名开始，找到方法体的 { } 对
    brace_start = uee_body.index("{", sig_pos)
    depth = 0; k2 = brace_start
    while k2 < len(uee_body):
        if uee_body[k2] == "{": depth += 1
        elif uee_body[k2] == "}":
            depth -= 1
            if depth == 0: break
        k2 += 1
    method = uee_body[sig_pos:k2+1]
    print(f"compressFull 方法 ({len(method)} chars):")
    print(method[:4000])
    if len(method) > 4000:
        print("\n... (后半段)")
        print(method[-1000:])
else:
    print("uEe 类体内无 compressFull——可能在基类 vO")

# 也列出 uEe 全部方法名
methods = re.findall(r'(\w+)\([^)]*\)\{', uee_body)
print("\nuEe 全部方法名:", sorted(set(methods)))
