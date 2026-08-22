"""docManager 结构：自有键/原型方法/encodeConsistency 位置。"""
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

def ev_await(expr, tid=2, timeout=300):
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
  var su = Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)[0];
  var dm = await SCH.docMemoryManager.getOrInitDoc(su);
  var protoM = [];
  var o = Object.getPrototypeOf(dm); var n=0;
  while(o && n<3){ Object.getOwnPropertyNames(o).forEach(function(p){
    try{ if(typeof dm[p]==='function') protoM.push(p);}catch(e){} });
    o=Object.getPrototypeOf(o); n++; }
  return {ownKeys: Object.keys(dm).slice(0,30),
          methods: Array.from(new Set(protoM)).slice(0,60),
          hasEC: 'encodeConsistency' in dm,
          ecKeys: dm.encodeConsistency?Object.keys(dm.encodeConsistency).slice(0,15):null};
})()
""")
print(json.dumps(r, ensure_ascii=False, indent=1)[:2000])
