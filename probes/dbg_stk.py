"""setSourceCode 调用栈回溯：定位解密函数。"""
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

# ① hook 原型 setSourceCode + getSourceCode，记录调用栈
r = ev_await("""
(function(){
  window.__stk = [];
  // 找一个已加载 docManager 拿到原型；没有则从 getOrInitDoc 后补
  var hookProto = function(dm){
    var h = dm.consistencyImpl.decodeAndRealTimeSyncHandler;
    if (h && !h.__hooked) {
      h.__hooked = true;
      ['setSourceCode','getSourceCode'].forEach(function(mn){
        var orig = h[mn].bind ? h[mn].bind(h) : h[mn];
        // 原型级：替换原型方法
        var proto = Object.getPrototypeOf(h);
        while (proto && !(proto.hasOwnProperty(mn) &&
               typeof proto[mn]==='function')) proto = Object.getPrototypeOf(proto);
        if (proto && !proto.__stkHooked) {
          proto.__stkHooked = true;
          var impl = proto[mn];
          proto[mn] = function(){
            try { throw new Error('trace'); } catch(e) {
              window.__stk.push({m: mn, stack: e.stack});
            }
            return impl.apply(this, arguments);
          };
        }
      });
      return 'hooked on proto';
    }
    return 'no handler';
  };
  var su = Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)[0];
  return SCH.docMemoryManager.getOrInitDoc(su).then(function(dm){
    return hookProto(dm);
  });
})()
""")
print("hook:", r)

# ② 触发重新加载（dispose + 新加载）
r = ev_await("""
(async function(){
  var su = Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)[0];
  SCH.docMemoryManager.dispose();
  var dm = await SCH.docMemoryManager.getOrInitDoc(su);
  var sc = dm.consistencyImpl.getSourceCode();
  if (sc && sc.then) sc = await sc;
  return {srclen: String(sc||'').length, stkCount: window.__stk.length};
})()
""")
print(json.dumps(r))

# ③ 输出捕获的栈
r = ev_await("JSON.stringify(window.__stk.map(function(s){return {m:s.m, stack:s.stack}}), null, 1)")
print(str(r)[:3000])
