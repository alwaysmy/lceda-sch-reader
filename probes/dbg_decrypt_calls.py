"""找 .decrypt( 调用与密钥实例化点。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\app.js",
           encoding="utf-8", errors="replace").read()

# 加密类在 ~2590023。搜 .decrypt( 调用
pos = 2590023
for m in re.finditer(r"\.decrypt\(", src):
    seg = src[max(0, m.start()-400):m.start()+200].replace("\n", "␤")
    print(f"--- .decrypt @{m.start()}:")
    print("  ", seg[:560])
    print()

# 搜 new + 类名（找加密类被赋给什么变量）
# 类定义在附近，搜 2590023 前后的变量赋值
ctx = src[2588000:2591000]
# 找 var/let X = class 模式
for m in re.finditer(r'(\w+)\s*=\s*class\s', ctx):
    print(f"类赋值: {m.group(1)} @ {2588000+m.start()}")

# 搜 2590023 附近谁被 new
for m in re.finditer(r'new\s+(\w+)\s*\(', src[pos-2000:pos+3000]):
    print(f"  new {m.group(1)} @ {pos-2000+m.start()}")
