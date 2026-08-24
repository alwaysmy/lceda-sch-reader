import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from PIL import Image

REF = r"C:\Users\dell\Pictures\Screenshots\屏幕截图 2026-08-23 065813.png"
im = Image.open(REF).convert("RGB")
px = im.load()
# 结点中心 (666,474)；NC 叉臂上一点 (971,531)
print("junction:", [px[658 + i, 473] for i in range(7)])
print("nc arm:", [px[970 + i, 531] for i in range(4)])
print("wire:", [px[702, 535]])
