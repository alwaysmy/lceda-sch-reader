"""直接从编辑器内存中提取全部文档明文（不依赖 dispose/reload）。"""
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
                print("EXC:", json.dumps(r["exceptionDetails"])[:300])
                return None
            return r.get("result", {}).get("value")
    return "(超时)"

# 遍历全部页，逐个 getOrInitDoc + getSourceCode（不 dispose）
sheets = ev("Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)")
print(f"页数: {len(sheets)}")

all_docs = {}
for i, su in enumerate(sheets):
    expr = f"""
    (async function(){{
      var dm = await SCH.docMemoryManager.getOrInitDoc({json.dumps(su)});
      var sc = dm.consistencyImpl.getSourceCode();
      if (sc && sc.then) sc = await sc;
      return String(sc||'');
    }})()
    """
    txt = ev(expr)
    if txt and len(txt) > 10:
        all_docs[su] = txt
    if (i+1) % 20 == 0:
        print(f"  进度 {i+1}/{len(sheets)}")

print(f"成功获取 {len(all_docs)} 个文档的明文")
total_chars = sum(len(v) for v in all_docs.values())
print(f"总字符数: {total_chars}")

# 也获取 symbols
syms = ev("Object.keys(SCH.gVars.projectMgr.componentCache.symbol)")
sym_docs = {}
for su in syms[:50]:  # 先取前50个验证
    expr = f"""
    (async function(){{
      var dm = await SCH.docMemoryManager.getOrInitDoc({json.dumps(su)});
      var sc = dm.consistencyImpl ? dm.consistencyImpl.getSourceCode() : null;
      if (sc && sc.then) sc = await sc;
      return String(sc||'');
    }})()
    """
    txt = ev(expr)
    if txt and len(txt) > 10:
        sym_docs[su] = txt
print(f"符号明文: {len(sym_docs)}")

# 保存到文件
out = {"sheets": all_docs, "symbols": sym_docs}
outp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "mem_dump.json")
with open(outp, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
print(f"\n保存到: {outp}")
