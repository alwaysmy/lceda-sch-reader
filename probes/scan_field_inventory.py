"""全量字段清单扫描器（AGENTS 纪律：参数必须有据）。

对四类容器逐文档逐行解析，聚合每种 (来源, docType, 记录类型) 的：
- 出现次数、长度分布
- 每个下标的取值类型分布 + 样例值（dict 展开键级统计）

输出 JSON 到 probes/data/field_inventory_<tag>.json，供
docs/工程文件字段字典.md 引用。只读，不改任何文件。
"""
import io, sys, os, json, sqlite3, base64, gzip, zipfile, collections

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data")
os.makedirs(OUT, exist_ok=True)


def vtype(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, dict):
        return "dict"
    if isinstance(v, list):
        return "list"
    return "other"


def sample(v, limit=60):
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + "…"


class Rec:
    __slots__ = ("count", "lengths", "fields")

    def __init__(self):
        self.count = 0
        self.lengths = collections.Counter()
        self.fields = {}

    def add(self, a):
        self.count += 1
        self.lengths[len(a)] += 1
        for i, v in enumerate(a):
            f = self.fields.setdefault(i, {
                "types": collections.Counter(), "ex": collections.Counter(),
                "keys": {}})
            t = vtype(v)
            f["types"][t] += 1
            if len(f["ex"]) < 6 and v is not None:
                if t == "list" and v and isinstance(v[0], list):
                    f["ex"][sample(v[:2]) + f"(len={len(v)})"] += 1
                else:
                    f["ex"][sample(v)] += 1
            if t == "dict":
                kd = f["keys"]
                for k, vv in v.items():
                    kf = kd.setdefault(str(k), {
                        "types": collections.Counter(),
                        "ex": collections.Counter()})
                    kf["types"][vtype(vv)] += 1
                    if len(kf["ex"]) < 5 and vv is not None:
                        kf["ex"][sample(vv)] += 1

    def dump(self):
        return {
            "count": self.count,
            "lengths": dict(self.lengths),
            "fields": {
                i: {"types": dict(f["types"]),
                    "examples": [e for e, _ in f["ex"].most_common(6)],
                    "dict_keys": {k: {"types": dict(v["types"]),
                                      "examples": [e for e, _ in
                                                   v["ex"].most_common(5)]}
                                  for k, v in f["keys"].items()}}
                for i, f in sorted(self.fields.items())},
        }


def scan_v2_arrays(inv, tag, text, doctag):
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            a = json.loads(ln)
        except Exception:
            inv[f"{tag}:{doctag}:<unparsable>"]["n"] += 1
            continue
        if not (isinstance(a, list) and a and isinstance(a[0], str)):
            continue
        slot = inv.setdefault(f"{tag}:{doctag}:{a[0]}", {"rec": None})
        r = slot["rec"]
        if not isinstance(r, Rec):
            r = slot["rec"] = Rec()
        r.add(a)


