"""在全部 bundle（含 sch-main/ui/pro-mgr）中搜 history_data 直连与加解密特征。"""
import io, sys, re, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CANDS = [
    r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe\sch-main.js",
    r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe\ui_3_2_173.js",
]
D = r"C:\Program Files\lceda-pro\resources\app\assets\pro-mgr\3.2.169.1.daafe289\js"
for fn in os.listdir(D):
    if fn.endswith(".js"):
        CANDS.append(os.path.join(D, fn))
APP = r"C:\Program Files\lceda-pro\resources\app\app.js"

for path in CANDS:
    src = open(path, encoding="utf-8", errors="replace").read()
    hits = list(re.finditer(r"history_data", src, re.I))
    name = os.path.basename(path)
    print(f"{name}: {len(hits)} 处")
    for m in hits[:3]:
        seg = src[max(0, m.start()-200):m.start()+260].replace("\n", "␤")
        print(f"   @{m.start()}: {seg[:420]}")
    # 加解密特征
    for pat in (r"createDecipheriv", r"createCipheriv", r"\bAES\b",
                r"chacha", r"blowfish", r"xxtea", r"tea\b"):
        n = len(re.findall(pat, src, re.I))
        if n:
            print(f"   特征 {pat}: {n}")
