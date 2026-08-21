"""app.js：搜 history 相关 RPC 通道与 dataStr 流向。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\app.js",
           encoding="utf-8", errors="replace").read()
# RPC 通道枚举
chans = sorted(set(re.findall(r'"([A-Z_]+\.HISTORY[A-Z_.]*)"', src)))
print("HISTORY 通道:", chans[:20])
chans2 = sorted(set(re.findall(r'"([A-Z_]+\.DATA[A-Z_.]*)"', src)))
print("DATA 通道:", chans2[:20])
# dataStr 在 F1 实体附近的读写
for m in list(re.finditer(r'new Q\("history_data"', src))[:2]:
    seg = src[m.start():m.start()+100]
    print("实体:", seg)
# 搜 compressFull / decompressFull（encodeConsistency 的对偶）
for pat in ("compressFull", "decompressFull", "parseFull", "fromFull"):
    n = len(re.findall(pat, src))
    print(pat, n)
