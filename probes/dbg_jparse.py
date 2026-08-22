"""hook JSON.parse（大输入过滤）+ reload；验证工程重载状态。"""
import io, sys, json, time
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

HOOK = """
(function(){
  if (window.__pHook) return;
  window.__pHook = [];
  var op = JSON.parse;
  JSON.parse = function(s, r){
    var v = op.call(JSON, s, r);
    try {
      if (typeof s === 'string' && s.length > 50000 &&
          s.indexOf('COMPONENT') >= 0 && s.indexOf('DOCHEAD') < 0) {
        window.__pHook.push({len: s.length,
          head: s.slice(0,100),
          stack: String(new Error().stack).slice(0,1800)});
      }
    } catch(e){}
    return v;
  };
})();
"""
ws2 = cdp.WS(t["webSocketDebuggerUrl"])
ws2.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws2.recv_text()
except SystemExit:
    pass

def send(obj):
    global _tid
    _tid += 1
    ws2.send_json({"id": _tid, **obj})
    return _tid
_tid = 300

def wait_result(tid, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = json.loads(ws2.recv_text())
        if msg.get("id") == tid:
            return msg.get("result", {})
    raise SystemExit("超时")

tid = send({"method": "Page.addScriptToEvaluateOnNewDocument",
            "params": {"source": HOOK}})
wait_result(tid)
tid = send({"method": "Page.reload"})
wait_result(tid, timeout=120)
print("reload 完成")
time.sleep(30)
tid = send({"method": "Runtime.evaluate", "params": {
    "expression":
    "JSON.stringify({title: document.title.slice(0,40), "
    "n: (window.__pHook||[]).length, "
    "sample: (window.__pHook||[]).slice(0,3)})",
    "returnByValue": True}})
res = wait_result(tid, timeout=60)
val = res.get("result", {}).get("result", {}).get("value")
print(val[:3500] if val else "无")
