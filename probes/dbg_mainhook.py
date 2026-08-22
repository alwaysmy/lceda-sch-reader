"""主进程 crypto 钩子 + 渲染层 reload 触发工程重开 → 捕获解密调用。"""
import io, sys, json, time, base64
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

import urllib.request

# ① 等主进程与页面就绪
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
if not (node_t and page_t):
    raise SystemExit("targets 未就绪（LCEDA 是否以 --inspect=9229 --remote-debugging-port=9222 启动？）")

# ② 主进程装钩子（mainModule.require 路径）
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
                return "EXC: " + json.dumps(r["exceptionDetails"])[:200]
            return r.get("result", {}).get("value")
    raise SystemExit("超时")

r = ev_n("""
(function(){
  if (globalThis.__capHooked) return 'already';
  globalThis.__capHooked = true;
  globalThis.__cap = [];
  var req = process.mainModule.require;
  var crypto = req('crypto');
  ['createDecipheriv','createCipheriv','createInflate','createGunzip',
   'createUnzip'].forEach(function(fn){
    if (typeof crypto[fn] !== 'function' &&
        typeof require('zlib')[fn] !== 'function') {
      try { var z = req('zlib'); if (typeof z[fn] !== 'function') return; }
      catch(e){ return; }
    }
    var owner = null;
    try { if (crypto[fn]) owner = crypto; } catch(e){}
    if (!owner) { try { owner = req('zlib'); } catch(e){ continue; } }
    var orig = owner[fn];
    Object.defineProperty(owner, fn, {value: function(){
      try {
        var e = {fn: fn};
        if (arguments[0] && typeof arguments[0]==='string') e.alg = arguments[0];
        if (arguments[1] && arguments[1].length)
          e.key = Buffer.from(arguments[1]).toString('hex').slice(0,64);
        if (arguments[2] && arguments[2].length)
          e.iv = Buffer.from(arguments[2]).toString('hex').slice(0,32);
        e.stack = String(new Error().stack).slice(0,800);
        globalThis.__cap.push(e);
      } catch(err){}
      return orig.apply(owner, arguments);
    }, writable: true, configurable: true});
  });
  return 'hooks installed';
})()
""")
print("主进程钩子:", r)

# ③ 渲染层 reload 触发工程重开
ws_p = cdp.WS(page_t["webSocketDebuggerUrl"])
ws_p.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws_p.recv_text()
except SystemExit:
    pass
ws_p.send_json({"id": 88, "method": "Page.reload"})
print("reload 触发，等待 35s...")
time.sleep(35)

# ④ 读捕获
cap = ev_n("JSON.stringify(globalThis.__cap||[])")
data = json.loads(cap or "[]")
outp = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool"
        r"\lceda_sch_reader\probes\crypto_capture.json")
with open(outp, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"捕获 {len(data)} 条 -> {outp}")
for d in data[:10]:
    print(json.dumps(d, ensure_ascii=False)[:250])
