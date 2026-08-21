"""--inspect-brk 主进程钩子：捕获工程打开时的全部加解密调用。
输出: probes/newfmt_crypto_cap.json"""
import io, sys, json, time, base64
sys.path.insert(0, r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

import urllib.request

HOOK = """
(function(){
  if (globalThis.__capHooked) return 'already';
  globalThis.__capHooked = true;
  globalThis.__cap = [];
  var req = process.mainModule ? process.mainModule.require : null;
  if (!req) return 'no require';
  var crypto = req('crypto');
  ['createDecipheriv','createCipheriv','pbkdf2Sync'].forEach(function(fn){
    var orig = crypto[fn];
    var wrapper = function(){
      try {
        var e = {fn: fn};
        if (fn === 'pbkdf2Sync') {
          e.pass = String(arguments[0]).slice(0,40);
          e.salt = String(arguments[1]).slice(0,40);
        } else {
          e.alg = arguments[0];
          e.keyHex = Buffer.from(arguments[1]).toString('hex').slice(0,64);
          e.ivHex = arguments[2] ?
            Buffer.from(arguments[2]).toString('hex').slice(0,32) : null;
        }
        e.stack = String(new Error().stack).slice(0,1000);
        globalThis.__cap.push(e);
      } catch(err){}
      return orig.apply(crypto, arguments);
    };
    try {
      Object.defineProperty(crypto, fn, {value: wrapper, writable: true,
                                         configurable: true});
    } catch(e) {
      // defineProperty 失败则改 hook Module 原型
      globalThis.__cap.push({fn: 'hookfail', method: fn,
                             err: String(e)});
    }
  });
  // 兜底：Module.prototype._load 拦截 crypto 模块获取
  try {
    var M = process.mainModule.constructor;
    var _load = M._load;
    M._load = function(req, parent, isMain){
      var m = _load.apply(this, arguments);
      if (req === 'crypto' && m && !m.__wrapped) {
        m.__wrapped = true;
        ['createDecipheriv','createCipheriv'].forEach(function(fn){
          var orig = m[fn];
          if (typeof orig !== 'function') return;
          Object.defineProperty(m, fn, {value: function(){
            try {
              globalThis.__cap.push({
                fn: 'M.'+fn, alg: arguments[0],
                keyHex: Buffer.from(arguments[1]).toString('hex')
                  .slice(0,64)});
            } catch(err){}
            return orig.apply(m, arguments);
          }, writable: true, configurable: true});
        });
      }
      return m;
    };
  } catch(e){}
  return 'hooks installed v2';
})()
"""

# ① 等待 Node target 出现（--inspect-brk 下启动即挂起）
print("等待 9229 Node target...")
node_t = None
for _ in range(30):
    time.sleep(1)
    try:
        targets = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:9229/json/list", timeout=3).read().decode())
        node_t = next((t for t in targets if t.get("type") == "node"), None)
        if node_t:
            break
    except Exception:
        pass
if not node_t:
    raise SystemExit("未找到 Node target")

ws = cdp.WS(node_t["webSocketDebuggerUrl"])
ws.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws.recv_text()
except SystemExit:
    pass

def ev(expr, tid=2, timeout=60):
    ws.send_json({"id": tid, "method": "Runtime.evaluate",
                  "params": {"expression": expr, "returnByValue": True}})
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = json.loads(ws.recv_text())
        if msg.get("id") == tid:
            r = msg.get("result", {})
            if "exceptionDetails" in r:
                print("EXC:", json.dumps(r["exceptionDetails"],
                                         ensure_ascii=False)[:300])
                return None
            return r.get("result", {}).get("value")
    raise SystemExit("超时")

# ② 预装钩子（此时主进程处于 brk 暂停态）
print("安装钩子:", ev(HOOK))

# ③ 放行
ws.send_json({"id": 50, "method": "Debugger.resume"})
try:
    while True:
        ws.recv_text()
except SystemExit:
    pass
except Exception:
    pass
print("已 resume，等待工程加载 40s...")
time.sleep(40)

# ④ 读取捕获（重连）
for _ in range(10):
    try:
        targets = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:9229/json/list", timeout=3).read().decode())
        node_t = next(t for t in targets if t.get("type") == "node")
        break
    except Exception:
        time.sleep(2)
ws = cdp.WS(node_t["webSocketDebuggerUrl"])
ws.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws.recv_text()
except SystemExit:
    pass

cap = ev("JSON.stringify(globalThis.__cap||[])")
data = json.loads(cap or "[]")
outp = r"D:\WorkDesigns\2_WorkProjects\E_distance\6_tools\lceda_sch_reader" \
       r"\probes\newfmt_crypto_cap.json"
with open(outp, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"捕获 {len(data)} 条调用 -> {outp}")
for d in data[:12]:
    print(json.dumps(d, ensure_ascii=False)[:220])
