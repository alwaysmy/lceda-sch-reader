import io, sys, json, zipfile, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
z = zipfile.ZipFile(E)
data = z.read("Piezo_Driver.epru").decode("utf-8", errors="replace")

seen = set()
samples = {}
docheads = []
for ln in data.split("\n"):
    if not ln.strip():
        continue
    head, sep, body = ln.partition("||")
    try:
        h = json.loads(head)
    except Exception:
        continue
    t = h.get("type", "?")
    if t == "DOCHEAD":
        try:
            docheads.append((h, json.loads(body)))
        except Exception as e:
            docheads.append((h, {"<parse-err>": str(e), "raw": body[:150]}))
    if t not in seen and len(samples) < 40:
        seen.add(t)
        samples[t] = (h, body[:220])
    if len(seen) >= 40 and len(docheads) >= 5:
        break

print("== DOCHEAD 样本 ==")
for h, b in docheads[:5]:
    print("  H:", json.dumps(h, ensure_ascii=False)[:160])
    print("  B:", json.dumps(b, ensure_ascii=False)[:200])

print("\n== 各类型 header 键与 body 头 ==")
for t, (h, b) in samples.items():
    print(f"[{t}] header={json.dumps(h, ensure_ascii=False)[:140]}")
    print(f"       body={b[:160]}")
