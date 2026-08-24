"""实测校准：从 EDA 参考截图量取 结点圆点/NC 叉 的相对尺寸。
方法：裁剪放大已知区域，人工读取像素尺寸；同时测导线宽作基准。
参考图：用户提供的 高速DA 页 EDA 截图(2026-08-23)。
"""
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

REF = r"C:\Users\dell\Pictures\Screenshots\屏幕截图 2026-08-23 065813.png"
OUT = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
       r"\probes\data\measure")
os.makedirs(OUT, exist_ok=True)

try:
    from PIL import Image
except ImportError:
    print("NO_PIL")
    sys.exit(0)

im = Image.open(REF)
print("尺寸:", im.size, im.mode)
# 裁剪几个感兴趣区域并放大保存，供人工读数：
# 1) DAC 左侧电阻网络(R61-R64 竖排)的结点圆点区
# 2) VOUTB 引脚附近的 NC 小叉
# 3) 任一段长直导线(测线宽基准)
crops = {
    "crop_junction": (620, 430, 800, 610),
    "crop_nc": (900, 520, 1000, 600),
    "crop_wire": (1050, 480, 1250, 530),
}
for name, box in crops.items():
    c = im.crop(box)
    c = c.resize((c.width * 4, c.height * 4), Image.NEAREST)
    p = os.path.join(OUT, name + ".png")
    c.save(p)
    print("saved", p, c.size)
