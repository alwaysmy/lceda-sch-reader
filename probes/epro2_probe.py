import io, sys, json, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
z = zipfile.ZipFile(E)
names = z.namelist()
print("== 条目统计 ==")
import collections
kinds = collections.Counter()
for n in names:
    top = n.split("/")[0] if "/" in n else n
    kinds[top] += 1
print(dict(kinds))
print("\n== 样例条目 ==")
for n in names[:25]:
    print(f"  {n}  ({z.getinfo(n).file_size}B)")

print("\n== project.json? ==")
if "project.json" in names:
    pj = json.loads(z.read("project.json"))
    print("  顶层键:", list(pj.keys()))
else:
    print("  无 project.json")

print("\n== epru 文件 DOCHEAD 样例 ==")
eprus = [n for n in names if n.endswith(".epru")]
print("epru 数量:", len(eprus))
if eprus:
    data = z.read(eprus[0]).decode("utf-8", errors="replace")
    print("首个 epru:", eprus[0], "长度", len(data))
    print("前 600 字符:")
    print(data[:600])
