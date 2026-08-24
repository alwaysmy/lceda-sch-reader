import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from PIL import Image

REF = r"C:\Users\dell\Pictures\Screenshots\屏幕截图 2026-08-23 065813.png"
OUT = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
       r"\probes\data\measure")
ref = Image.open(REF).convert("RGB")
ref.crop((700, 330, 1010, 560)).resize((930, 690),
                                       Image.NEAREST).save(
    os.path.join(OUT, "z_ref_agnd2.png"))
print("ok")
