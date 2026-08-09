import sqlite3
conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
cur.execute('SELECT sql FROM sqlite_master WHERE name IN ("components","devices","schematics","attributes","documents")')
for r in cur.fetchall():
    print(r[0][:2000])
    print("----")
