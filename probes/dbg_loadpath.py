"""project-worker.js: 找二进制 blob → 文档数据 的完整加载路径。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\assets\pro-mgr"
           r"\3.2.169.1.daafe289\js\project-worker.js",
           encoding="utf-8", errors="replace").read()

# 1) 搜 "loadProject" / "openProject" / "readProject" 等入口
for pat in (r"async\s+\w*[Ll]oad\w*\(", r"async\s+\w*[Oo]pen\w*\(",
            r"async\s+\w*[Rr]ead\w*\(", r"async\s+init\w*\("):
    for m in list(re.finditer(pat, src))[:3]:
        name = re.search(r'async\s+(\w+)', src[m.start():m.start()+50])
        if name:
            print(f"== {name.group(1)} @{m.start()} ==")
            # 打印函数体前 800 chars
            brace = src.index("{", m.start())
            depth = 0; k = brace
            while k < len(src) and k < brace + 3000:
                if src[k] == "{": depth += 1
                elif src[k] == "}":
                    depth -= 1
                    if depth == 0: break
                k += 1
            body = src[brace:k+1]
            print(body[:1500])
            print()
