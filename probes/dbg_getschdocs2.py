"""getSchDocs 返回值结构细查。"""
import io, sys, json
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
ws.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws.recv_text()
except SystemExit:
    pass

def ev_await(expr, tid=2, timeout=180):
    ws.send_json({"id": tid, "method": "Runtime.evaluate",
                  "params": {"expression": expr, "returnByValue": True,
                             "awaitPromise": True}})
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = json.loads(ws.recv_text())
        if msg.get("id") == tid:
            r = msg.get("result", {})
            if "exceptionDetails" in r:
                print("EXC:", json.dumps(r["exceptionDetails"],
                                         ensure_ascii=False)[:400])
                return None
            return r.get("result", {}).get("value")
    raise SystemExit("超时")

r = ev_await("""
(async function(){
  var dm=SCH.docMemoryManager;
  var su = Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)[0];
  var res = await dm.getSchDocs([su]);
  var info = {resType: Object.prototype.toString.call(res)};
  if (res instanceof Map) {
    info.kind='Map'; info.size=res.size;
    var ks=[]; res.forEach(function(v,k){ ks.push(k); });
    info.keys=ks.slice(0,5);
    var k0=ks[0]; var v0=res.get(k0);
    info.v0 = typeof v0==='string' ? 'str['+v0.length+'] head='+v0.slice(0,150)
            : 'obj keys='+Object.keys(v0||{}).slice(0,20).join(',');
  } else {
    info.kind='object'; info.keys=Object.keys(res||{}).slice(0,5);
    var k0=info.keys[0];
    if (k0!==undefined){
      var v0=res[k0];
      info.v0 = typeof v0==='string' ? 'str['+v0.length+'] head='+v0.slice(0,150)
              : (v0 && v0.dataStr ? 'has dataStr len='+String(v0.dataStr).length
              : 'obj keys='+Object.keys(v0||{}).slice(0,20).join(','));
    }
  }
  return info;
})()
""")
print(json.dumps(r, ensure_ascii=False, indent=1)[:2000])
