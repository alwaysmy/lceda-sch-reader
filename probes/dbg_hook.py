"""运行时钩子实验：包装 crypto.subtle.decrypt/encrypt 与 pako.inflate，
触发文档加载，捕获调用（算法/密钥可提取性/数据头）。"""
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
                                         ensure_ascii=False)[:400])
                return None
            return r.get("result", {}).get("value")
    raise SystemExit("超时")

# ① 安装钩子
r = ev_await("""
(function(){
  window.__cap = [];
  try {
    var sd = crypto.subtle.decrypt.bind(crypto.subtle);
    Object.defineProperty(crypto.subtle, 'decrypt', {value: function(a,k,d){
      window.__cap.push({t:'subtle.decrypt', alg: JSON.stringify(a),
        keyExtractable: k.extractable, dlen: d.byteLength||d.size||0});
      return sd(a,k,d);
    }, writable: true, configurable: true});
  } catch(e) { return 'subtle hook 失败: '+e; }
  // pako 系（全局或 webpack 内部不易挂，尝试常见全局）
  var hooked=[];
  ['pako','Pako'].forEach(function(n){
    if (window[n] && window[n].inflate) {
      var oi = window[n].inflate.bind(window[n]);
      window[n].inflate = function(d,o){
        window.__cap.push({t:'pako.inflate', dlen: d&&d.length});
        return oi(d,o);
      };
      hooked.push(n);
    }
  });
  return 'subtle OK; pako hooks: '+hooked.join(',');
})()
""")
print("钩子安装:", r)

# ② 触发文档加载（清空 docMap 后重新 getOrInitDoc 一页）
r = ev_await("""
(async function(){
  var su = Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)[0];
  SCH.docMemoryManager.dispose ? SCH.docMemoryManager.dispose() : null;
  var dm = await SCH.docMemoryManager.getOrInitDoc(su);
  var sc = dm.consistencyImpl.getSourceCode();
  if (sc && sc.then) sc = await sc;
  return {loaded: !!dm, srclen: String(sc).length,
          capCount: window.__cap.length,
          cap: window.__cap.slice(0,10)};
})()
""")
print(json.dumps(r, ensure_ascii=False, indent=1)[:1500])
