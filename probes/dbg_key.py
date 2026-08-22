"""找加密类实例化点与 AES 密钥来源。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\app.js",
           encoding="utf-8", errors="replace").read()

# 加密类在 @2590023 附近。搜谁调用了 decrypt 方法
# 类是匿名的 `class t{...}`，通过某种方式实例化
# 搜 .decrypt( 调用（排除类定义本身）
for m in re.finditer(r"\.decrypt\(", src):
    seg = src[max(0, m.start()-300):m.start()+200].replace("\n", "␤")
    print(f"--- .decrypt @{m.start()}:")
    print("  ", seg[:480])
    print()

# 搜 16 字节 hex 密钥的可能来源
print("== 搜 key 相关 ==")
for pat in (r'"hex".*?16', r"from\(.*hex.*\).*16", r"encryptionKey",
            r"encKey", r"projectKey"):
    ms = list(re.finditer(pat, src[:3000000]))
    if ms:
        print(f"  {pat}: {len(ms)} 处")
        for m in ms[:2]:
            seg = src[max(0,m.start()-100):m.start()+200].replace("\n","␤")
            print(f"    {seg[:280]}")
