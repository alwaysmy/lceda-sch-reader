"""新版加密 .eprj2 破解导出：经 CDP 从立创EDA 内存抽取解密后的全部文档，
打包为标准 .epro2（Epro2DB 可直接读取）。
用法: python export_newfmt.py <工程.eprj2>
前提: lceda-pro.exe 已以 --remote-debugging-port=9222 打开该工程。"""
import io, sys, json, sqlite3, base64, zipfile, time
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cdp", r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\probes\cdp_eval.py")
cdp = importlib.util.module_from_spec(spec)
sys.argv = ["cdp"]
spec.loader.exec_module(cdp)

import urllib.request

EPRJ = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2"

targets = json.loads(urllib.request.urlopen(
    "http://127.0.0.1:9222/json/list", timeout=5).read().decode())
t = next(x for x in targets if x["type"] == "page")
ws = cdp.WS(t["webSocketDebuggerUrl"])
ws.send_json({"id": 0, "method": "Runtime.enable"})
try:
    ws.recv_text()
except SystemExit:
    pass

def ev_await(expr, timeout=600):
    global _tid
    _tid += 1
    ws.send_json({"id": _tid, "method": "Runtime.evaluate",
                  "params": {"expression": expr, "returnByValue": True,
                             "awaitPromise": True}})
    t0 = time.time()
    while time.time() - t0 < timeout:
        msg = json.loads(ws.recv_text())
        if msg.get("id") == _tid:
            r = msg.get("result", {})
            if "exceptionDetails" in r:
                raise RuntimeError(json.dumps(
                    r["exceptionDetails"], ensure_ascii=False)[:300])
            return r.get("result", {}).get("value")
    raise SystemExit("evaluate 超时")

_tid = 100

# ① 结构树（来自 .eprj2 明文表）
conn = sqlite3.connect(f"file:{EPRJ}?mode=ro", uri=True)
st = json.loads(conn.execute(
    "SELECT structure FROM project_structures").fetchone()[0])
proj_uuid = conn.execute("SELECT uuid FROM projects").fetchone()[0]
conn.close()

def line(header_obj, body_obj, ticket):
    return (json.dumps(header_obj, ensure_ascii=False) + "||" +
            json.dumps(body_obj, ensure_ascii=False) + "|")

segments = []
ticket = 50000

def add_doc(doc_uuid, doc_type, meta_body, content_text=None):
    """合成 DOCHEAD(+META) 并附加实抓内容文本。"""
    global ticket
    segments.append(line({"type": "DOCHEAD", "ticket": ticket},
                         {"docType": doc_type, "uuid": doc_uuid,
                          "version": str(int(time.time() * 1000))},
                         ticket))
    ticket += 1
    if meta_body is not None:
        mb = dict(meta_body)
        segments.append(line({"type": "META", "ticket": ticket,
                              "id": "META"}, mb, ticket))
        ticket += 1
    if content_text:
        # 内容行自带 | 结尾，直接追加
        segments.append(content_text.rstrip("\n"))

# ② BOARD / SCH 层级段（structure 合成）
for b in st.get("boards", {}).values():
    add_doc(b["uuid"], "BOARD", {"title": b.get("title") or b["uuid"],
                                 "zIndex": b.get("zIndex")})
sch_board = {}
for su, s in st.get("schematics", {}).items():
    sch_board[su] = s
    add_doc(su, "SCH", {"title": s.get("name") or su,
                        "board": s.get("board") or ""})
for p in st.get("pcbs", {}).values():
    add_doc(p["uuid"], "PCB", {"title": p.get("title") or p["uuid"],
                               "board": p.get("board") or ""})

print("结构树: boards=%d schematics=%d sheets=%d pcbs=%d" % (
    len(st.get("boards", {})), len(st.get("schematics", {})),
    len(st.get("sheets", {})), len(st.get("pcbs", {}))))

# ③ SCH_PAGE 实抓（DOCHEAD+META 合成自 sheetCache 元数据 + 内容实抓）
# 以 structure.sheets 为权威清单（sheetCache 可能含已删页残留）
auth_sheets = set(st.get("sheets", {}).keys())
sheet_keys = [k for k in ev_await(
    "Object.keys(SCH.gVars.projectMgr.sheetCache.sheet)") if k in auth_sheets]
skipped = len(st.get("sheets", {})) - len(sheet_keys)
print(f"SCH_PAGE {len(sheet_keys)} 个（structure 权威，跳过残留 {skipped}），"
      f"逐页加载导出...")
