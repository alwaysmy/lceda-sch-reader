import io, sys, json, zipfile, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
z = zipfile.ZipFile(E)
data = z.read("Piezo_Driver.epru").decode("utf-8", errors="replace")

print("== 全文搜 symbolType / docType\":17 ==")
print("  'symbolType' 出现:", data.count("symbolType"))
print("  '\"docType\":17' 出现:", data.count('"docType":17'),
      "| '\"docType\": 17':", data.count('"docType": 17'))

# 找一个单 PIN 的 SYMBOL 文档完整 dump（GND 旗标）
lines = data.split("\n")
def jl(s):
    try:
        return json.loads(s)
    except Exception:
        return None

# 定位 SYMBOL 文档边界
docs = []   # (uuid, start, end)
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

sym_docs = [d for d in docs if d[1] == "SYMBOL"]
print("\nSYMBOL 文档数:", len(sym_docs))

# 找只有 1 个 PIN 的 SYMBOL，dump 全部记录
import json as J
target = None
for u, dt, s, e in sym_docs:
    npin = 0
    for ln in lines[s:e]:
        if '"PIN"' in ln[:20]:
            npin += 1
    if npin == 1:
        target = (u, s, e)
        break
if target:
    u, s, e = target
    print(f"\n== 单PIN SYMBOL 文档 {u} 全部记录 ==")
    for ln in lines[s:e]:
        head, _, body = ln.partition("||")
        h = jl(head)
        b = jl(body.rstrip("|"))
        if h is None:
            continue
        print(f"  [{h.get('type')}] id={str(h.get('id'))[:20]}: "
              f"{J.dumps(b, ensure_ascii=False)[:200] if b else ''}")

# CBB 黑盒符号：找 title 匹配 _CBB_ 板名的 SYMBOL 文档
board_titles = set()
for u, dt, s, e in docs:
    if dt != "BOARD":
        continue
    for ln in lines[s:e]:
        if '"META"' in ln[:16]:
            b = jl(ln.partition("||")[2].rstrip("|"))
            if b and b.get("title"):
                board_titles.add(b["title"])
print("\n== title 与板名同名的 SYMBOL 文档（黑盒候选） ==")
for u, dt, s, e in docs:
    if dt != "SYMBOL":
        continue
    for ln in lines[s:e]:
        if '"META"' in ln[:16]:
            b = jl(ln.partition("||")[2].rstrip("|"))
            if b and b.get("title") in board_titles and "_CBB_" in str(b.get("title")):
                print(f"  {u} title={b['title']} source={str(b.get('source'))[:60]}")
                for ln2 in lines[s:e][:8]:
                    head, _, body = ln2.partition("||")
                    h2 = jl(head)
                    b2 = jl(body.rstrip("|"))
                    if h2:
                        print(f"     [{h2.get('type')}] {J.dumps(b2, ensure_ascii=False)[:130] if b2 else ''}")
                break
