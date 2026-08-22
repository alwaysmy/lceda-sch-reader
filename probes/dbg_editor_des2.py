"""精确获取 quadPizeoDriver_RevA 的 ControlDAC_A 页全部元件位号。"""
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
                print("EXC:", json.dumps(r["exceptionDetails"])[:400])
                return None
            return r.get("result", {}).get("value")
    return "(超时)"

# Step 1: 列出全部 sheet 及其归属板
r = ev("""
(function(){
  var pm = SCH.gVars.projectMgr;
  var out = [];
  Object.keys(pm.sheetCache.sheet).forEach(function(k){
    var s = pm.sheetCache.sheet[k];
    out.push({uuid:k, title:s.title, sch:s.schematic_uuid});
  });
  return JSON.stringify(out);
})()
""")
sheets = json.loads(r)
print(f"总页数: {len(sheets)}")

# 找 quadPizeoDriver_RevA 的 ControlDAC_A
# 需要知道哪个 sch_uuid 对应 quadPizeoDriver_RevA 板
# 从 BOARD 文档的 META 找
board_sch_map = {}
for u, d in db_docs if False else []:
    pass

# 直接从编辑器查
r = ev("""
(function(){
  var pm = SCH.gVars.projectMgr;
  // 查 projectMgr 的 path 或其他属性确定当前打开的是哪个工程
  return JSON.stringify({
    uuid: pm.uuid || 'N/A',
    title: pm.title || 'N/A',
    path: pm.path || 'N/A',
    isCBB: pm.isCBB
  });
})()
""")
print("projectMgr:", r)

# Step 2: 尝试加载每个 ControlDAC_A 页并列出元件位号
for s in sheets:
    if "controldac_a" not in s["title"].lower():
        continue
    print(f"\n== {s['title']} (sch={s['sch'][:12]}) ==")
    
    expr = f"""
    (async function(){{
      var dm = await SCH.docMemoryManager.getOrInitDoc({json.dumps(s['uuid'])});
      var shapes = [];
      var mm = dm.shapeManager.modelMap;
      mm.forEach(function(shape, id) {{
        try {{
          var desig = '';
          var devTitle = '';
          try {{ desig = shape.getAttr('Designator') || ''; }} catch(e){{}}
          try {{ devTitle = shape.getAttr('Device') || ''; }} catch(e){{}}
          // 也检查 Name attr（V3 的实例名）
          var name = '';
          try {{ name = shape.getAttr('Name') || ''; }} catch(e){{}}
          if (desig) {{
            shapes.push({{desig: desig, device: String(devTitle).slice(0,40), name: String(name).slice(0,30)}});
          }}
        }} catch(e){{}}
      }});
      return JSON.stringify(shapes);
    }})()
    """
    shapes_json = ev(expr)
    if shapes_json and shapes_json != "(超时)":
        try:
            shapes = json.loads(shapes_json)
            # 只输出 CBB 和主要器件
            cbb_items = [s for s in shapes if "CBB" in s.get("desig","")]
            other_items = [s for s in shapes 
                          if s.get("desig") and not s.get("desig","").startswith(("PORT","SHORT"))]
            print(f"  有位号元件数: {len(other_items)}")
            print(f"  CBB 实例:")
            for it in cbb_items:
                print(f"    {it['desig']}  device={it.get('device','')[:30]}")
            print(f"  主要器件(非CBB/PORT):")
            for it in other_items[:20]:
                d = it.get("desig","")
                if d and not d.startswith(("PORT","SHORT")):
                    print(f"    {d:10s} {it.get('device','')[:35]}")
        except Exception as e:
            print(f"  解析失败: {e}")
    else:
        print(f"  加载失败或无数据")
