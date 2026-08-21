"""实测：getOrInitDoc 加载一页 + getDataStr 导出，检查输出格式。"""
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
                                         ensure_ascii=False)[:500])
                return None
            return r.get("result", {}).get("value")
    raise SystemExit("超时")

print("ZY =", ev_await("String(typeof ZY!=='undefined'?ZY:'(非全局)');"))
r = ev_await("""
(async function(){
  var su = Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)[0];
  var pid = SCH.gVars.currentProject.projectId;
  var dm = await pe.instance.getOrInitDoc(Ta(su, pid));
  var out = {su: su, docUuid: dm.uuid,
             keys: Object.keys(dm).slice(0,20)};
  try {
    var ds = dm.getDataStr(true);
    out.dsType = typeof ds;
    if (ds && ds.then) { out.isPromise = true; }
    else {
      out.len = ds.length; out.head = ds.slice(0,120);
      out.isBase64Gz = ds.startsWith('base64');
    }
  } catch(e) { out.dsErr = String(e); }
  return out;
})()
""")
print(json.dumps(r, ensure_ascii=False, indent=1)[:1200])
