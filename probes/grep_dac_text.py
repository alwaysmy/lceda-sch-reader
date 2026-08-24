import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
svg = open(r"C:\Users\dell\AppData\Local\Temp\lceda_render\P1.svg",
           encoding="utf-8").read()
for kw in ("双路DAC", "DAC8562"):
    for m in re.finditer(r"<text[^>]*>[^<]*" + kw + "[^<]*</text>", svg):
        print(m.group(0)[:220])
        print("---")
