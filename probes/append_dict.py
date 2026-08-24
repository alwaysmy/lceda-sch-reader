import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
p = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
     r"\docs\工程文件字段字典.md")
src = open(p, encoding="utf-8").read()
add = """
## 0.1 渲染常量实测记录（2026-08-23）

来源：用户提供的 高速DA 页 EDA 截图像素测量
（probes/measure_sizes2.py 游程统计 + measure_colors.py 取色，
以 DAC 符号 BBOX 高 100 单位≈145px 标定 px↔单位）：

| 常量 | 实测值 | 备注 |
| --- | --- | --- |
| 默认线宽（LINESTYLE width=null 时） | ≈1 单位 | 绿色 #349d32（实测 RGB 52,157,50） |
| 结点圆点半径 | ≈2 单位（直径≈4×线宽） | **红色 #cc0000**（204,0,0）——非绿色 |
| NC 叉半臂 | ≈3.5 单位（≈0.35×引脚长10） | **绿色 #33cc33**（51,204,51）——非红色；位于引脚连接端 |
| 默认字号 | 10 单位 ≈14.5px 与截图中引脚名一致 | FONTSTYLE null 时继承 |

注意：结点/NC 尺寸不在文件格式内存储（无 JUNCTION 记录、NO_CONNECT
只是 ATTR 标志），是 EDA 内部默认值——以上为对 EDA 显示的实测标定。
"""
open(p, "w", encoding="utf-8", newline="\n").write(src.rstrip("\n") + add)
print("ok")
