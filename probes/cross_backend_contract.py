"""跨后端一致性测试：同一操作在三种格式上的行为契约。

从原理出发的隐藏问题排查：
1. sheets()/sheet_records() 的 doc_type 参数在各后端语义是否一致
2. symbol_records() 三后端可用性（V3 缺失 → 渲染退化）
3. device_attrs/symbol_of_device 空值行为
4. hierarchy() 板关联（新 eprj2 structure 未消费问题）
5. pcb_docs 空 PCB / 无 PCB 工程行为
6. resolve_page 同名页 + --schematic 过滤
7. parse_sheet 对 PCB 文档（docType=3）误用是否安全
"""
import io, sys, os, json, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader")
import lceda_reader as lr

FILES = {
    "eprj2": (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch"
              r"\涡流传感器-V1.0-2026.04.01.eprj2", False),
    "epro": (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples"
             r"\ProPrj_TPS56C230_Buck_12Vto5V_6A_2026-08-13.epro", False),
    "epro2": (r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch"
              r"\涡流传感器_backup\涡流传感器_2026-08-10-14-47.epro2",
              False),
    "neweprj2": (r"C:\Users\dell\Documents\LCEDA-Pro\projects"
                 r"\Piezo_Driver.eprj2", True),
}


def open_db(tag):
    path, decrypt = FILES[tag]
    r = lr.detect_backend(path)
    if r == "DECRYPT_NEW" or decrypt:
        tmp = lr._decrypt_new_eprj2(path)
        return lr.Epro2DB(tmp)
    return r(path)


nfail = 0


def check(name, cond, detail=""):
    global nfail
    print(f"{'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        nfail += 1


for tag in FILES:
    print(f"\n===== {tag} =====")
    try:
        db = open_db(tag)
    except Exception as e:
        print(f"FAIL 打开 {tag}: {e}")
        nfail += 1
        continue

    # 1. 基本清单
    sheets = db.sheets()
    sch_pages = [s for s in sheets if s[3] == 1]
    check(f"{tag} sheets() 有页", len(sch_pages) > 0,
          f"pages={len(sch_pages)}")

    # 2. sheet_records doc_type=2（未定义类型）不应崩溃
    try:
        r = db.sheet_records(sch_pages[0][0], doc_type=99)
        check(f"{tag} sheet_records doc_type=99 不崩溃", True,
              f"返回{'非None' if r is not None else 'None'}")
    except Exception as e:
        check(f"{tag} sheet_records doc_type=99 不崩溃", False,
              f"{type(e).__name__}: {e}")

    # 3. symbol_records 可用性
    sh = lr.parse_sheet(db, sch_pages[0][0])
    syms = set()
    for c in (sh or {}).get("components", [])[:30]:
        s = lr.symbol_of(db, c)
        if s:
            syms.add(s)
    has_rec = any(db.symbol_records(s) for s in list(syms)[:5])
    if has_rec:
        check(f"{tag} symbol_records 可用", True)
    else:
        print(f"INFO {tag} symbol_records 不可用"
              f"（V3 图形未转换，已知待办非契约违规）")

    # 4. device_attrs 空值行为
    try:
        r = db.device_attrs("nonexistent_uuid")
        check(f"{tag} device_attrs 不存在 uuid", r is None or r == {} or
              isinstance(r, dict), f"返回 {type(r).__name__}")
    except Exception as e:
        check(f"{tag} device_attrs 不存在 uuid", False,
              f"{type(e).__name__}: {e}")

    # 5. hierarchy 板关联
    try:
        h = db.hierarchy()
        nb = len(h.get("boards", []))
        check(f"{tag} hierarchy() 板数", True, f"boards={nb}")
    except Exception as e:
        check(f"{tag} hierarchy()", False, f"{type(e).__name__}: {e}")

    # 6. pcb_docs / 空 PCB
    try:
        pcbs = db.pcb_docs()
        inv = db.pcb_inventory()
        empty = [i for i in inv if not i["comps"]]
        check(f"{tag} pcb_inventory", True,
              f"pcbs={len(pcbs)} 空PCB={len(empty)}")
    except lr.UnsupportedFormatError as e:
        check(f"{tag} pcb_inventory", True, f"明确不支持: {str(e)[:40]}")
    except Exception as e:
        check(f"{tag} pcb_inventory", False, f"{type(e).__name__}: {e}")

    # 7. parse_sheet 对 PCB 文档（docType=3）——契约：一律不可当 SCH 解析
    try:
        pcbs = db.pcb_docs()
        if pcbs:
            sh_pcb = lr.parse_sheet(db, pcbs[0][0])
            n = len((sh_pcb or {}).get("components", []))
            check(f"{tag} parse_sheet(PCB文档) 返回空(契约)", n == 0,
                  f"comps={n}" + ("" if n == 0 else " ← 应为 0"))
        else:
            check(f"{tag} parse_sheet(PCB文档)", True, "无 PCB 跳过")
    except Exception as e:
        check(f"{tag} parse_sheet(PCB文档) 不崩溃", False,
              f"{type(e).__name__}: {str(e)[:60]}")

    # 8. resolve_page 同名页
    try:
        titles = {}
        for u, t, s, dt in sch_pages:
            titles.setdefault(t, []).append(u)
        dup = [t for t, us in titles.items() if len(us) > 1]
        if dup:
            p1 = lr.resolve_page(db, dup[0])
            p2 = lr.resolve_page(db, dup[0], schematic="不存在的板XYZ")
            check(f"{tag} resolve_page 同名页+坏板名", True,
                  f"dup={dup[0][:20]} p1={str(p1)[:8]} p2={p2}")
        else:
            check(f"{tag} resolve_page 同名页", True, "无同名页")
    except Exception as e:
        check(f"{tag} resolve_page", False, f"{type(e).__name__}: {e}")


# ===== 跨后端一致性：同设计多格式（examples 自带，最稳护栏）=====
# 契约：同一设计在 EproDB(.epro) 与 Epro2DB(.epro2) 下，页集合的元件位号
# 必须一致、元件总数必须一致（B 项 P3 护栏；格式差异只在后端归一化）。
EX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "..", "examples")


