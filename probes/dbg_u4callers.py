"""找 U4 的调用者（谁接收并存储了加密密钥）+ 对应的解密函数。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\app.js",
           encoding="utf-8", errors="replace").read()

# 搜 U4 调用点
for m in re.finditer(r"\bU4\b", src):
    if m.start() < 2600000 and m.start() > 2610000:
        continue
    seg = src[max(0, m.start()-400):m.start()+400].replace("\n", "␤")
    print(f"--- U4 @{m.start()}:")
    print("  ", seg[:720])
    print()

# 搜对应的解密函数（可能有 U5 或类似命名）
# 或搜 .decrypt( 在渲染层 bundle sch-main.js 中
src2 = open(r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe\sch-main.js",
            encoding="utf-8", errors="replace").read()
for m in re.finditer(r"\.decrypt\(|decryptData|decHistory", src2):
    seg = src2[max(0, m.start()-250):m.start()+250].replace("\n", "␤")
    print(f"--- sch-main .decrypt @{m.start()}:")
    print("  ", seg[:480])
