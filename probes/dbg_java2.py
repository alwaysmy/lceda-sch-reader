import io, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
base = ("https://raw.githubusercontent.com/brandon3055/EasyEDA-Pro-to-Json/"
        "HEAD/src/main/java/com/brandon3055/edaprotoibom/")
for f in ("EDAProToIBOM.java", "DocumentProcessor.java"):
    print("=" * 30, f, "=" * 30)
    txt = urllib.request.urlopen(base + f, timeout=30).read().decode(
        "utf-8", errors="replace")
    print(txt[:4000])
    print()
