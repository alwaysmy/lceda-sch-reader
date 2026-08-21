"""Node CDP 上下文诊断：process/require 可达性。"""
import io, sys, json, time
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

import urllib.request
targets = json.loads(urllib.request.urlopen(
    "http://127.0.0.1:9229/json/list", timeout=5).read().decode())
node_t = next(t for t in targets if t.get("type") == "node")
ws = cdp.WS(node_t["webSocketDebuggerUrl"])
ws.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws.recv_text()
except SystemExit:
    pass

def ev(expr, tid=2, timeout=30):
    ws.send_json({"id": tid, "method": "Runtime.evaluate",
                  "params": {"expression": expr,
                             "returnByValue": True,
                             "awaitPromise": True}})
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = json.loads(ws.recv_text())
        if msg.get("id") == tid:
            r = msg.get("result", {})
            if "exceptionDetails" in r:
                print("EXC:", json.dumps(r["exceptionDetails"],
                                         ensure_ascii=False)[:200])
                return None
            return r.get("result", {}).get("value")
    raise SystemExit("超时")

print("typeof process:", ev("typeof process"))
print("cwd:", ev("process && process.cwd ? process.cwd() : 'n/a'"))
print("execPath:", ev("process.execPath"))
print("mainModule require:", ev(
    "typeof process.mainModule !== 'undefined' ? 'yes' : 'no'"))
print("module hooks:", ev("""
(function(){
  try {
    var m = process.mainModule || require('module');
    var req = process.mainModule ? process.mainModule.require : require;
    var crypto = req('crypto');
    return 'crypto OK: ' + Object.keys(crypto).slice(0,6).join(',');
  } catch(e) { return 'ERR: ' + e.message; }
})()
"""))
