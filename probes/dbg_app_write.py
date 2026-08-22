"""搜 app.js 中 history_data 的 INSERT/SELECT 操作与 blob 写入前处理。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\app.js",
           encoding="utf-8", errors="replace").read()

# 搜 ORM 实体 F1 的使用（history_data 的 entity）
# F1 = new Q("history_data", ...)
# 找 F1 被引用的地方
for pat in (r'\bF1\b', r'history_data', r'getHistoryData|setHistoryData',
            r'saveHistory|loadHistory'):
    ms = list(re.finditer(pat, src))
    print(f"== {pat}: {len(ms)} 处 ==")
    for m in ms[:5]:
        seg = src[max(0, m.start()-200):m.start()+250].replace("\n", "␤")
        print(f"  @{m.start()}: {seg[:420]}")
    print()

# 搜 deflate/gzip 的应用调用（非库内部）
print("== deflate/gzip 应用调用 ==")
for m in list(re.finditer(r'deflateSync|gzipSync|deflate\(', src))[:6]:
    seg = src[max(0, m.start()-200):m.start()+200].replace("\n", "␤")
    print(f"  @{m.start()}: {seg[:380]}")
