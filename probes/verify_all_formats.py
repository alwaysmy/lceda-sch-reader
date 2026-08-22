"""全盘工程文件格式路由与后端验证（AGENTS.md 测试规则：脚本入 probes/）。
对电脑上全部 .eprj2/.epro/.epro2 逐一验证：格式路由 + 冒烟命令 + 跨格式
交叉对比（同工程 .eprj2 vs .epro2 的 板/页/元件/网络集合）。"""
import io, sys, json, subprocess, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
TOOL = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader\lceda_reader.py"
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

FILES = [
    # (路径, 期望: "ok"/"unsupported")
    (r"C:\Users\dell\Documents\LCEDA-Pro\example-projects\示例工程_3D外壳设计.eprj2", "?"),
    (r"C:\Users\dell\Documents\LCEDA-Pro\example-projects\示例工程_彩色丝印设计.eprj2", "?"),
    (r"C:\Users\dell\Documents\LCEDA-Pro\example-projects\示例工程_面板打印设计.eprj2", "?"),
    (r"C:\Users\dell\Documents\LCEDA-Pro\example-projects\示例工程_快速入门.eprj2", "?"),
    (r"C:\Users\dell\Documents\LCEDA-Pro\example-projects\示例工程_FPC补强设计.eprj2", "?"),
    (r"C:\Users\dell\Documents\LCEDA-Pro\projects\Piezo_Driver.eprj2", "ok"),
    (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器-V1.0-2026.04.01.eprj2", "ok"),
    (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\V1.1版主控原理图\MCU主控-V1.1-2026.05.06.eprj2", "?"),
    (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2", "ok"),
    (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_Piezo_Driver_2026-08-21.epro", "ok"),
    (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples\ProPrj_TPS56C230_Buck_12Vto5V_6A_2026-08-13.epro", "ok"),
    (r"C:\Users\dell\Downloads\ProPrj_Piezo_Driver_2026-08-21.epro2", "ok"),
    (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器_backup\涡流传感器_2026-08-10-14-47.epro2", "ok"),
    (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\V1.1版主控原理图\MCU主控-V1.1-2026.05.06_backup\MCU主控-V1.1-2026.05.06_2026-08-07-14-46.epro2", "ok"),
    (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器_backup\涡流传感器_2026-08-06-18-56.epro2", "ok"),
]

def smoke(path):
    """返回 dict(板数,页数,元件数,网络数) 或抛异常。"""
    r = lr.detect_backend(path)
    if r == "DECRYPT_NEW":   # 新版加密 .eprj2：解密 → 临时 .epro2
        tmp = lr._decrypt_new_eprj2(path)
        db = lr.Epro2DB(tmp)
        cls_name = "Epro2DB(解密)"
    else:
        db = r(path)
        cls_name = type(db).__name__
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
            for tok in v.split(","):
                if tok:
                    nets.add(tok)
    return {"boards": len(db._boards) if hasattr(db, "_boards") else
            len(list(db.schematics())), "pages": len(sheets),
            "comps": ncomp, "nets": len(nets), "_db": db,
            "_netset": nets, "_cls": cls_name}

print("=" * 100)
print(f"{'文件':52s} {'路由结果':28s} {'板':>4s} {'页':>4s} {'元件':>6s} {'网络':>6s}  结果")
print("=" * 100)
results = {}
for path, expect in FILES:
    name = path.replace("\\", "/").split("/")[-1]
    try:
        cls = lr.detect_backend(path)
    except lr.UnsupportedFormatError as e:
        ok = "PASS" if expect in ("unsupported", "?") else "FAIL"
        print(f"{name:52s} {'UnsupportedFormatError':28s} {'-':>4s} {'-':>4s} "
              f"{'-':>6s} {'-':>6s}  {ok}(明确报错)")
        results[path] = {"status": "unsupported"}
        continue
    except Exception as e:
        print(f"{name:52s} 路由异常: {type(e).__name__}: {str(e)[:60]}  "
              f"{'PASS' if expect=='?' else 'FAIL'}")
        results[path] = {"status": "error", "err": str(e)}
        continue
    try:
        r = smoke(path)
        results[path] = {"status": "ok", **{k: v for k, v in r.items()
                                            if not k.startswith("_")}}
        print(f"{name:52s} {r['_cls']:28s} {r['boards']:>4d} {r['pages']:>4d} "
              f"{r['comps']:>6d} {r['nets']:>6d}  PASS")
    except Exception as e:
        print(f"{name:52s} {'?':28s} 冒烟失败: "
              f"{type(e).__name__}: {str(e)[:60]}  FAIL")
        results[path] = {"status": "smoke-error", "err": str(e)}

print("\n" + "=" * 60)
print("跨格式交叉对比（同工程 .eprj2 vs .epro2）")
print("=" * 60)
pairs = [
    ("涡流传感器", FILES[8][0], FILES[12][0]),
    ("MCU主控-V1.1", FILES[7][0], FILES[13][0]),
]
for tag, f_old, f_new in pairs:
    ro, rn = results.get(f_old), results.get(f_new)
    if not ro or not rn or ro.get("status") != "ok" or rn.get("status") != "ok":
        print(f"[{tag}] 跳过（一侧不可用: {ro and ro.get('status')} / "
              f"{rn and rn.get('status')}）")
        continue
    print(f"[{tag}] eprj2: 板{ro['boards']} 页{ro['pages']} 元件{ro['comps']} "
          f"网{ro['nets']}  |  epro2: 板{rn['boards']} 页{rn['pages']} "
          f"元件{rn['comps']} 网{rn['nets']}")
    # 网络名集合差异
    db_o = lr.detect_backend(f_old)(f_old)
    db_n = lr.detect_backend(f_new)(f_new)
    def netset(db):
        ns = set()
        for u, t, s, dt in db.sheets():
            if dt != 1:
                continue
            sh = lr.parse_sheet(db, u)
            if not sh:
                continue
            pinc = lr._collect_pinmap_data(db, sh, u)
            if not pinc:
                continue
            cp, ws, pw, ep = pinc
            dom = lr.resolve_nets_by_domain(db, sh, cp, ws, pw, ep)
            for k, v in dom.items():
                ns.update(t for t in v.split(",") if t)
        return ns
    so, sn = netset(db_o), netset(db_n)
    only_o, only_n = so - sn, sn - so
    print(f"   网络集合: 共同{len(so & sn)}  仅eprj2:{len(only_o)}  "
          f"仅epro2:{len(only_n)}")
    if only_o:
        print(f"     仅eprj2 样例: {sorted(only_o)[:6]}")
    if only_n:
        print(f"     仅epro2 样例: {sorted(only_n)[:6]}")
