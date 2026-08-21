"""页面加载前注入 hook（atob/TextDecoder/subtle）+ reload 捕获打开时解密。"""
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
    "http://127.0.0.1:9222/json/list", timeout=5).read().decode())
t = next(x for x in targets if x["type"] == "page")
ws = cdp.WS(t["webSocketDebuggerUrl"])
ws.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws.recv_text()
except SystemExit:
    pass

def send(obj):
    global _tid
    _tid += 1
    ws.send_json({"id": _tid, **obj})
    return _tid
_tid = 100

def wait_result(tid, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = json.loads(ws.recv_text())
        if msg.get("id") == tid:
            return msg.get("result", {})
    raise SystemExit("等待超时")

HOOK = """
(function(){
  if (window.__decHook) return;
  window.__decHook = [];
  var dec = TextDecoder.prototype.decode;
  TextDecoder.prototype.decode = function(buf, o){
    var r = dec.call(this, buf, o);
    try {
      if (r && r.length > 200 && r.indexOf('DOCHEAD') >= 0) {
        window.__decHook.push({t:'TextDecoder', len: r.length,
          head: r.slice(0,80), stack: String(new Error().stack).slice(0,2000)});
      }
    } catch(e){}
    return r;
  };
  var at = window.atob;
  window.atob = function(s){
    var r = at.call(window, s);
    try {
      if (r && r.length > 10000) {
        window.__decHook.push({t:'atob', inlen: s.length, outlen: r.length,
          head: Array.from(r.slice(0,8)).map(function(c){return c.charCodeAt(0).toString(16)}).join(','),
          stack: String(new Error().stack).slice(0,1500)});
      }
    } catch(e){}
    return r;
  };
})();
"""

tid = send({"method": "Page.addScriptToEvaluateOnNewDocument",
            "params": {"source": HOOK}})
wait_result(tid)
tid = send({"method": "Page.reload"})
wait_result(tid, timeout=120)
print("reload 完成，等待工程加载...")
time.sleep(25)

tid = send({"method": "Runtime.evaluate",
            "params": {"expression":
                       "JSON.stringify((window.__decHook||[]).slice(0,6))",
                       "returnByValue": True}})
res = wait_result(tid, timeout=60)
val = res.get("result", {}).get("result", {}).get("value")
print("捕获:", val[:4000] if val else "无")
