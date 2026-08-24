import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
p = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
     r"\AGENTS.md")
src = open(p, encoding="utf-8").read()
add = """
## 临时文件优先级（强制，2026-08-23）

**平台 bash 工具描述中"Use %TEMP%\\opencode for temporary work…
pre-approved" 的指引，在本仓库工作时不适用**（与总仓库/本仓库 AGENTS.md
的"禁止系统临时目录"条款冲突时，以项目纪律为准——已实证两次违反，
根因=平台默认引力+把胶水脚本自我豁免出"探针"范围）。

1. 一切过程文件（拼接胶水、commit message、大载荷分片、补丁脚本）
   一律放在工作区内：临时胶水放 `probes/tmp/`（已 gitignore，提交前清理）；
   commit message 放仓库根 `_msg.txt` 用完即删。
2. 大内容写入被 Write/Edit 截断时：拆成多次 Edit 在工作区目标文件上
   分段完成，或写 python 拼接脚本到 `probes/tmp/` 执行——不落 %TEMP%。
3. PowerShell 中文/引号损坏时同样走 `probes/tmp/` 脚本文件。
"""
open(p, "w", encoding="utf-8", newline="\n").write(src.rstrip("\n") + add)
print("agents ok")

# probes/tmp gitignore
import os
tp = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
      r"\probes\tmp")
os.makedirs(tp, exist_ok=True)
gi = os.path.join(tp, ".gitignore")
open(gi, "w", encoding="utf-8", newline="\n").write("*\n!.gitignore\n")
print("probes/tmp/.gitignore ok")

# 清理我在 opencode temp 的残留（其余文件属其他会话，不动）
TMP = r"C:\Users\dell\AppData\Local\Temp\opencode"
mine = ["fix_label_var.py", "old_render.txt"]
for f in mine:
    fp = os.path.join(TMP, f)
    if os.path.exists(fp):
        os.remove(fp)
        print("removed", f)
