import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from PIL import Image
from collections import Counter

REF = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples"
       r"\实际的.png")
im = Image.open(REF).convert("RGB")
W, H = im.size
print("尺寸:", W, H)
px = im.load()

# 在整图找"蓝色文字"像素（位号/值是蓝色系），统计精确色值
cnt = Counter()
for y in range(0, H, 1):
    for x in range(0, W, 1):
        r, g, b = px[x, y]
        if b > 120 and b - r > 60 and b - g > 40 and r < 140:
            cnt[(r, g, b)] += 1
print("蓝色系文字 top8:", cnt.most_common(8))

# 绿色系（网络名？）
cnt2 = Counter()
for y in range(0, H, 1):
    for x in range(0, W, 1):
        r, g, b = px[x, y]
        if g > 100 and g - r > 40 and g - b > 40:
            cnt2[(r, g, b)] += 1
print("绿色系 top5:", cnt2.most_common(5))

# 红色系（符号/标题栏框）
cnt3 = Counter()
for y in range(0, H, 1):
    for x in range(0, W, 1):
        r, g, b = px[x, y]
        if r > 140 and r - g > 60 and r - b > 60:
            cnt3[(r, g, b)] += 1
print("红色系 top5:", cnt3.most_common(5))

# 黑/灰文字
cnt4 = Counter()
for y in range(0, H, 1):
    for x in range(0, W, 1):
        r, g, b = px[x, y]
        if abs(r-g) < 18 and abs(g-b) < 18 and r < 120:
            cnt4[(r, g, b)] += 1
print("黑灰系 top5:", cnt4.most_common(5))
