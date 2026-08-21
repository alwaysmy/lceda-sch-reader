"""钩 messageBus.rpcCall：捕获文档加载时的全部 RPC 通道与载荷规模。"""
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

# ① 钩 rpcCall（记录通道、参数规模、结果规模与头部）
r = ev_await("""
(function(){
  var mb = SCH.gVars.messageBus;
  window.__rpc = [];
  var orig = mb.rpcCall.bind(mb);
  mb.rpcCall = function(ch, args){
    var entry = {ch: ch, alen: JSON.stringify(args||[]).length};
    var p = Promise.resolve(orig(ch, args)).then(function(res){
      try {
        var s = JSON.stringify(res);
        entry.rlen = s ? s.length : 0;
        entry.head = s ? s.slice(0, 100) : String(res).slice(0,80);
      } catch(e){ entry.rlen = -1; }
    });
    window.__rpc.push(entry);
    return p;
  };
  return 'rpcCall hooked';
})()
""")
print("钩子:", r)

# ② 清 docMap 相关并重新加载一页
r = ev_await("""
(async function(){
  var su = Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)[0];
  var before = window.__rpc.length;
  var dm = await SCH.docMemoryManager.getOrInitDoc(su + '@' +
            SCH.gVars.currentProject.projectId);
  var sc = dm.consistencyImpl.getSourceCode();
  if (sc && sc.then) sc = await sc;
  var calls = window.__rpc.slice(before);
  return {srclen: String(sc).length, rpcCount: calls.length,
          calls: calls.map(function(c){
            return {ch: c.ch, alen: c.alen, rlen: c.rlen, head: c.head};
          })};
})()
""")
print(json.dumps(r, ensure_ascii=False, indent=1)[:2500])
