import sqlite3
conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
kw = ('ADS8331','LTC2485','ADT7310','DAC7562','DAC8562','DAC8760','STM32','TPM','REF','LM','TPS','TLV','ADR','AD860','AD862','AD854','OPA','LMP','MCP','CH340','CH343','CP210','FT232','USB','SGM','AZ431','TL431','ME62','RT9013','XC6206','HT7','TLV700','ISO','ADuM')
rows = list(cur.execute("SELECT title, display_title, description FROM components"))
seen = set()
for t, dt, d in rows:
    t2 = (t or '').upper()
    if any(k.upper() in t2 for k in kw):
        key = (t, d)
        if key in seen: continue
        seen.add(key)
        print(f"{t}\t{dt}\t{d}")
