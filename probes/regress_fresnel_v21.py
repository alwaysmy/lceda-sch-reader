"""回归：Fresnel_V2.1_LaserDriver_EVM.epro2（本机实测工程，覆盖三个已修 bug）。

用法：
    set PYTHONIOENCODING=utf-8
    python probes\\regress_fresnel_v21.py [工程路径]
工程路径也可用环境变量 LCEDA_FRESNEL 指定；默认取工作区路径。

覆盖点（对应 2026-09-30 的三处解析层修复）：

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

3. **已删除导线的孤儿 LINE 被复活成"幽灵导线"**
   LCEDA 删除导线时，导出包里该导线的 WIRE 记录**整体消失**，但 append-only
   的 .epru 仍保留其 LINE 记录（lineGroup=已删导线 id）。Epro2DB 按 lineGroup
   无条件聚合，于是幽灵线进入连通域并**凭空造出短路**——本工程 MCU 页
   PA8<->PA9（I2C2_SDA 与 I2C2_SCL）、PA6<->PA7（SPI1_MISO 与 SPI1_MOSI）
   就是这样被误判为短接，而官方导出 PDF 里并无这两段线。
   断言：两对引脚各自独立成域；同时**有意的**网络短接 PB4<->SPI3_MISO
   （SHORT 短接符，PDF 中同样画出）必须仍然合并——防止修过头。
   几何级验收：修复后 MCU 页导线段与官方 PDF 逐段一致
   （343 段 vs 343 段，零差异，见 docs/变更记录-2026-09-30.md）。
"""
import io
import json
import os
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

MCU_UUID = "8cfa75fcb651bfd9"       # LaserDriver EVM::MCU

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

# --- 1) CBB 残留映射不再崩溃 + 2) Name 型 NetPort 端口名 ------------------
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
                    agg.setdefault(tok, set()).add(title)
    crashed = None
except Exception as exc:            # noqa: BLE001 - 回归要看清崩溃类型
    crashed = "%s: %s" % (type(exc).__name__, exc)
    agg = {}

err = buf.getvalue()
check("netlist 全页解析不崩溃", crashed is None, crashed or "")
check("残留 CBB 模板页给出一次性告警", "CBB 模板页" in err, err.strip()[:200])

for net in ("I2C2_SDA", "I2C2_SCL", "EEPROM_WP", "ADC_CS", "ADC_SYNC"):
    check("网络名存在: %s" % net, net in agg,
          "实际网络名: %s" % ",".join(sorted(agg)[:40]))

for net in ("SPI3_SCLK", "SPI3_MISO", "SPI3_MOSI", "ADC_CS", "ADC_SYNC"):
    pages = agg.get(net, set())
    check("%s 跨页归并 MCU<->TEC Controller" % net,
          any("MCU" in p for p in pages) and any("TEC" in p for p in pages),
          "归属页: %s" % ",".join(sorted(pages)))

for auto in ("PA8", "PA9", "PA10", "PD2", "PB3"):
    check("自动名网络仍保留: %s" % auto, auto in agg)

# --- 3) 幽灵导线不再复活 --------------------------------------------------
mcu = L.parse_sheet(db, MCU_UUID)
cp, ws, pw, ep = L._collect_pinmap_data(db, mcu, MCU_UUID)
dom_out = {}
L.resolve_nets_by_domain(db, mcu, cp, ws, pw, ep, domain_out=dom_out)


def dom_of(des, pin):
    for (d, p), v in dom_out.items():
        if d == des and p == pin:
            return v
    return None


for d1, p1, d2, p2, desc in [
    ("U701", "PA8", "U701", "PA9",
     "PA8/PA9（I2C2_SDA/SCL）不得被幽灵线短接"),
    ("U701", "PA6", "U701", "PA7",
     "PA6/PA7（SPI1_MISO/MOSI）不得被幽灵线短接"),
]:
    a, b = dom_of(d1, p1), dom_of(d2, p2)
    check(desc, a is not None and b is not None and a != b,
          "%s.%s=%s  %s.%s=%s" % (d1, p1, a, d2, p2, b))

# 反向断言：有意短接符（PB4<->SPI3_MISO，官方 PDF 同样画出）必须仍然合并
a, b = dom_of("U701", "PB4"), dom_of("U701", "PC11")
check("有意短接 PB4<->SPI3_MISO 仍合并", a is not None and a == b,
      "PB4=%s PC11=%s" % (a, b))

# MCU 页不应残留"无 WIRE/BUS 记录"的孤儿几何组
declared, groups = set(), set()
for ln in db._iter_doc_lines(MCU_UUID):
    head, _, body = ln.partition("||")
    try:
        h = json.loads(head)
    except ValueError:
        continue
    if not h:
        continue
    if h.get("type") in ("WIRE", "BUS"):
        declared.add(str(h.get("id")))
    elif h.get("type") == "LINE":
        try:
            b = json.loads(body.rstrip("|") or "{}")
        except ValueError:
            continue
        if b.get("lineGroup"):
            groups.add(b["lineGroup"])
check("MCU 页无孤儿几何组（幽灵导线=0）", not (groups - declared),
      "孤儿组: %s" % sorted(groups - declared)[:5])

print()
print("ALL: %s" % ("PASS" if not FAILS else "FAIL(%d)" % len(FAILS)))
sys.exit(0 if not FAILS else 1)
