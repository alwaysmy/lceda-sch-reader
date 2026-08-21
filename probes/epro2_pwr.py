import io, sys, json, zipfile, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
z = zipfile.ZipFile(E)
data = z.read("Piezo_Driver.epru").decode("utf-8", errors="replace")
lines = data.split("\n")

print("== 关键字计数 ==")
for kw in ("Short", "SHORT", "short", "NetPort", "Power", "GND", "netflag",
           "NetFlag", "VCC", "barrel"):
    print(f"  {kw!r}: {data.count(kw)}")

# 找 title 为 GND/VCC 的 SYMBOL 文档，dump 其 META 与结构
def jl(s):
    try:
        return json.loads(s)
    except Exception:
        return None

docs = []
cur = None
for i, ln in enumerate(lines):
    if '"DOCHEAD"' not in ln[:30]:
        continue
    h = jl(ln.partition("||")[0])
    b = jl(ln.partition("||")[2].rstrip("|")) if h else None
    if h and h.get("type") == "DOCHEAD" and b:
        if cur:
            cur[2] = i
            docs.append(cur)
        cur = [b.get("uuid"), b.get("docType"), i, None]
if cur:
    cur[2] = len(lines)
    docs.append(cur)

print("\n== 单PIN SYMBOL 的 META 抽样（找电源/端口特征） ==")
shown = 0
for u, dt, s, e in docs:
    if dt != "SYMBOL":
        continue
    npin = sum(1 for ln in lines[s:e] if '"PIN"' in ln[:14])
    if npin != 1:
        continue
    for ln in lines[s:e]:
        if '"META"' in ln[:16]:
            b = jl(ln.partition("||")[2].rstrip("|"))
            if b and shown < 10:
                print(f"  {u[:12]}: {json.dumps(b, ensure_ascii=False)[:200]}")
                shown += 1
            break
