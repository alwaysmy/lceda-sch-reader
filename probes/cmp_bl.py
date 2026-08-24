import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from PIL import Image

REF = r"C:\Users\dell\Pictures\Screenshots\屏幕截图 2026-08-23 065813.png"
MINE = r"C:\Users\dell\AppData\Local\Temp\lceda_render\da_v7.png"
OUT = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
       r"\probes\data\measure")

ref = Image.open(REF).convert("RGB")
mine = Image.open(MINE).convert("RGB")
# 参考图整页 1506x1078；我的截图 1600x1000。各裁左下角区域
rc = ref.crop((0, 700, 420, 1000)).resize((840, 600), Image.NEAREST)
rc.save(os.path.join(OUT, "cmp_ref_bl.png"))
mc = mine.crop((300, 700, 720, 1000)).resize((840, 600), Image.NEAREST)
mc.save(os.path.join(OUT, "cmp_mine_bl.png"))
print("saved cmp_ref_bl.png / cmp_mine_bl.png")

# NC 叉颜色核对：SVG 里搜 NC 线的颜色
svg = open(r"C:\Users\dell\AppData\Local\Temp\lceda_render\P1.svg",
           encoding="utf-8").read()
for c in ("#33cc33", "#dd0000", "#cc0000"):
    print(c, "出现次数:", svg.count(c))
