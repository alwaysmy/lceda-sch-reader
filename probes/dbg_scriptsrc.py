"""直接搜全局大函数源码：找含 history_data 的已加载脚本（Performance/ScriptSource）。"""
import io, sys, json, time, socket
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

import urllib.request
targets = json.loads(urllib.request.urlopen(
    "http://127.0.0.1:9222/json/list", timeout=5).read().decode())
t = next(x for x in targets if x["type"] == "page")

ws = cdp.WS(t["webSocketDebuggerUrl"])
mid = [0]

def send(method, params=None):
    mid[0] += 1
    ws.send_json({"id": mid[0], "method": method, "params": params or {}})
    return mid[0]

def recv_until(mid_want, timeout=60):
    ws.sock.settimeout(timeout)
    t0 = time.time()
    result = None
    while time.time() - t0 < timeout:
        try:
            m = json.loads(ws.recv_text())
        except socket.timeout:
            break
        if m.get("id") == mid_want:
            result = m
    return result

# Debugger.enable 收集全部 scriptParsed（含 URL）
send("Runtime.enable")
send("Debugger.enable", {"maxScriptsCacheSize": 1e9})
time.sleep(3)

# 排空事件，收集 scriptId->url
scripts = {}
drained = 0
ws.sock.settimeout(2)
try:
    while drained < 200:
        m = json.loads(ws.recv_text())
        if m.get("method") == "Debugger.scriptParsed":
            scripts[m["params"]["scriptId"]] = m["params"]["url"]
            drained += 1
except socket.timeout:
    pass

print(f"已知脚本数: {len(scripts)}")
cand = {sid: url for sid, url in scripts.items()
        if any(k in url for k in ("sch-main", "ui.js", "pro-mgr", "worker"))}
for sid, url in list(cand.items())[:10]:
    print(f"  scriptId={sid} url={url[:80]}")

# 对目标脚本用 Debugger.getScriptSource 搜 history_data
for sid, url in cand.items():
    tid = send("Debugger.getScriptSource", {"scriptId": sid})
    res = recv_until(tid, timeout=60)
    if not res:
        continue
    r = res.get("result", {})
    src = r.get("result", {}).get("scriptSource", "")
    n = src.count("history_data")
    print(f"{url[:60]}: len={len(src)} history_data×{n}")
    if n:
        outp = os.path.join(
            r"D:\WorkDesigns\3_WorkTools\sch_review_tool"
            r"\lceda_sch_reader\probes",
            os.path.basename(url).replace("/", "_") + ".src.js")
        with open(outp, "w", encoding="utf-8") as f:
            f.write(src)
        # 提取上下文
        import re
        for mm in list(re.finditer(r"history_data", src))[:5]:
            seg = src[max(0, mm.start()-300):mm.start()+400].replace("\n", "␤")
            print(f"   @{mm.start()}: {seg[:600]}")
