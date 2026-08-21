"""提取 project-worker.js 的 onLine 完整源码（二进制日志解析器）。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
D = r"C:\Program Files\lceda-pro\resources\app\assets\pro-mgr\3.2.169.1.daafe289\js"
src = open(D + r"\project-worker.js", encoding="utf-8", errors="replace").read()
m = re.search(r'onLine\(e,t,s,r,i,n,a,o,c,l,u,h\)\{', src)
if m:
    # 括号配平提取函数体
    i = m.start()
    depth = 0
    j = src.index("{", i)
    k = j
    while k < len(src):
        ch = src[k]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    body = src[i:k+1]
    print("onLine 长度:", len(body))
    print(body[:3000])
else:
    print("未找到 onLine")
