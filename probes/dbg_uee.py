"""uEe 类（extends vO）的 compressFull 完整实现 + vO 基类。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open(r"C:\Users\dell\AppData\Local\Temp\opencode\lceda_probe\sch-main.js",
           encoding="utf-8", errors="replace").read()

# uEe 类定义从 @452332 开始，extends vO
# 先提取 uEe 类体
start = src.index("uEe=class extends vO{", 452000)
j = src.index("{", start)
depth = 0; k = j
while k < len(src):
    if src[k] == "{": depth += 1
    elif src[k] == "}":
        depth -= 1
        if depth == 0: break
    k += 1
uee_body = src[start:k+1]
print(f"uEe 类体长度: {len(uee_body)}")

# 找 compressFull 在 uEe 内的位置
cf = uee_body.find("compressFull")
if cf >= 0:
    # 提取 compressFull 方法体
    m2 = re.search(r'compressFull\(i=\{\}\)\{', uee_body[cf:])
    if m2:
        j2 = uee_body.index("{", cf + m2.start())
        depth = 0; k2 = j2
        while k2 < len(uee_body):
            if uee_body[k2] == "{": depth += 1
            elif uee_body[k2] == "}":
                depth -= 1
                if depth == 0: break
            k2 += 1
        cfull = uee_body[cf+m2.start():k2+1]
        print(f"\n== uEe.compressFull ({len(cfull)} chars) ==")
        print(cfull[:3000])
else:
    print("uEe 内无 compressFull——在基类 vO 中")
    # 找 vO 类定义
    vo_start = src.find("class vO")
    if vo_start < 0:
        # 可能是 var vO=class 或其他形式
        for mm in re.finditer(r'\bvO\s*=\s*class\b', src):
            vo_start = mm.start()
            break
    if vo_start:
        j3 = src.index("{", vo_start)
        depth = 0; k3 = j3
        while k3 < len(src):
            if src[k3] == "{": depth += 1
            elif src[k3] == "}":
                depth -= 1
                if depth == 0: break
            k3 += 1
        vo_body = src[vo_start:k3+1]
        print(f"\n== vO 类体长度: {len(vo_body)} ==")
        cf2 = vo_body.find("compressFull")
        if cf2 >= 0:
            m4 = re.search(r'compressFull\([^)]*\)\{', vo_body[cf2:])
            if m4:
                j4 = vo_body.index("{", cf2 + m4.start())
                depth = 0; k4 = j4
                while k4 < len(vo_body):
                    if vo_body[k4] == "{": depth += 1
                    elif vo_body[k4] == "}":
                        depth -= 1
                        if depth == 0: break
                    k4 += 1
                print(f"\n== vO.compressFull ({k4+1-cf2-m4.start()} chars) ==")
                print(vo_body[cf2+m4.start():k4+1][:3000])
        else:
            print("vO 内也无 compressFull")
            # 列出全部方法名
            meths = re.findall(r'(\w+)\(', vo_body[vo_body.index('{'):])
            print("vO 方法:", sorted(set(meths))[:30])
