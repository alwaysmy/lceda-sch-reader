import sqlite3
conn = sqlite3.connect(r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2')
cur = conn.cursor()
want = ['386219d7910e4b378affc2ad9be17e0f','95e7db17afd74ac09758daf3bdbba0e7','49aac4ff9d4143be9bba8c2860c8ad00',
'f96259eabcbf470fafc4c98a3afbb91d','92683843e9d54caa81a426c2417925da','7ccc9bf615a64e2c8012badf59764a29',
'bfaab3471d1341c88dc6b4ec46089aad','496d4f18a3bf4d55a0ce2418227e450f','7637790e95c84de8ae0f46c2cc011158',
'c5b36f14d17a4dca92185e72dd61ccbb','1585115c68e44285a85dde27bc46fe4e','f4cd7522f5b3430093c810e94a366bba',
'8d2ff9bb2546403cbe5f9070b68c895d','10109bd05be947469ba080fdb97e564d','c47a60f6107c4306b59e35982e8c5f6e',
'007016e9be414b21a13cec6921042feb','8e65331843134cabbb31b31c3d5ac3da','deb7983ddb93468ab6f1f7ccd3fac048',
'd0df8d6e9ca34ed893743ec8ad5007a0','6fd4c95004e044e6a4755c3cf58f4747','1830b693fe1b4ca0a79e18f6d339bbad',
'abe73cfde71d440898abbf511c68aff9','3f2f39ac73b44e08b644e558d177cdc6','d5eb4f916bce401cb22892cd158cdad3',
'c968fb9d67614f1087444199d9b80c7b','61e22cb6df0e4df5a6b04923290cbad1','68c730d30c3747e8bf5b9d8309a32c2c',
'ab6cb584d24c4fd49a5e1786bc996c42','a72f29b83fe84e3ba9d037219fb1896b','5acbd624c8b64a61a070cd3e62fb1481',
'7910d9920a5e4d298a0e1138097f8d8f','10b7e273ade54a809d822f14768457f5']
q = ' OR '.join(['uuid=?']*len(want))
for r in cur.execute(f'SELECT uuid, title, display_title, description FROM devices WHERE {q}', want):
    print(r[0][:8], "|", r[1], "|", r[2], "|", r[3][:100])
