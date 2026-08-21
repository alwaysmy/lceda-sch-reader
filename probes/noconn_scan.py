import base64, gzip, io, json, sqlite3, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

NEW = r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2"
conn = sqlite3.connect(f"file:{NEW}?mode=ro", uri=True)

def decompress(ds):
    if not ds:
        return ""
    s = ds[6:] if isinstance(ds, str) and ds.startswith("base64") else ds
    try:
        data = base64.b64decode(s)
    except Exception:
        return ""
    try:
        return gzip.decompress(data).decode("utf-8")
    except Exception:
        return data.decode("utf-8", errors="replace")

# NO_CONNECT 挂载结构
print("== NO_CONNECT 样例 ==")
cnt = 0
for u, t, dt, ds in conn.execute(
        "SELECT uuid, display_title, docType, dataStr FROM documents WHERE docType=1").fetchall():
    for ln in decompress(ds).splitlines():
        if '"NO_CONNECT"' not in ln:
            continue
        try:
            a = json.loads(ln)
        except Exception:
            continue
        print(f"  页[{t}] ATTR parentId={a[2]} key={a[3]} val={a[4]}")
        cnt += 1
        if cnt >= 8:
            break
    if cnt >= 8:
        break
print("  (共 139 个)")

# NO_CONNECT 的 parentId 是否同时是 ATTR NAME/NUMBER 的 parent（即 pin）
print("\n== NO_CONNECT 引脚 vs 普通引脚 识别链 ==")
for u, t, dt, ds in conn.execute(
        "SELECT uuid, display_title, docType, dataStr FROM documents WHERE docType=1").fetchall():
    for ln in decompress(ds).splitlines():
        if '"NO_CONNECT"' not in ln:
            continue
        try:
            a = json.loads(ln)
        except Exception:
            continue
        pid = a[2]
        # 找同页同 pid 的 NAME/NUMBER ATTR
        text = decompress(ds)
        nname = nnum = None
        for ln2 in text.splitlines():
            try:
                a2 = json.loads(ln2)
            except Exception:
                continue
            if (a2[0] == "ATTR" and len(a2) >= 5 and a2[2] == pid
                    and a2[3] in ("NAME", "NUMBER")):
                if a2[3] == "NAME":
                    nname = a2[4]
                else:
                    nnum = a2[4]
        print(f"  NO_CONNECT on pin id={pid} name={nname} number={nnum} (页 {t})")
        break
    break

# PCB 文档格式抽样（docType=3 第一行）
print("\n== PCB 文档格式抽样 ==")
for u, t, dt, ds in conn.execute(
        "SELECT uuid, display_title, docType, dataStr FROM documents WHERE docType=3 AND LENGTH(dataStr)>1000").fetchall():
    text = decompress(ds)
    print(f"  {t} ({len(text)} chars):")
    for ln in text.splitlines()[:8]:
        print("   ", ln[:130])
    break

conn.close()
