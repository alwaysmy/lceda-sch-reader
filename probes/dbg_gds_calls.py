"""sch-main.js getDataStr 全部调用点上下文（找对象来源）。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe\sch-main.js",
           encoding="utf-8", errors="replace").read()
for m in re.finditer(r"getDataStr\(", src):
    seg = src[max(0, m.start()-350):m.start()+200].replace("\n", "␤")
    print(f"--- @{m.start()}:")
    print("  ", seg[:520])
    print()
