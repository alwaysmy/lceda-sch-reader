"""遍历 webpack 模块缓存，定位含 history_data 的模块并提取相关源码段。"""
import io, sys, json, time
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes")
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

def ev(expr, timeout=120):
    ws = cdp.WS(t["webSocketDebuggerUrl"])
    ws.send_json({"id": 7, "method": "Runtime.evaluate",
                  "params": {"expression": expr, "returnByValue": True}})
    ws.sock.settimeout(timeout)
    t0 = time.time()
    while time.time() - t0 < timeout:
        m = json.loads(ws.recv_text())
        if m.get("id") == 7:
            r = m.get("result", {})
            if "exceptionDetails" in r:
                return "EXC: " + json.dumps(r["exceptionDetails"])[:200]
            return r.get("result", {}).get("value")
    raise SystemExit("超时")

# 探测 webpack 分块数组全局名
print(ev("""
Object.keys(window).filter(function(k){
  try { var v=window[k]; return Array.isArray(v) && v.length>0 &&
        typeof v[0]==='object' && v[0]!==null &&
        Object.keys(v[0]).length>20; } catch(e){return false}
}).slice(0,5).join(',')
"""))
