"""属性键全量普查（lceda_attrs.py 映射表的依据来源）。

对多个真实工程扫描 devices/components 的描述串，统计所有出现过的
"键:值"属性键及其样例值。**不做任何映射假设**——只报告事实，
供 lceda_attrs.py 的规范键表与值解析做依据（仓库"参数依据纪律"）。

用法:
    python probes/attr_survey.py            # 默认扫 examples + 指定工程
    python probes/attr_survey.py <文件>...  # 指定工程文件
"""
import io
import os
import sys
import collections

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import lceda_reader as R

DEFAULT = [
    os.path.join(ROOT, "..", "examples", "涡流传感器.eprj2"),
    os.path.join(ROOT, "..", "examples", "Piezo_Driver.eprj2"),
    os.path.join(ROOT, "..", "examples", "MCU主控-V1.1-2026.05.06.eprj2"),
    os.path.join(ROOT, "..", "examples",
                 "ProPrj_TPS56C230_Buck_12Vto5V_6A_2026-08-13.epro"),
]


def open_db(path):
    db = R.detect_backend(path)
    if db == "DECRYPT_NEW":
        return R.Epro2DB(R._decrypt_new_eprj2(path))
    return db(path) if isinstance(db, type) else db


def survey(paths):
    keys = collections.Counter()
    samples = {}
    for p in paths:
        if not os.path.isfile(p):
            print(f"[skip] 不存在: {p}", file=sys.stderr)
            continue
        try:
            db = open_db(p)
            dmap = db.device_map()
        except Exception as e:
            print(f"[skip] {os.path.basename(p)}: {type(e).__name__} {e}",
                  file=sys.stderr)
            continue
        for _u, (_t, _d, desc) in dmap.items():
            if not desc or ";" not in desc or ":" not in desc:
                continue
            for kv in desc.split(";"):
                kv = kv.strip()
                if ":" not in kv:
                    continue
                k, v = kv.split(":", 1)
                k = k.strip()
                keys[k] += 1
                samples.setdefault(k, v.strip())
    return keys, samples


def main():
    paths = sys.argv[1:] or DEFAULT
    keys, samples = survey(paths)
    print(f"=== 共 {len(keys)} 个属性键 ===")
    for k, n in keys.most_common():
        print(f"{n:6d}  {k}  = {samples[k][:40]}")


if __name__ == "__main__":
    main()
