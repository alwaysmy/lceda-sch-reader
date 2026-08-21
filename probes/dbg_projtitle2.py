import io, sys, sqlite3, json, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
conn = sqlite3.connect(
    r"file:C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2?mode=ro",
    uri=True)
print("新版 .eprj2 projects.name:",
      conn.execute("SELECT name FROM projects").fetchone())
z = zipfile.ZipFile(r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro")
print(".epro title:", json.loads(z.read("project.json")).get("title"))
z2 = zipfile.ZipFile(r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2")
print(".epro2 title:", json.loads(z2.read("project2.json")).get("title"))
