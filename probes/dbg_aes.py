"""提取 AES-128-GCM 加密类完整源码 + 密钥来源。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Program Files\lceda-pro\resources\app\app.js",
           encoding="utf-8", errors="replace").read()

# @2590023 附近提取完整类
pos = 2590023
# 向前找 class 定义
class_start = src.rfind("class", max(0, pos-2000), pos)
if class_start < 0:
    # 可能是 var X = class { ... } 形式
    class_start = src.rfind("=class", max(0, pos-2000), pos)
    if class_start >= 0:
        class_start = src.rfind("var", max(0, class_start-100), class_start)

# 括号配平提取类体
j = src.index("{", class_start)
depth = 0; k = j
while k < len(src):
    if src[k] == "{": depth += 1
    elif src[k] == "}":
        depth -= 1
        if depth == 0: break
    k += 1
class_body = src[class_start:k+1]
print(f"类定义 ({len(class_body)} chars):")
print(class_body[:4000])
if len(class_body) > 4000:
    print("\n... (截断)")

# 找实例化点（谁传了 key）
print("\n\n== 实例化/密钥来源 ==")
# 搜类名
cls_name_match = re.search(r'(\w+)\s*=\s*class\s*\{', src[class_start:class_start+100])
if cls_name_match:
    cname = cls_name_match.group(1)
    print(f"类名: {cname}")
    for m in re.finditer(rf'new {cname}\(', src):
        seg = src[max(0, m.start()-300):m.start()+300].replace("\n", "␤")
        print(f"  @{m.start()}: {seg[:550]}")