def _load(p):
    r = lr.detect_backend(p)
    return lr.Epro2DB(lr._decrypt_new_eprj2(p)) if r == "DECRYPT_NEW" else r(p)


def _page_des(d):
    m, comps, pages = {}, 0, 0
    for u, t, s, dt in d.sheets():
        if dt != 1:
            continue
        pages += 1
        sh = lr.parse_sheet(d, u)
        if not sh:
            continue
        comps += len(sh["components"])
        m[str(t)] = frozenset(c.get("designator") for c in sh["components"]
                              if c.get("designator"))
    return m, comps, pages


def test_cross_format(tag, na, nb):
    pa, pb = os.path.join(EX_DIR, na), os.path.join(EX_DIR, nb)
    if not (os.path.exists(pa) and os.path.exists(pb)):
        print(f"\n[跨后端 {tag}] 样本缺失，跳过（{na} / {nb}）")
        return
    print(f"\n[跨后端 {tag}]")
    ma, ca, pga = _page_des(_load(pa))
    mb, cb, pgb = _page_des(_load(pb))
    check(f"{tag} 元件总数一致", ca == cb, f"{ca} vs {cb}")
    common = set(ma) & set(mb)
    diff = sorted(t for t in common if ma[t] != mb[t])
    check(f"{tag} 共同页位号集一致（{len(common)}/{pga},{pgb} 页）",
          not diff, f"差异页={diff[:5]}")


test_cross_format("Piezo epro↔epro2",
                  "ProPrj_Piezo_Driver_2026-08-21.epro",
                  "ProPrj_Piezo_Driver_2026-08-22.epro2")

print("\n===== 汇总 =====")
print("ALL:", "PASS" if nfail == 0 else f"{nfail} FAIL")