import io, sys, json, zipfile, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

E = r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2"
z = zipfile.ZipFile(E)
data = z.read("Piezo_Driver.epru").decode("utf-8", errors="replace")
lines = data.split("\n")

def jl(s):
    try:
        return json.loads(s)
    except Exception:
        return None

print("== docType:17 记录全文 ==")
for i, ln in enumerate(lines):
    if '"docType":17' in ln:
        head, _, body = ln.partition("||")
        h = jl(head)
        b = jl(body.rstrip("|"))
        print(f"  L{i} header={json.dumps(h, ensure_ascii=False)[:120]}")
        print(f"       body={json.dumps(b, ensure_ascii=False)[:400]}")

print("\n== Pin Name / Pin Number / Pin Designator 键统计 ==")
kn = collections.Counter()
pin_attr_samples = {}
for ln in lines:
    if '"ATTR"' not in ln[:16]:
        continue
    b = jl(ln.partition("||")[2].rstrip("|"))
    if not b:
        continue
    k = b.get("key")
    if k and k.startswith("Pin"):
        kn[k] += 1
        if k not in pin_attr_samples:
            pin_attr_samples[k] = b
print(" ", dict(kn))
for k, b in pin_attr_samples.items():
    print(f"   {k}: parentId={b.get('parentId')} value={b.get('value')!r}")

print("\n== 页上 Symbol 属性值样例（是否 SYMBOL uuid） ==")
n = 0
for ln in lines:
    if '"ATTR"' not in ln[:16]:
        continue
    b = jl(ln.partition("||")[2].rstrip("|"))
    if b and b.get("key") == "Symbol":
        print(f"   value={b.get('value')!r} parentId={str(b.get('parentId'))[:14]}")
        n += 1
        if n >= 5:
            break

print("\n== NO_CONNECT 在 epro2 中? ==")
print("   出现:", data.count("NO_CONNECT"))

print("\n== Add into BOM / Convert to PCB ==")
print("   Add into BOM:", data.count('"Add into BOM"'),
      "| Convert to PCB:", data.count('"Convert to PCB"'))
