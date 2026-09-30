"""回归：Fresnel_V2.1_LaserDriver_EVM.epro2（本机实测工程，覆盖两个已修 bug）。

用法：
    set PYTHONIOENCODING=utf-8
    python probes\\regress_fresnel_v21.py [工程路径]
工程路径也可用环境变量 LCEDA_FRESNEL 指定；默认取工作区路径。

覆盖点（对应 2026-09-30 的两处解析层修复）：

1. **INSTANCE 文档残留映射导致 netlist 崩溃**
   TEC Controller 页残留 CBB 实例（cid=3851a5f68fce21f1）的 src 指向
   `b1958471d75069f5` —— 该 uuid 在本工程里只剩 IMAGE 缩略图，没有对应原理图页。
   修复前 `_cbb_dom` 把 parse_sheet 的 None 直接喂给 `_collect_pinmap_data`，
   `sheet["nets"]` 对 None 取下标 -> TypeError，整条 netlist/trace 挂掉。
   断言：netlist 正常返回，且 stderr 给出一次性告警。

2. **NetPort 端口名存放在 `Name` 而非 `Global Net Name` 时被丢弃**
   本工程 MCU 页 I2C2_SDA/I2C2_SCL/EEPROM_WP/ADC_CS/ADC_SYNC 五个端口的
   Symbol 为 a029f22680921aa0 / ed17ac3692b0f0b6，端口名写在 `Name` 属性；
   其 stub 线没有 NET 属性。修复前这五个网络名整体丢失，退回立创自动名
   （PA8/PA9/PA10/PD2/PB3），跨页同名归并随之失效。
   断言：五个网络名都出现在 netlist 中，且 ADC_CS/ADC_SYNC/SPI3_* 同时归属
   MCU 与 TEC Controller 两页（AD7175-2 ADC 总线）。
"""
import io
import os
import subprocess
import sys
from contextlib import redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import lceda_reader as L  # noqa: E402

DEFAULT = (r"D:\Projects\01-激光干涉仪\06-激光干涉仪V2.1\02-硬件工程"
           r"\Fresnel_V2.1_LaserDriver_EVM.epro2")
PATH = (sys.argv[1] if len(sys.argv) > 1
        else os.environ.get("LCEDA_FRESNEL", DEFAULT))

FAILS = []


def check(name, cond, detail=""):
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           ("  -- " + detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


if not os.path.isfile(PATH):
    print("回归工程不存在: %s（可用 LCEDA_FRESNEL 环境变量覆盖）" % PATH)
    sys.exit(2)

print("工程: %s" % PATH)
cls = L.detect_backend(PATH)
db = cls(PATH)

# --- 1) CBB 残留映射不再崩溃 ---------------------------------------------
buf = io.StringIO()
try:
    with redirect_stderr(buf):
        agg = {}
        for uuid, title, sch, dt in db.sheets():
            if dt != 1:
                continue
            sheet = L.parse_sheet(db, uuid)
            if sheet is None:
                continue
            cp, ws, pw, ep = L._collect_pinmap_data(db, sheet, uuid)
            dom = L.resolve_nets_by_domain(db, sheet, cp, ws, pw, ep)
            for (des, pin), net in dom.items():
                for tok in L.net_tokens(net or ""):
                    e = agg.setdefault(tok, set())
                    e.add(title)
    crashed = None
except Exception as exc:            # noqa: BLE001 - 回归要看清崩溃类型
    crashed = "%s: %s" % (type(exc).__name__, exc)
    agg = {}

err = buf.getvalue()
check("netlist 全页解析不崩溃", crashed is None, crashed or "")
check("残留 CBB 模板页给出一次性告警", "CBB 模板页" in err, err.strip()[:200])

# --- 2) Name 型 NetPort 端口名不再丢失 ------------------------------------
for net in ("I2C2_SDA", "I2C2_SCL", "EEPROM_WP", "ADC_CS", "ADC_SYNC"):
    check("网络名存在: %s" % net, net in agg,
          "实际网络名: %s" % ",".join(sorted(agg)[:40]))

for net in ("SPI3_SCLK", "SPI3_MISO", "SPI3_MOSI", "ADC_CS", "ADC_SYNC"):
    pages = agg.get(net, set())
    check("%s 跨页归并 MCU<->TEC Controller" % net,
          any("MCU" in p for p in pages) and any("TEC" in p for p in pages),
          "归属页: %s" % ",".join(sorted(pages)))

# 立创自动名不应再吞掉功能名：PA8/PA9/PA10/PD2/PB3 仍各自独立存在
for auto in ("PA8", "PA9", "PA10", "PD2", "PB3"):
    check("自动名网络仍保留: %s" % auto, auto in agg)

print()
print("ALL: %s" % ("PASS" if not FAILS else "FAIL(%d)" % len(FAILS)))
sys.exit(0 if not FAILS else 1)
