"""各格式工程名字段核查。"""
import io, sys, json, sqlite3, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

print("== 旧版 .eprj2 projects.name ==")
conn = sqlite3.connect(
    r"file:D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2?mode=ro",
    uri=True)
print(" ", list(conn.execute("SELECT name FROM projects")))
print("  schematics.name:", [r[0] for r in conn.execute(
    "SELECT name FROM schematics LIMIT 3")])

print("\n== 新版 .eprj2 projects.name ==")
conn = sqlite3.connect(
    r"file:C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2?mode=ro",
    uri=True)
print(" ", list(conn.execute("SELECT name, title FROM projects" if True else ""))[:1]
      or "")
cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)")]
print("  列含 title?", "title" in cols)
row = conn.execute("SELECT name FROM projects").fetchone()
print("  name:", row)

print("\n== .epro project.json title ==")
import zipfile
z = zipfile.ZipFile(r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro")
pj = json.loads(z.read("project.json"))
print("  title:", pj.get("title"))

print("\n== .epro2 project2.json title ==")
z2 = zipfile.ZipFile(r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2")
p2 = json.loads(z2.read("project2.json"))
print("  title:", p2.get("title"))
