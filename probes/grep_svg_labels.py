import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
svg = open(r"C:\Users\dell\AppData\Local\Temp\lceda_render\P1.svg",
           encoding="utf-8").read()
for m in re.finditer(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*>([^<]*)</text>',
                     svg):
    x, y, s = float(m.group(1)), float(m.group(2)), m.group(3)
    if any(k in s for k in ("H_DA", "D3V3", "VOUT", "VDDA", "VREF")):
        print(f"x={x:8.1f} y={y:8.1f}  {s}")
print("---viewBox---")
print(re.search(r'viewBox="([^"]+)"', svg).group(1))
