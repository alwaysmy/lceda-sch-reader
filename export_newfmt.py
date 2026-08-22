"""完善版导出：从运行中的 LCEDA 提取全部解密内容 → 标准 .epro2。
用法: python export_newfmt.py <工程.eprj2路径>
前提: lceda-pro.exe --remote-debugging-port=9222 <同一工程> 已启动。
产物: <工程目录>/<stem>_export.epro2（Epro2DB 可直接读取）。"""
import io, sys, json, sqlite3, base64, zipfile, time, os, re
_probes = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probes")
sys.path.insert(0, _probes)
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", os.path.join(_probes, "cdp_eval.py"))
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

import urllib.request

EPRJ = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"

# ── CDP 连接 ──
targets = json.loads(urllib.request.urlopen(
    "http://127.0.0.1:9222/json/list", timeout=5).read().decode())
t = next(x for x in targets if x["type"] == "page")
ws = cdp.WS(t["webSocketDebuggerUrl"])
ws.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws.recv_text()
except SystemExit:
    pass

_tid = [100]

def ev_await(expr, timeout=600):
    _tid[0] += 1
    tid = _tid[0]
    ws.send_json({"id": tid, "method": "Runtime.evaluate",
                  "params": {"expression": expr, "returnByValue": True,
                             "awaitPromise": True}})
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = json.loads(ws.recv_text())
        if msg.get("id") == tid:
            r = msg.get("result", {})
            if "exceptionDetails" in r:
                raise RuntimeError(json.dumps(
                    r["exceptionDetails"], ensure_ascii=False)[:300])
            return r.get("result", {}).get("value")
    raise SystemExit(f"evaluate 超时 ({timeout}s)")

def batch_get(expr_fn, keys, label):
    """批量 evaluate（每批 5 个防超时）。"""
    results = {}
    total = len(keys)
    for bi in range(0, total, 5):
        batch = keys[bi:bi+5]
        js_items = []
        for k in batch:
            js_items.append(f'''
      try {{
        var dm = await SCH.docMemoryManager.getOrInitDoc({json.dumps(k)});
        var sc = dm.consistencyImpl.getSourceCode();
        if (sc && sc.then) sc = await sc;
        out[{json.dumps(k)}] = String(sc||'');
      }} catch(e) {{ out[{json.dumps(k)}] = ''; }}''')
        expr = ("(async function(){ var out={};\n" +
                "\n".join(js_items) + "\n  return out; })()")
        r = ev_await(expr)
        if r:
            results.update(r)
        print(f"  {label} {min(bi+5,total)}/{total}")
    return results

# ── 结构树（来自 .eprj2 明文表） ──
conn = sqlite3.connect(f"file:{EPRJ}?mode=ro", uri=True)
st = json.loads(conn.execute(
    "SELECT structure FROM project_structures").fetchone()[0])
conn.close()

segments = []
ticket = [50000]

def add_doc(doc_uuid, doc_type, meta_body=None, content=None):
    segments.append(json.dumps(
        {"type": "DOCHEAD", "ticket": ticket[0]},
        ensure_ascii=False) + "||" +
        json.dumps({"docType": doc_type, "uuid": doc_uuid},
                   ensure_ascii=False) + "|")
    ticket[0] += 1
    if meta_body:
        segments.append(json.dumps(
            {"type": "META", "ticket": ticket[0], "id": "META"},
            ensure_ascii=False) + "||" +
            json.dumps(meta_body, ensure_ascii=False) + "|")
        ticket[0] += 1
    if content:
        for ln in content.rstrip("\n").split("\n"):
            segments.append(ln)

# BOARD/SCH/PCB 层级合成
for b in st.get("boards", {}).values():
    add_doc(b["uuid"], "BOARD",
            {"title": b.get("title") or b["uuid"],
             "zIndex": b.get("zIndex")})
for su, s in st.get("schematics", {}).items():
    add_doc(su, "SCH", {"title": s.get("name") or su,
                        "board": s.get("board") or ""})
