"""全盘格式路由与后端验证（AGENTS.md 测试规则：脚本入 probes/）。

只读仓库自带 ../../examples/ 下 6 个工程文件（无外部绝对路径，换机可用）：
涡流/MCU（LcedaDB .eprj2）、Piezo（.eprj2 新版加密解密/.epro/.epro2 三格式同工程）、
TPS56C230（.epro）。逐一验证格式路由 + 冒烟（板/页/元件/网络计数），
再对 Piezo 三格式做交叉对比（元件数必须一致；板/页/网络差异仅 WARN，
已知：epro2 含孤儿旧 CBB 页 sch=?，页数 75 vs 73）。
"""
import io, sys, json, os, re, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # lceda_sch_reader/
sys.path.insert(0, ROOT)
import lceda_reader as lr

EXAMPLES = os.path.normpath(os.path.join(ROOT, '..', 'examples'))
FILES = [
    # (文件名, 期望: "ok"/"unsupported")
    ("涡流传感器.eprj2", "ok"),
    ("MCU主控-V1.1-2026.05.06.eprj2", "ok"),
    ("Piezo_Driver.eprj2", "ok"),  # 新版加密，需解密路径
    ("ProPrj_Piezo_Driver_2026-08-21.epro", "ok"),
    ("ProPrj_Piezo_Driver_2026-08-22.epro2", "ok"),
    ("ProPrj_TPS56C230_Buck_12Vto5V_6A_2026-08-13.epro", "ok"),
]
SEP_RE = re.compile("[,\u241f]")

def split_nets(v):
    return [t for t in SEP_RE.split(v) if t]

def open_db(path):
    r = lr.detect_backend(path)
    if r == "DECRYPT_NEW":   # 新版加密 .eprj2：解密 → 临时 .epro2
        tmp = lr._decrypt_new_eprj2(path)
        return lr.Epro2DB(tmp), "Epro2DB(解密)"
    db = r(path)
    return db, type(db).__name__

def smoke(path):
    """返回 dict(板数,页数,元件数,网络数) 或抛异常。"""
    db, cls_name = open_db(path)
    sheets = [s for s in db.sheets() if s[3] == 1]
    ncomp = 0
    for u, t, s, dt in sheets:
        sh = lr.parse_sheet(db, u)
        if sh:
            ncomp += len(sh["components"])
    nets = set()
    for u, t, s, dt in sheets:
        sh = lr.parse_sheet(db, u)
        if not sh:
            continue
        pinc = lr._collect_pinmap_data(db, sh, u)
        if not pinc:
            continue
        cp, ws, pw, ep = pinc
        dom = lr.resolve_nets_by_domain(db, sh, cp, ws, pw, ep)
        for k, v in dom.items():
            nets.update(split_nets(v))
    return {"boards": len(db._boards) if hasattr(db, "_boards") else
            len(list(db.schematics())), "pages": len(sheets),
            "comps": ncomp, "nets": len(nets), "_db": db,
            "_netset": nets, "_cls": cls_name}

print("=" * 100)
print(f"{'文件':52s} {'路由结果':28s} {'板':>4s} {'页':>4s} {'元件':>6s} {'网络':>6s}  结果")
print("=" * 100)
results = {}
all_ok = True
for name, expect in FILES:
    path = os.path.join(EXAMPLES, name)
    if not os.path.isfile(path):
        print(f"{name:52s} {'文件缺失':28s} {'-':>4s} {'-':>4s} "
              f"{'-':>6s} {'-':>6s}  FAIL(回归样本缺失)")
        results[name] = {"status": "missing"}
        all_ok = False
        continue
    try:
        cls = lr.detect_backend(path)
    except lr.UnsupportedFormatError:
        ok = "PASS" if expect in ("unsupported", "?") else "FAIL"
        print(f"{name:52s} {'UnsupportedFormatError':28s} {'-':>4s} {'-':>4s} "
              f"{'-':>6s} {'-':>6s}  {ok}(明确报错)")
        results[name] = {"status": "unsupported"}
        if expect == "ok":
            all_ok = False
        continue
    except Exception as e:
        print(f"{name:52s} 路由异常: {type(e).__name__}: {str(e)[:60]}  "
              f"{'PASS' if expect=='?' else 'FAIL'}")
        results[name] = {"status": "error", "err": str(e)}
        all_ok = False
        continue
    try:
        r = smoke(path)
        results[name] = {"status": "ok", **{k: v for k, v in r.items()
                                            if not k.startswith("_")}}
        print(f"{name:52s} {r['_cls']:28s} {r['boards']:>4d} {r['pages']:>4d} "
              f"{r['comps']:>6d} {r['nets']:>6d}  PASS")
    except Exception as e:
        print(f"{name:52s} {'?':28s} 冒烟失败: "
              f"{type(e).__name__}: {str(e)[:60]}  FAIL")
        results[name] = {"status": "smoke-error", "err": str(e)}
        all_ok = False

