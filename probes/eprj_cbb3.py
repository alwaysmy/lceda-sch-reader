import io, sys, json, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"
conn = sqlite3.connect(f"file:{E}?mode=ro", uri=True)
cur = conn.cursor()

print("== 各表行数 ==")
for t in ("documents", "schematics", "components", "devices", "attributes",
          "boards", "projects", "branches", "backups", "db_paths",
          "block_symbol_attributes", "editor_caches", "sessions",
          "project_structures", "system_config"):
    try:
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n}")
    except Exception as e:
        print(f"  {t}: ERR {e}")

print("\n== projects 行 ==")
cols = [r[1] for r in cur.execute("PRAGMA table_info(projects)")]
print("  列:", cols)
for row in cur.execute("SELECT * FROM projects LIMIT 3"):
    print("  ", str(row)[:400])

print("\n== branches 行 ==")
for row in cur.execute("SELECT uuid, project_uuid, name FROM branches LIMIT 5"):
    print("  ", row[0][:12], row[1][:12] if row[1] else None, row[2])

print("\n== db_paths 行 ==")
for row in cur.execute("SELECT * FROM db_paths LIMIT 5"):
    print("  ", row)

print("\n== system_config ==")
for row in cur.execute("SELECT key, value FROM system_config LIMIT 10"):
    print("  ", row[0], "=", str(row[1])[:150])

print("\n== editor_caches 键 ==")
for row in cur.execute("SELECT key FROM editor_caches LIMIT 20"):
    print("  ", row[0])
