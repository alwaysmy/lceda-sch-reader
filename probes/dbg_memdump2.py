"""从编辑器内存提取全部文档明文（不 dispose，直接 getOrInitDoc + getSourceCode）。
输出: probes/mem_dump.json"""
import io, sys, json, time, os, socket
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cdp_eval.py"))
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

import urllib.request
targets = json.loads(urllib.request.urlopen(
    "http://127.0.0.1:9222/json/list", timeout=5).read().decode())
t = next(x for x in targets if x["type"] == "page")

ws = cdp.WS(t["webSocketDebuggerUrl"])
mid = [0]

def ev(expr, timeout=120):
    mid[0] += 1
    ws.send_json({"id": mid[0], "method": "Runtime.evaluate",
                  "params": {"expression": expr, "returnByValue": True,
                             "awaitPromise": True}})
    ws.sock.settimeout(timeout)
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            m = json.loads(ws.recv_text())
        except socket.timeout:
            break
        if m.get("id") == mid[0]:
            r = m.get("result", {})
            if "exceptionDetails" in r:
                return None
            return r.get("result", {}).get("value")
    return None

sheets = ev("Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)")
if not sheets:
    print("无法获取页列表")
    sys.exit(1)
print(f"页数: {len(sheets)}")

all_docs = {}
for i, su in enumerate(sheets):
    expr = f"""(async function(){{
      var dm = await SCH.docMemoryManager.getOrInitDoc({json.dumps(su)});
      var sc = dm.consistencyImpl.getSourceCode();
      if (sc && sc.then) sc = await sc;
      return String(sc||'');
    }})()"""
    txt = ev(expr)
    if txt and len(txt) > 10:
        all_docs[su] = txt
    if (i+1) % 20 == 0:
        print(f"  进度 {i+1}/{len(sheets)}")

print(f"成功获取明文的页数: {len(all_docs)}")
total_chars = sum(len(v) for v in all_docs.values())
print(f"总字符数: {total_chars}")

syms = ev("Object.keys(SCH.gVars.projectMgr.componentCache.symbol)")
sym_docs = {}
if syms:
    for su in syms:
        expr = f"""(async function(){{
          var dm = await SCH.docMemoryManager.getOrInitDoc({json.dumps(su)});
          var sc = dm.consistencyImpl.getSourceCode();
          if (sc && sc.then) sc = await sc;
          return String(sc||'');
        }})()"""
        txt = ev(expr)
        if txt and len(txt) > 10:
            sym_docs[su] = txt

print(f"符号明文数: {len(sym_docs)}")

outp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mem_dump.json")
with open(outp, "w", encoding="utf-8") as f:
    json.dump({"sheets": all_docs, "symbols": sym_docs}, f,
              ensure_ascii=False)
sz = os.path.getsize(outp)
print(f"保存到: {outp} ({sz/1e6:.1f} MB)")
