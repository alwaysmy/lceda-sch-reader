"""ui.js 中 createDecipheriv/createCipheriv 调用上下文全提取。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe\ui_3_2_173.js",
           encoding="utf-8", errors="replace").read()
for pat in ("createDecipheriv", "createCipheriv"):
    print(f"########## {pat} ##########")
    for i, m in enumerate(re.finditer(pat, src)):
        seg = src[max(0, m.start()-350):m.start()+450].replace("\n", "␤")
        print(f"--- #{i} @{m.start()}:")
        print(seg[:760])
        print()