print("\n" + "=" * 60)
print("跨格式交叉对比（Piezo 同工程三格式：元件数必须一致）")
print("=" * 60)
trio = ["Piezo_Driver.eprj2", "ProPrj_Piezo_Driver_2026-08-21.epro",
        "ProPrj_Piezo_Driver_2026-08-22.epro2"]
maps = {}
for name in trio:
    path = os.path.join(EXAMPLES, name)
    try:
        db, cls = open_db(path)
    except Exception as e:
        print(f"[{name}] 打开失败: {type(e).__name__}: {str(e)[:80]}  FAIL")
        all_ok = False
        continue
    ns = set()
    ncomp = 0
    npages = 0
    for u, t, s, dt in db.sheets():
        if dt != 1:
            continue
        npages += 1
        sh = lr.parse_sheet(db, u)
        if not sh:
            continue
        ncomp += len(sh["components"])
        pinc = lr._collect_pinmap_data(db, sh, u)
        if not pinc:
            continue
        cp, ws, pw, ep = pinc
        dom = lr.resolve_nets_by_domain(db, sh, cp, ws, pw, ep)
        for v in dom.values():
            ns.update(split_nets(v))
    maps[name] = {"comps": ncomp, "pages": npages, "nets": ns, "cls": cls}
    print(f"[{name}] {cls}: 页{npages} 元件{ncomp} 网络{len(ns)}")
if len(maps) == 3:
    cs = {v["comps"] for v in maps.values()}
    if len(cs) == 1:
        print(f"元件数一致: {cs.pop()}  PASS")
    else:
        print(f"元件数不一致: { {k: v['comps'] for k, v in maps.items()} }  FAIL")
        all_ok = False
    a, b, c = (maps[trio[0]]["nets"], maps[trio[1]]["nets"],
               maps[trio[2]]["nets"])
    na, nb, nc = len(a), len(b), len(c)
    print(f"板/页/网: eprj2({maps[trio[0]]['cls']}) 页73 网{na} | "
          f"epro 页73 网{nb} | epro2 页75(多2孤儿旧CBB页) 网{nc}")
    if a == b == c:
        print("网络集合三格式零差异  PASS")
    else:
        ab, ac, bc = len(a & b), len(a & c), len(b & c)
        print(f"网络集合差异（WARN，已知 epro2 孤儿旧 CBB 页问题，待查）："
              f"三方共同{len(a & b & c)} 两两共同(ab/ac/bc)={ab}/{ac}/{bc} "
              f"仅eprj2:{len(a - b - c)} 仅epro:{len(b - a - c)} "
              f"仅epro2:{len(c - a - b)}")
        only = sorted((c - a - b))[:6]
        if only:
            print(f"  仅epro2样例: {only}")
else:
    print("三格式不全，跳过交叉对比  FAIL")
    all_ok = False

print("\n" + "=" * 60)
print("Piezo .epro 回归项：CBB 展开实例数（应 15）")
print("=" * 60)
READER = os.path.join(ROOT, "lceda_reader.py")
p = subprocess.run(
    [sys.executable, READER, "--eprj",
     os.path.join(EXAMPLES, "ProPrj_Piezo_Driver_2026-08-21.epro"),
     "netlist"], capture_output=True, text=True, encoding="utf-8",
    env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
    cwd=ROOT)
cbb_refs = re.findall(r"CBB\d+\.", p.stdout)
cbb = set(cbb_refs)
print(f"CBB 展开实例数: {len(cbb)}（引用 {len(cbb_refs)} 处）")
if p.returncode == 0 and len(cbb) == 15:
    print("CBB 展开  PASS")
else:
    print(f"CBB 展开  FAIL(rc={p.returncode})")
    all_ok = False

print("\nALL:", "PASS" if all_ok else "FAIL")
sys.exit(0 if all_ok else 1)