ok = fail = 0
for i, su in enumerate(sheet_keys):
    try:
        meta_raw = ev_await(
            f"JSON.stringify(SCH.gVars.projectMgr.sheetCache.sheet"
            f"[{json.dumps(su)}])")
        meta = json.loads(meta_raw) if meta_raw else {}
        txt = ev_await(f"""
(async function(){{
  var dm = await SCH.docMemoryManager.getOrInitDoc({json.dumps(su)});
  var sc = dm.consistencyImpl.getSourceCode();
  if (sc && sc.then) sc = await sc;
  return String(sc);
}})()
""")
        if txt:
            add_doc(su, "SCH_PAGE", meta, content_text=txt)
            ok += 1
    except Exception as e:
        fail += 1
        print(f"  页失败 {su[:12]}: {str(e)[:80]}")
    if (i + 1) % 10 == 0:
        print(f"  进度 {i+1}/{len(sheet_keys)}")
print(f"SCH_PAGE 完成: 成功 {ok} 失败 {fail}")

# ④ SYMBOL 实抓（同三段式；META 含 docType=17 等 → CBB 映射关键）
sym_keys = ev_await("Object.keys(SCH.gVars.projectMgr.componentCache.symbol)")
print(f"SYMBOL {len(sym_keys)} 个...")
ok = fail = 0
for i, su in enumerate(sym_keys):
    try:
        meta_raw = ev_await(
            f"JSON.stringify(SCH.gVars.projectMgr.componentCache.symbol"
            f"[{json.dumps(su)}])")
        meta = json.loads(meta_raw) if meta_raw else {}
        txt = ev_await(f"""
(async function(){{
  var dm = await SCH.docMemoryManager.getOrInitDoc({json.dumps(su)});
  var sc = dm.consistencyImpl ? dm.consistencyImpl.getSourceCode() : null;
  if (sc && sc.then) sc = await sc;
  return String(sc||'');
}})()
""")
        if txt:
            add_doc(su, "SYMBOL", meta, content_text=txt)
            ok += 1
    except Exception:
        fail += 1
    if (i + 1) % 40 == 0:
        print(f"  进度 {i+1}/{len(sym_keys)}")
print(f"SYMBOL 完成: 成功 {ok} 失败 {fail}")

# ⑤ DEVICE 合成（deviceResult JSON）
dev_dump = ev_await("""
(function(){
  var d=SCH.gVars.projectMgr.componentCache.device;
  var out={};
  Object.keys(d).forEach(function(k){
    var v=d[k]; var r=v&&v.deviceResult?v.deviceResult:null;
    if(r) out[k]=r;
  });
  return out;
})()
""")
print(f"DEVICE {len(dev_dump)} 个（deviceResult 合成）")
for du, meta in dev_dump.items():
    add_doc(du, "DEVICE", meta)

# ⑥ INSTANCE 段（CBB 成员位号映射，Epro2DB.cbb_instances 需要）
inst_cnt = ev_await("""
(function(){
  var n=0; for(var k in window){ if(k.indexOf('_$')>0 && k.split('_$').length>=3) n++; }
  return n;
})()
""")
print(f"window 上疑似 INSTANCE 全局对象: {inst_cnt}（V3 导出可缺省，"
      f"cbb_instances 为空时回退原生符号映射）")

# ⑥ INSTANCE 段（CBB 成员母图位号映射，从 instanceAttrMgr.savedData 合成）
inst_dump = ev_await("""
(function(){
  var ia=SCH.gVars.projectMgr.instanceAttrMgr;
  var out={};
  ['savedData','unsavedData'].forEach(function(bucket){
    var b=ia[bucket]||{};
    Object.keys(b).forEach(function(k){
      try{ out[k]=b[k]; }catch(e){}
    });
  });
  return out;
})()
""")
print(f"INSTANCE 键: {len(inst_dump)}")
for iu, members in inst_dump.items():
    # iu 形如 <sch>_$<page>~<inst>_$<src>；members = {模板cid: {Designator:...}}
    parts = iu.split("_$")
    if len(parts) < 3:
        continue
    page = parts[1].split("~", 1)[0]
    inst_cid = parts[1].split("~", 1)[1]
    src = parts[2]
    segments.append(line({"type": "DOCHEAD", "ticket": ticket},
                         {"docType": "INSTANCE", "uuid": iu,
                          "version": str(int(time.time() * 1000))},
                         ticket))
    ticket += 1
    for mid, mval in (members or {}).items():
        segments.append(line({"type": "INSTANCE_ATTR", "ticket": ticket,
                              "id": mid}, mval, ticket))
        ticket += 1
    _ = (page, inst_cid, src)   # 编码信息保留在 uuid 中

# ⑦ 打包 .epro2
import os
stem = os.path.splitext(os.path.basename(EPRJ))[0]
outdir = os.path.dirname(EPRJ)
outpath = os.path.join(outdir, stem + "_export.epro2")
epru_name = stem + ".epru"
epru_text = "\n".join(segments) + "\n"
with zipfile.ZipFile(outpath, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("project2.json", json.dumps(
        {"title": stem, "cbb_project": False, "editorVersion": "export"},
        ensure_ascii=False))
    zf.writestr(epru_name, epru_text)
print(f"\n导出完成: {outpath}")
print(f"  epru 文本 {len(epru_text)/1e6:.1f} MB, 段数 {len(segments)}")
