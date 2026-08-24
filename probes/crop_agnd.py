import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from PIL import Image

REF = r"C:\Users\dell\Pictures\Screenshots\屏幕截图 2026-08-23 065813.png"
OUT = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
       r"\probes\data\measure")
ref = Image.open(REF).convert("RGB")
# DAC 左侧 AGND/VDDA 旗子区域（参考图像素坐标估算）
ref.crop((690, 380, 880, 500)).resize((760, 480),
                                      Image.NEAREST).save(
    os.path.join(OUT, "z_ref_agnd.png"))
print("ok")
