"""探针：.epro ZIP 内部布局——PCB 数据在哪、project.json 结构。"""
import io, sys, json, zipfile, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

P = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro"
z = zipfile.ZipFile(P)
names = z.namelist()
print(f"条目数: {len(names)}")

# 按顶层目录/扩展名归类
kinds = collections.Counter()
for n in names:
    top = n.split("/")[0]
    ext = n.rsplit(".", 1)[-1] if "." in n else "-"
    kinds[f"{top}/*.{ext}"] += 1
for k, c in kinds.most_common(30):
    print(f"  {c:5d}  {k}")

# project.json 顶层键
obj = json.loads(z.read("project.json"))
print("\nproject.json 顶层键:", list(obj.keys()))
boards = obj.get("boards", {})
print("boards:", {k: list(v.keys()) for k, v in boards.items()})
for k, v in boards.items():
    print(f"  board {k}: keys={list(v.keys())}")
    for kk, vv in v.items():
        if kk != "schematic":
            s = json.dumps(vv, ensure_ascii=False)[:120]
            print(f"    {kk} = {s}")

# 非 SHEET 目录的文件样例
others = [n for n in names if not n.startswith("SHEET/")][:40]
print("\n非 SHEET 条目:")
for n in others:
    info = z.getinfo(n)
    print(f"  {info.file_size:9d}  {n}")
