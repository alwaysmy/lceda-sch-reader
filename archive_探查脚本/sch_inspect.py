import sqlite3
conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("TABLES:", tables)
for t in tables:
    try:
        cur.execute(f'SELECT count(*) FROM "{t}"')
        print(t, cur.fetchone()[0])
    except Exception as e:
        print(t, "ERR", e)
