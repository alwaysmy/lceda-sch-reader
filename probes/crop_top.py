import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from PIL import Image

MINE = r"C:\Users\dell\AppData\Local\Temp\lceda_render\da_v9.png"
REF = r"C:\Users\dell\Pictures\Screenshots\屏幕截图 2026-08-23 065813.png"
OUT = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
       r"\probes\data\measure")
mine = Image.open(MINE).convert("RGB")
ref = Image.open(REF).convert("RGB")
# 我的截图顶部旗子区域 (820,360)-(1000,460)；参考图对应 (770,330)-(950,430)
mine.crop((820, 350, 1010, 470)).resize((760, 480),
                                        Image.NEAREST).save(
    os.path.join(OUT, "z_mine_top.png"))
ref.crop((770, 320, 960, 440)).resize((760, 480),
                                      Image.NEAREST).save(
    os.path.join(OUT, "z_ref_top.png"))
print("ok")