def scan_eprj2(path, out):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    inv = {}
    # 元数据表结构
    tables = {}
    for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"):
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({name})")]
        n = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        tables[name] = {"columns": cols, "rows": n}
    inv["sqlite:tables"] = {"meta": tables}

    def dec(ds):
        if not ds:
            return ""
        if isinstance(ds, str) and ds.startswith("base64"):
            raw = base64.b64decode(ds[6:])
            try:
                return gzip.decompress(raw).decode("utf-8")
            except Exception:
                return raw.decode("utf-8", errors="replace")
        return ds

    for u, dt, title in conn.execute(
            "SELECT uuid, docType, display_title FROM documents"):
        text = dec(conn.execute(
            "SELECT dataStr FROM documents WHERE uuid=?", (u,)).fetchone()[0])
        if not text:
            inv.setdefault(f"documents:docType={dt}:<empty>", {"n": 0})["n"] += 1
            continue
        scan_v2_arrays(inv, "documents", text, f"docType={dt}")
    # 符号定义（components 表 = SYMBOL 文档）
    n_sym = 0
    for (ds,) in conn.execute("SELECT dataStr FROM components"):
        text = dec(ds)
        if not text:
            continue
        scan_v2_arrays(inv, "components(SYMBOL)", text, "symbol")
        n_sym += 1
    inv["components(SYMBOL):count"] = {"n": n_sym}
    # devices / attributes 结构样例
    dev_cols = [c[1] for c in conn.execute("PRAGMA table_info(devices)")]
    devs = []
    for row in conn.execute(
            "SELECT * FROM devices LIMIT 3"):
        devs.append(sample(dict(zip(dev_cols, row)), 200))
    inv["sqlite:devices_sample"] = {"rows": devs}
    att_cols = [c[1] for c in conn.execute("PRAGMA table_info(attributes)")]
    atts = []
    for row in conn.execute("SELECT * FROM attributes LIMIT 8"):
        atts.append(sample(dict(zip(att_cols, row)), 150))
    inv["sqlite:attributes_sample"] = {"rows": atts}
    conn.close()
    json.dump({k: (v["rec"].dump() if "rec" in v else v)
               for k, v in inv.items()},
              open(os.path.join(out, "field_inventory_eprj2.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=1)


def scan_epro_zip(path, out):
    z = zipfile.ZipFile(path)
    obj = json.loads(z.read("project.json"))
    inv = {}
    # project.json 形状：顶层键与各节首元素样例
    pj = {}
    for k, v in obj.items():
        if isinstance(v, dict):
            first = next(iter(v.items()), None)
            pj[k] = {"kind": "dict", "size": len(v),
                     "first_key": first[0] if first else None,
                     "first_val": sample(first[1], 300) if first else None}
        elif isinstance(v, list):
            pj[k] = {"kind": "list", "size": len(v),
                     "first_val": sample(v[0], 300) if v else None}
        else:
            pj[k] = {"kind": type(v).__name__, "val": sample(v, 100)}
    inv["project.json"] = pj
    groups = {}
    for n in z.namelist():
        top, _, rest = n.partition("/")
        if not rest:
            continue
        groups.setdefault(top, []).append(n)
    inv["zip_groups"] = {k: len(v) for k, v in groups.items()}
    limits = {"SHEET": 8, "SYMBOL": 6, "FOOTPRINT": 3, "INSTANCE": 4,
              "PCB": 3}
    for top, names in groups.items():
        lim = limits.get(top, 2)
        for n in names[:lim]:
            try:
                text = z.read(n).decode("utf-8", errors="replace")
            except Exception:
                continue
            scan_v2_arrays(inv, f"{top}/*", text, "doc")
    json.dump({k: (v["rec"].dump() if "rec" in v else v)
               for k, v in inv.items()},
              open(os.path.join(out, "field_inventory_epro.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=1)


def scan_v3(path, out, decrypt=False):
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    import lceda_reader as lr
    if decrypt:
        tmp = lr._decrypt_new_eprj2(path)
        db = lr.Epro2DB(tmp)
    else:
        db = lr.Epro2DB(path)
    inv = {}
    for u, d in db._docs.items():
        dt = d.get("docType")
        m = db._meta.get(u) or {}
        for ln in db._iter_doc_lines(u):
            head, _, body = ln.partition("||")
            h = lr.Epro2DB._jl(head)
            b = lr.Epro2DB._jl(body.rstrip("|"))
            t = (h or {}).get("type") or "<badhead>"
            key = f"v3:{dt}:{t}"
            e = inv.setdefault(key, {"rec": Rec(), "bodykeys": {}})
            if not isinstance(e["rec"], Rec):
                e["rec"] = Rec()
            e["rec"].add([h.get("type"), h.get("id"), h.get("ticket"),
                          b])
            bk = e["bodykeys"]
            if isinstance(b, dict):
                for k, vv in b.items():
                    kf = bk.setdefault(str(k), {
                        "types": collections.Counter(),
                        "ex": collections.Counter()})
                    kf["types"][vtype(vv)] += 1
                    if len(kf["ex"]) < 5 and vv is not None:
                        kf["ex"][sample(vv)] += 1
    dump = {}
    for k, e in inv.items():
        dd = e["rec"].dump() if isinstance(e["rec"], Rec) else e
        if "fields" in dd and 3 in dd["fields"]:
            dd["fields"][3]["dict_keys"] = {
                k2: {"types": dict(v2["types"]),
                     "examples": [x for x, _ in v2["ex"].most_common(5)]}
                for k2, v2 in e.get("bodykeys", {}).items()}
        dump[k] = dd
    dump["v3:META_titles"] = {
        dt: [{"title": (db._meta.get(u) or {}).get("title")}
             for u, d in list(db._docs.items()) if d.get("docType") == dt][:5]
        for dt in ("BOARD", "SCH", "SCH_PAGE", "PCB", "SYMBOL", "DEVICE",
                   "FOOTPRINT", "INSTANCE")}
    tag = "epro2"
    json.dump(dump, open(os.path.join(out, f"field_inventory_{tag}.json"),
                         "w", encoding="utf-8"), ensure_ascii=False, indent=1)


out = OUT
scan_eprj2(r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch"
           r"\涡流传感器-V1.0-2026.04.01.eprj2", out)
print("eprj2 done")
scan_epro_zip(r"D:\WorkDesigns\3_WorkTools\sch_review_tool\examples"
              r"\ProPrj_Piezo_Driver_2026-08-21.epro", out)
print("epro done")
scan_v3(r"D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器_backup"
        r"\涡流传感器_2026-08-10-14-47.epro2", out)
print("epro2 done")
