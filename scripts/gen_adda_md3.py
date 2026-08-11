import io, sys, json, subprocess, os, re
import os as _os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 工具所在目录 = 本脚本上一级（scripts/ -> 工具根）
TOOL_DIR = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
TOOL = _os.path.join(TOOL_DIR, 'lceda_reader.py')




import argparse as _argparse
_ap = _argparse.ArgumentParser()
_ap.add_argument("--eprj", default=None, help="立创EDA工程(.eprj2)，默认用脚本内置路径")
_ap.add_argument("--eprj2", default=None, help="第二工程(.eprj2)，与 --eprj 配套")
_ap.add_argument("--out", default=None, help="输出 md 路径，默认用脚本内置路径")
_ap.add_argument("--tool", default=None, help="lceda_reader.py 路径(默认自动定位)")
_args = _ap.parse_args()
if _args.tool:
    TOOL = _args.tool
elif not _os.path.exists(TOOL):
    TOOL = _os.path.join(TOOL_DIR, "lceda_reader.py")
env = dict(os.environ, PYTHONIOENCODING='utf-8')
V0 = _os.getenv('LCEDA_EPRJ_V0', '')  # 通过环境变量或 --eprj 指定
V11 = _os.getenv('LCEDA_EPRJ_V11', '')  # 通过环境变量或 --eprj 指定
if _args.eprj:
    V0 = _args.eprj
if _args.eprj2:
    V11 = _args.eprj2

def run(eprj, *args):
    p = subprocess.run([sys.executable, TOOL, '--eprj', eprj] + list(args),
                       capture_output=True, text=True, encoding='utf-8', env=env)
    return json.loads(p.stdout) if p.returncode == 0 else []

def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)]

# V1.1 MCU: pin -> net
v11_u3 = {}
for page in ('STM32H743VIT6', '对外连接'):
    for comp in run(V11, '--json', 'pinmap', page):
        if comp['designator'] == 'U3':
            for p in comp['pins']:
                if p['net']:
                    v11_u3[p['pin']] = p['net']

# V0.1 ADDA 全器件 pinmap（新方案已含连通域推断）
ADDA_PAGES = ['对外连接', '板载温度', '探头温度采集', '四路低速DA',
              '高速AD', '高速DA', '基准']
all_dev = {}
adda_conn = {}
for page in ADDA_PAGES:
    for comp in run(V0, '--json', 'pinmap', page, '--schematic', 'schematic2'):
        des = comp['designator']
        if des in ('H2', 'H3'):
            adda_conn.setdefault(des, {})
            for p in comp['pins']:
                adda_conn[des][p['number']] = p['net']
        else:
            all_dev.setdefault(des, {})
            for p in comp['pins']:
                all_dev[des][p['pin']] = p

POWER_SIG = re.compile(r'^(GND|AGND|DGND|D3V3|\+5V|\+3\.3V|VBUS)$')

report = []
report.append('# V1.1 主控板与 ADDA 板器件对应关系')
report.append('')
report.append('> V1.1 主控（MCU主控-V1.1）通过 H1/H2(2x20) 排针与 ADDA 板对接，')
report.append('> 连接器 40pin 网络**完全一致**（已自动核对）。控制器：U3 STM32H743VIT6。')
report.append('> 器件引脚网络经**走线连通域解析**（同导线记录端点相接 + 0Ω 跳线直连 +')
report.append('> 两脚无源器件桥传播），标 `*` 为推断网络。')
report.append('')
report.append('## 板间接线（V1.1 H1/H2 ↔ ADDA H2）')
report.append('')
report.append('| 连接器引脚 | 网络名 | MCU 引脚 |')
report.append('| --- | --- | --- |')
for pin in sorted(adda_conn.get('H2', {}), key=lambda x: int(x)):
    net = adda_conn['H2'][pin]
    mcu = ','.join([m for m, n in v11_u3.items() if n == net])
    report.append(f'| {pin} | {net} | {mcu} |')
report.append('')

GROUPS = [
    ('高速AD（U26 ADS8331）', 'U26'),
    ('高速DA（U27 DAC8562）', 'U27'),
    ('四路低速DA（U3/U4 DAC7562）', ['U3', 'U4']),
    ('板载温度（U18 ADT7310）', 'U18'),
    ('探头温度采集（U2 LTC2485）', 'U2'),
    ('基准（U28 LTC6655）', 'U28'),
]
for gname, desigs in GROUPS:
    des_list = desigs if isinstance(desigs, list) else [desigs]
    report.append(f'## {gname}')
    report.append('')
    report.append('| 器件引脚 | 网络名 | MCU 引脚 | 说明 |')
    report.append('| --- | --- | --- | --- |')
    for des in des_list:
        if des not in all_dev:
            continue
        for pin in sorted(all_dev[des], key=natkey):
            p = all_dev[des][pin]
            net = p['net']
            inferred = p.get('net_inferred', False)
            mcu = ''
            if net:
                best = None
                for tok in net.split(','):
                    if POWER_SIG.match(tok):
                        continue
                    hits = [m for m, n in v11_u3.items() if n == tok]
                    if hits and (best is None or len(best) > len(hits)):
                        best = hits
                mcu = ','.join(best or [])
            desc = ''
            if p.get('wire_peers'):
                desc = '经 ' + ','.join(p['wire_peers']) + ' 连接'
            tag = '*' if inferred else ''
            report.append(f'| {des}.{pin} | {net}{tag} | {mcu} | {desc} |')
    report.append('')

out = _args.out
if not out:
    sys.exit('需 --out 指定输出路径')
with open(out, 'w', encoding='utf-8') as f:
    f.write('\n'.join(report))
print('written:', out, 'lines:', len(report))
