"""扫描 .epro2：统计"孤儿 lineGroup"（无 WIRE/BUS 记录的几何组）。

用途
----
为 `_iter_doc_lines` 的孤儿几何过滤提供事实依据，并可在改动解析层后复核。
LCEDA 删除导线/总线有两种落盘编码：

1. **墓碑**：最新记录 body 为空（`|||`）——`_iter_doc_lines` 早已处理。
2. **记录整体消失**：导出包里 WIRE/BUS 记录直接不见，但 append-only 的
   `.epru` 仍保留它的 `LINE` 记录（`lineGroup` = 已删对象 id）。
   Epro2DB 按 lineGroup 聚合，孤儿几何会复活成"幽灵导线"并凭空造出短路。

本探针统计第 2 种编码的规模。**只读**，不修改任何文件。

用法
----
    set PYTHONIOENCODING=utf-8
    python probes\\scan_epro2_orphans.py <文件或目录> [...]

本机实测（2026-09-30，74 个 .epro2）：
    30792 个 WIRE id / 36971 个 lineGroup / **6179 个孤儿组（16.7%）** /
    11999 段孤儿几何。分布极不均匀——V4.0/V4.1 单通道扫描台、电容前置
    放大器等早期导出为 0，而反复删改的 MMC-110 高达 323 个。
"""
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict

REC = re.compile(r'\{"type":"([A-Z_]+)","ticket":(\d+),"id":"([^"]*)"')
LINE = re.compile(
    r'\{"type":"LINE","ticket":(\d+),"id":"([^"]+)"[^|]*\}\|\|'
    r'\{[^}]*"lineGroup":"([^"]+)"')


def scan(path):
    """返回单个 .epro2 的统计；非 .epro2 / 无 .epru 返回 None。"""
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.endswith(".epru")]
        if not names:
            return None
        data = z.read(names[0]).decode("utf-8", "replace")

    types = Counter()
    ids = defaultdict(set)
    for m in REC.finditer(data):
        types[m.group(1)] += 1
        ids[m.group(1)].add(m.group(3))

    groups = defaultdict(int)
    for m in LINE.finditer(data):
        groups[m.group(3)] += 1

    declared = ids["WIRE"] | ids["BUS"]
    orphan = [g for g in groups if g not in declared]
    return {
        "file": os.path.basename(path),
        "wire_ids": len(ids["WIRE"]),
        "bus_ids": len(ids["BUS"]),
        "groups": len(groups),
        "orphan": len(orphan),
        "orphan_segs": sum(groups[g] for g in orphan),
    }


def walk(target):
    if os.path.isfile(target):
        yield target
        return
    for root, _dirs, files in os.walk(target):
        for f in files:
            if f.lower().endswith(".epro2"):
                yield os.path.join(root, f)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    tot = Counter()
    n = 0
    for target in argv:
        for p in walk(target):
            try:
                r = scan(p)
            except Exception as exc:                  # noqa: BLE001
                print("SKIP %s (%s)" % (os.path.basename(p), exc))
                continue
            if not r:
                continue
            n += 1
            for k in ("wire_ids", "groups", "orphan", "orphan_segs"):
                tot[k] += r[k]
            print("%-58s WIRE=%-5d BUS=%-4d groups=%-5d orphan=%-5d orphanSegs=%d"
                  % (r["file"][:58], r["wire_ids"], r["bus_ids"], r["groups"],
                     r["orphan"], r["orphan_segs"]))
    print()
    print("files=%d  WIRE ids=%d  lineGroups=%d  orphanGroups=%d  orphanSegs=%d"
          % (n, tot["wire_ids"], tot["groups"], tot["orphan"], tot["orphan_segs"]))
    if tot["groups"]:
        print("孤儿组占 %.1f%%（这些几何在 EDA 里已不存在，必须忽略）"
              % (100.0 * tot["orphan"] / tot["groups"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
