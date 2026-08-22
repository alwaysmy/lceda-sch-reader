import io, sys, urllib.request, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def raw(path, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(
                "https://raw.githubusercontent.com/easyeda/"
                "easyeda-pro-file-format-v2/main/" + path)
            return urllib.request.urlopen(req, timeout=30).read().decode(
                "utf-8", errors="replace")
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2)

for p in ("docs/zh/general/file-header.md", "docs/zh/general/blob.md"):
    print("=" * 30, p, "=" * 30)
    print(raw(p))
    print()
