"""主进程 crypto/zlib 钩子 + 渲染层 reload 触发工程重开 → 捕获解密调用。
(v2: 修复 continue 语法错误，简化钩子结构)"""
import io, sys, json, time
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

import urllib.request

node_t = page_t = None
for _ in range(15):
    try:
        targets = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:9229/json/list", timeout=3).read().decode())
        node_t = next((t for t in targets if t.get("type") == "node"), None)
        pages = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:9222/json/list", timeout=3).read().decode())
        page_t = next((t for t in pages if t.get("type") == "page"), None)
        if node_t and page_t:
            break
    except Exception:
        pass
    time.sleep(2)

ws_n = cdp.WS(node_t["webSocketDebuggerUrl"])
ws_n.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws_n.recv_text()
except SystemExit:
    pass

def ev_n(expr, tid=2, timeout=60):
    ws_n.send_json({"id": tid, "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True}})
    t0 = time.time()
    while time.time() - t0 < timeout:
        m = json.loads(ws_n.recv_text())
        if m.get("id") == tid:
            r = m.get("result", {})
            if "exceptionDetails" in r:
                return "EXC: " + json.dumps(r["exceptionDetails"])[:300]
            return r.get("result", {}).get("value")
    raise SystemExit("超时")

HOOK = """
(function(){
  if (globalThis.__capHooked) return 'already';
  globalThis.__capHooked = true;
  globalThis.__cap = [];
  var req = process.mainModule.require;
  var zlib = req('zlib');
  var fns = ['createDecipheriv','createCipheriv','createInflate',
             'createGunzip','createUnzip','inflateSync','gunzipSync',
             'unzipSync'];
  var hookedCount = 0;
  fns.forEach(function(fn){
    var orig = zlib[fn];
    if (typeof orig !== 'function') return;
    var wrapper = function(){
      try {
        var e = {fn: 'zlib.'+fn};
        if (typeof arguments[0] === 'string' || Buffer.isBuffer(arguments[0])) {
          var d = arguments[0];
          e.dlen = d.length;
          e.dhead = d.slice ? d.slice(0,8).toString('hex')
                             : Array.prototype.slice.call(d,0,4).toString();
        }
        e.stack = String(new Error().stack).slice(0,600);
        globalThis.__cap.push(e);
      } catch(err){}
      return orig.apply(zlib, arguments);
    };
    Object.defineProperty(zlib, fn,
      {value: wrapper, writable: true, configurable: true});
    hookedCount++;
  });
  // crypto 的 decipher/cipher
  try {
    var cr = req('crypto');
    ['createDecipheriv','createCipheriv'].forEach(function(fn){
      if (typeof cr[fn] !== 'function') return;
      var orig = cr[fn];
      var w = function(){
        try {
          globalThis.__cap.push({
            fn: 'crypto.'+fn, alg: arguments[0],
            keyHex: arguments[1] ?
              Buffer.from(arguments[1]).toString('hex').slice(0,64) : null});
        } catch(err){}
        return orig.apply(cr, arguments);
      };
      Object.defineProperty(cr, fn,
        {value: w, writable: true, configurable: true});
      hookedCount++;
    });
  } catch(e){}
  return 'hooked '+hookedCount+' functions';
})()
"""

r = ev_n(HOOK)
print("主进程钩子:", r)

# 渲染层 reload 触发工程重开
ws_p = cdp.WS(page_t["webSocketDebuggerUrl"])
ws_p.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws_p.recv_text()
except SystemExit:
    pass
ws_p.send_json({"id": 88, "method": "Page.reload"})
print("reload 触发，等待 35s...")
time.sleep(35)

cap = ev_n("JSON.stringify(globalThis.__cap||[])")
data = json.loads(cap or "[]")
outp = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool"
        r"\lceda_sch_reader\probes\crypto_capture.json")
with open(outp, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"捕获 {len(data)} 条 -> {outp}")
for d in data[:15]:
    print(json.dumps(d, ensure_ascii=False)[:250])
