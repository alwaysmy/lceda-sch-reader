"""hook PP 函数捕获解密参数（key/iv/dataStrId）。"""
import io, sys, json, time, socket
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

ws = cdp.WS(t["webSocketDebuggerUrl"])
mid = [0]

def send(method, params=None):
    mid[0] += 1
    ws.send_json({"id": mid[0], "method": method,
                  "params": params or {}})
    return mid[0]

def recv_result(want, timeout=30):
    ws.sock.settimeout(timeout)
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            m = json.loads(ws.recv_text())
        except socket.timeout:
            break
        if m.get("id") == want:
            r = m.get("result", {})
            if "exceptionDetails" in r:
                print("EXC:", json.dumps(r["exceptionDetails"])[:300])
                return None
            return r.get("result", {}).get("value")
    return "(超时)"

# 先确保一个文档已加载（docManager 存在）
r = send("Runtime.evaluate", {"expression":
    "(async function(){"
    " var su=Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)[0];"
    " await SCH.docMemoryManager.getOrInitDoc(su);"
    " return 'loaded';})()", "awaitPromise": True})
print("预加载:", recv_result(r))

# 找到 decodeAndRealTimeSyncHandler 并 hook 其 getSourceCode 之前的初始化路径
# 更直接：hook crypto.subtle.decrypt 和 fetch，然后 dispose+重载
HOOK = """
(function(){
  window.__cap2 = [];
  // hook fetch
  var of = window.fetch;
  window.fetch = function(){
    var url = arguments[0];
    if (typeof url === 'string' && url.length > 20) {
      window.__cap2.push({type:'fetch', url:url.slice(0,120)});
    }
    return of.apply(this, arguments);
  };
  // hook TextDecoder for large decodes
  var td = TextDecoder.prototype.decode;
  TextDecoder.prototype.decode = function(buf, opts){
    var r = td.call(this, buf, opts);
    try {
      if (r && r.length > 500 && r.indexOf('{') >= 0 &&
          r.indexOf('ticket') >= 0) {
        window.__cap2.push({type:'TextDecoder', len:r.length,
          head:r.slice(0,80)});
      }
    } catch(e){}
    return r;
  };
  // hook Vke.prototype.init（加密工具类）
  // Vke 可能不在全局——但可以通过已有 docManager 的 handler 找到
  return 'hooks installed, cap2 ready';
})()
"""
tid = send("Runtime.evaluate", {"expression": HOOK})
print("hook:", recv_result(tid))

# dispose + 重载触发完整加载链路（包括可能的 fetch 解密）
tid = send("Runtime.evaluate", {"expression": """
(async function(){
  var su = Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)[0];
  SCH.docMemoryManager.dispose();
  // 清除可能的内容缓存
  var pm = SCH.gVars.projectMgr;
  Object.keys(pm.sheetCache.sheet).forEach(function(k){
    delete pm.sheetCache.sheet[k].dataStrId;
    delete pm.sheetCache.sheet[k].dataStr;
  });
  var dm = await SCH.docMemoryManager.getOrInitDoc(su);
  var sc = dm.consistencyImpl.getSourceCode();
  if (sc && sc.then) sc = await sc;
  return {srclen:String(sc||'').length, cap:(window.__cap2||[]).slice(0,10)};
})()
""", "awaitPromise": True})
res = recv_result(tid, timeout=60)
if res:
    val = res.get("result", {}).get("result", {}).get("value")
    if val:
        d = json.loads(val) if isinstance(val, str) else val
        print(f"srclen={d.get('srclen')} cap数={d.get('cap')}")
        for c in (d.get('cap') or [])[:5]:
            print(f"  {json.dumps(c, ensure_ascii=False)[:150]}")
    else:
        print("val=None")
else:
    print("evaluate 超时")
