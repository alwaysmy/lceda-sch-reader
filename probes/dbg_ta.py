import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe\sch-main.js",
           encoding="utf-8", errors="replace").read()

print("== function Ta( 定义 ==")
for m in list(re.finditer(r"function Ta\(", src))[:3]:
    print(src[m.start():m.start()+400].replace(chr(10), " "))
    print("---")

print("== getDataStr / toDataStr 出现数 ==")
for pat in ("getDataStr", "toDataStr", "getSaveData", "toStorage"):
    print(pat, len(re.findall(pat, src)))

print("\n== getDataStr 首个上下文 ==")
m = re.search(r"getDataStr", src)
if m:
    print(src[max(0, m.start()-150):m.start()+300].replace(chr(10), " "))
