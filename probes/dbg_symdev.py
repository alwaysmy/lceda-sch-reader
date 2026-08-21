"""符号/器件文档加载与 getSourceCode 验证。"""
import io, sys, json
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

def ev_await(expr, tid=2, timeout=600):
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
  var pm=SCH.gVars.projectMgr;
  var symK=Object.keys(pm.componentCache.symbol)[0];
  var devK=Object.keys(pm.componentCache.device)[0];
  var out={};
  try {
    var sdm=await SCH.docMemoryManager.getOrInitDoc(symK);
    var s1=sdm.consistencyImpl?sdm.consistencyImpl.getSourceCode():null;
    if (s1&&s1.then) s1=await s1;
    out.symbol={uuid:symK, loaded:!!sdm, isSymbol:sdm.isSymbolDoc?sdm.isSymbolDoc():null,
                len:s1?s1.length:0, head:s1?String(s1).slice(0,150):null};
  } catch(e){ out.symbol={err:String(e)}; }
  try {
    var ddm=await SCH.docMemoryManager.getOrInitDoc(devK);
    var s2=ddm.consistencyImpl?ddm.consistencyImpl.getSourceCode():null;
    if (s2&&s2.then) s2=await s2;
    out.device={uuid:devK, loaded:!!ddm,
                len:s2?s2.length:0, head:s2?String(s2).slice(0,150):null};
  } catch(e){ out.device={err:String(e)}; }
  return out;
})()
""")
print(json.dumps(r, ensure_ascii=False, indent=1)[:1500])
