import io, sys, urllib.request, json, base64
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def gh(path):
    req = urllib.request.Request("https://api.github.com" + path,
                                 headers={"User-Agent": "research"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

def readme(repo):
    rd = gh(f"/repos/{repo}/readme")
    return base64.b64decode(rd["content"]).decode("utf-8", errors="replace")

# V2 仓库文件树
tree = gh("/repos/easyeda/easyeda-pro-file-format-v2/git/trees/main?recursive=1")
print("== file-format-v2 文件树 ==")
for it in tree.get("tree", []):
    if it["type"] == "blob":
        print("  ", it["path"], f"({it.get('size',0)})")
