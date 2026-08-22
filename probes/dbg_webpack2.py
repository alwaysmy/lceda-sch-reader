"""webpack 分块探测 + history_data 模块源码提取（v2，含超时保护）。"""
import io, sys, json, time
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

def ev(expr, timeout=90):
    ws = cdp.WS(t["webSocketDebuggerUrl"])
    ws.send_json({"id": 7, "method": "Runtime.evaluate",
                  "params": {"expression": expr, "returnByValue": True}})
    ws.sock.settimeout(timeout)
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            m = json.loads(ws.recv_text())
        except socket.timeout:
            break
        if m.get("id") == 7:
            r = m.get("result", {})
            if "exceptionDetails" in r:
                return "EXC: " + json.dumps(r["exceptionDetails"])[:200]
            return r.get("result", {}).get("value")
    return "(超时)"

# 探测 webpack chunk 数组
r = ev("""
(function(){
  var names = Object.keys(window).filter(function(k){
    try { var v=window[k]; return Array.isArray(v) && v.length>0 &&
      typeof v[0]==='object' && v[0]!==null &&
      Object.keys(v[0]).length>20; } catch(e){return false}
  });
  var out = [];
  names.forEach(function(n){
    try {
      var total = 0, withFn = 0;
      window[n].forEach(function(chunk){
        if (chunk && typeof chunk==='object') {
          var ks = Object.keys(chunk);
          total += ks.length;
          ks.forEach(function(k){ if (typeof chunk[k]==='function') withFn++; });
        }
      });
      out.push(n + ': chunks=' + window[n].length + ' modules=' + total +
               ' fns=' + withFn);
    } catch(e){}
  });
  return out.join('\\n') || '未找到 chunk 数组';
})()
""")
print(r)
