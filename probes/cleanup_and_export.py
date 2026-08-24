import io, sys, shutil, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 1) 清理 opencode 临时目录里的一次性工作文件（内容均已入库：字典文档、
#    git 提交历史、probes 脚本）
TMP = r"C:\Users\dell\AppData\Local\Temp\opencode"
for f in ("new_render.py", "dict_part.md", "commit_msg.txt",
          "do_replace.py", "peek.py", "fix_epru_pcb_comp.py",
          "add_rule.py", "place_dict.py", "wb_nav.json"):
    p = os.path.join(TMP, f)
    if os.path.exists(p):
        os.remove(p)
        print("removed", f)

# 2) 渲染产物放到总仓库规定的留痕位置 test_scripts/results/
SRC = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
       r"\probes\data\render_smoke")
DST = (r"D:\WorkDesigns\2_WorkProjects\E_distance\test_scripts\results"
       r"\render_20260823")
os.makedirs(DST, exist_ok=True)
for f in os.listdir(SRC):
    if f.endswith(".svg"):
        shutil.copyfile(os.path.join(SRC, f), os.path.join(DST, f))
        print("copied", f)

# 3) 高速DA 最新版(含实测尺寸修正)单独输出一份
TOOL = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
        r"\lceda_reader.py")
EPRJ = (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch"
        r"\涡流传感器-V1.0-2026.04.01.eprj2")
out = os.path.join(DST, "高速DA_measured.svg")
r = os.system(f'set PYTHONIOENCODING=utf-8&& python "{TOOL}" --eprj '
              f'"{EPRJ}" render "高速DA" -o "{out}" --no-texts')
print("render rc:", r, "->", out)
