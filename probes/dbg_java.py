import io, sys, urllib.request, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def gh(path):
    req = urllib.request.Request("https://api.github.com" + path,
                                 headers={"User-Agent": "research"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())

tree = gh("/repos/brandon3055/EasyEDA-Pro-to-Json/git/trees/HEAD?recursive=1")
print("== EasyEDA-Pro-to-Json 文件树 ==")
for it in tree.get("tree", []):
    if it["type"] == "blob" and (it["path"].endswith(".java") or
                                 it["path"].endswith(".md")):
        print("  ", it["path"], f"({it.get('size',0)})")
