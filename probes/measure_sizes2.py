"""像素级测量：结点圆点直径 / 导线宽 比值；NC 叉尺寸/颜色。
在参考截图中定位已知特征行/列做颜色游程统计。"""
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from PIL import Image

REF = r"C:\Users\dell\Pictures\Screenshots\屏幕截图 2026-08-23 065813.png"
im = Image.open(REF).convert("RGB")
W, H = im.size
px = im.load()


def classify(c):
    r, g, b = c
    if r > 140 and g < 110 and b < 110:
        return "R"          # 红（符号图形/结点）
    if g > 120 and r < 130 and b < 130:
        return "G"          # 绿（导线）
    return "."


def run_row(y, x0, x1):
    runs, cur, n, sx = [], None, 0, x0
    for x in range(x0, x1):
        k = classify(px[x, y])
        if k != cur:
            if cur is not None and cur in ("R","G"):
                runs.append((cur, sx, n))
            cur, n, sx = k, 0, x
        n += 1
    if cur is not None and cur in ("R","G"):
        runs.append((cur, sx, n))
    return runs


def run_col(x, y0, y1):
    runs, cur, n, sy = [], None, 0, y0
    for y in range(y0, y1):
        k = classify(px[x, y])
        if k != cur:
            if cur is not None and cur in ("R","G"):
                runs.append((cur, sy, n))
            cur, n, sy = k, 0, y
        n += 1
    if cur is not None and cur in ("R","G"):
        runs.append((cur, sy, n))
    return runs


# 结点：crop_junction 内第一颗红点中心原图坐标约 (666, 474)
print("== 结点红点 水平游程 (y=468..480, x 655..680) ==")
for y in range(468, 481):
    rs = [(k, x, n) for k, x, n in run_row(y, 650, 685) if k == "R"]
    if rs:
        print(f"y={y}: {rs}")
# 导线宽基准：竖直绿线（R64 下方竖线 x≈707, y 500..600 找绿段）
print("== 竖直导线 绿色厚度 (x=700..716, y=520..560) ==")
for x in range(700, 717):
    rs = [(k, y, n) for k, y, n in run_col(x, 505, 585) if k == "G"]
    if rs:
        print(f"x={x}: {rs[:3]}")
# NC 叉：绿色 X 位于 VOUTB 引脚端 约 (952, 538)（从 crop_nc 推算）
print("== NC 绿叉 游程 (y=530..548, x 935..975) ==")
for y in range(530, 549):
    rs = [(k, x, n) for k, x, n in run_row(y, 930, 980) if k == "G"]
    if rs:
        print(f"y={y}: {rs}")
