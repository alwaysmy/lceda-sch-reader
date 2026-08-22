"""直接打印 compressFull 和 compress 方法周围的大段源码。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe\sch-main.js",
           encoding="utf-8", errors="replace").read()

# uEe 类体范围
start = src.index("uEe=class extends vO{", 452000)
j = src.index("{", start)
depth = 0; k = j
while k < len(src):
    if src[k] == "{": depth += 1
    elif src[k] == "}":
        depth -= 1
        if depth == 0: break
    k += 1
uee = src[start:k+1]

# compressFull 周围 2000 chars
pos = uee.find("compressFull(")
print("== compressFull 周围 ==")
print(uee[pos:pos+2000])
print("\n" + "="*60)

# compress 方法周围
pos2 = uee.find("compress(")
if pos2 >= 0:
    print("\n== compress 周围 ==")
    print(uee[pos2:pos2+2000])
