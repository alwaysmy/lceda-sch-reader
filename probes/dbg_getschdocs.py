"""调用 docMemoryManager.getSchDocs 强制加载页内容（解密后）并采样。"""
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

def ev_await(expr, tid=2, timeout=120):
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

# 取一个 SCH_PAGE uuid
sheet_uuid = ev_await("""
Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)[0]
""")
print("目标页:", sheet_uuid)

r = ev_await(f"""
(async function(){{
  var dm=SCH.docMemoryManager;
  var out={{}};
  try {{
    var res = await dm.getSchDocs([{json.dumps(sheet_uuid)}]);
    if (res && typeof res==='object' && !(res instanceof Array)) {{
      Object.keys(res).forEach(function(k){{
        var v=res[k];
        out[k] = typeof v==='string' ? ('str['+v.length+']:'+v.slice(0,120))
               : (v&&v.dataStr ? ('obj.dataStr['+String(v.dataStr).length+']')
               : ('obj keys='+Object.keys(v||{{}}).slice(0,15).join(',')));
      }});
      return {{kind:'map', out:out}};
    }}
    return {{kind:'other', type:typeof res,
             preview:String(res).slice(0,200)}};
  }} catch(e) {{ return {{kind:'error', msg:String(e)}}; }}
}})()
""")
print(json.dumps(r, ensure_ascii=False, indent=1)[:1500])