for p in st.get("pcbs", {}).values():
    add_doc(p["uuid"], "PCB", {"title": p.get("title") or p["uuid"],
                               "board": p.get("board") or ""})

print(f"结构树: boards={len(st.get('boards',{}))} "
      f"schematics={len(st.get('schematics',{}))} "
      f"sheets={len(st.get('sheets',{}))} pcbs={len(st.get('pcbs',{}))}")

# SCH_PAGE 实抓
auth_sheets = set(st.get("sheets", {}).keys())
sheet_keys = ev_await("Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)")
sheet_keys = [k for k in sheet_keys if k in auth_sheets]
print(f"SCH_PAGE: {len(sheet_keys)} 个")
page_results = batch_get(None, sheet_keys, "page")
for su, txt in page_results.items():
    if txt:
        meta_raw = ev_await(
            f"JSON.stringify(SCH.gVars.projectMgr.sheetCache.sheet"
            f"[{json.dumps(su)}])")
        meta = json.loads(meta_raw) if meta_raw else {}
        add_doc(su, "SCH_PAGE", meta, content=txt)

# SYMBOL 实抓
sym_keys = ev_await("Object.keys(SCH.gVars.projectMgr.componentCache.symbol)")
print(f"SYMBOL: {len(sym_keys)} 个")
sym_results = batch_get(None, sym_keys, "symbol")
for su, txt in sym_results.items():
    if txt:
        meta_raw = ev_await(
            f"JSON.stringify(SCH.gVars.projectMgr.componentCache.symbol"
            f"[{json.dumps(su)}])")
        meta = json.loads(meta_raw) if meta_raw else {}
        add_doc(su, "SYMBOL", meta, content=txt)

# DEVICE 合成
dev_dump = ev_await("""
(function(){
  var d=SCH.gVars.projectMgr.componentCache.device;
  var out={};
  Object.keys(d).forEach(function(k){
    var v=d[k];
    if(v && v.deviceResult) out[k]=v.deviceResult;
  });
  return out;
})()
""")
print(f"DEVICE: {len(dev_dump)} 个")
for du, meta in dev_dump.items():
    add_doc(du, "DEVICE", meta)

# INSTANCE 合成
inst_dump = ev_await("""
(function(){
  var ia=SCH.gVars.projectMgr.instanceAttrMgr;
  var out={};
  ['savedData','unsavedData'].forEach(function(bucket){
    var b=ia[bucket]||{};
    Object.keys(b).forEach(function(k){ try{out[k]=b[k];}catch(e){} });
  });
  return out;
})()
""")
print(f"INSTANCE: {len(inst_dump)} 个")
for iu, members in inst_dump.items():
    parts = iu.split("_$")
    if len(parts) < 3:
        continue
    segments.append(json.dumps(
        {"type": "DOCHEAD", "ticket": ticket[0]},
        ensure_ascii=False) + "||" +
        json.dumps({"docType": "INSTANCE", "uuid": iu},
                   ensure_ascii=False) + "|")
    ticket[0] += 1
    for mid, mval in (members or {}).items():
        segments.append(json.dumps(
            {"type": "INSTANCE_ATTR", "ticket": ticket[0], "id": mid},
            ensure_ascii=False) + "||" +
            json.dumps(mval, ensure_ascii=False) + "|")
        ticket[0] += 1

# ── 打包 ──
stem = os.path.splitext(os.path.basename(EPRJ))[0]
outdir = os.path.dirname(EPRJ)
outpath = os.path.join(outdir, stem + "_export.epro2")
epru_name = stem + ".epru"
epru_text = "\n".join(segments) + "\n"
with zipfile.ZipFile(outpath, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("project2.json", json.dumps(
        {"title": stem, "cbb_project": False,
         "editorVersion": "export"}, ensure_ascii=False))
    zf.writestr(epru_name, epru_text)
print(f"\n导出完成: {outpath}")
print(f"  epru 文本 {len(epru_text)/1e6:.1f} MB, 段数 {len(segments)}")
