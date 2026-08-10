import io, sys, json, subprocess, os, re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


import os as _os

def _repo_root():
    """从脚本位置向上找含 1_sch/ 的仓库根。"""
    d = _os.path.dirname(_os.path.abspath(__file__))
    while True:
        if _os.path.isdir(_os.path.join(d, '1_sch')):
            return d
        p = _os.path.dirname(d)
        if p == d:
            return _os.path.dirname(_os.path.abspath(__file__))
        d = p
REPO = _repo_root()

TOOL = _os.path.join(REPO, '6_tools', 'lceda_sch_reader', 'lceda_reader.py')
EPRJ = _os.path.join(REPO, '1_sch', 'V1.1版主控原理图', 'MCU主控-V1.1-2026.05.06.eprj2')

import argparse as _argparse
_ap = _argparse.ArgumentParser()
_ap.add_argument("--eprj", default=None, help="立创EDA工程(.eprj2)，默认用脚本内置路径")
_ap.add_argument("--out", default=None, help="输出 md 路径，默认用脚本内置路径")
_ap.add_argument("--tool", default=None, help="lceda_reader.py 路径(默认自动定位)")
_args = _ap.parse_args()
if _args.eprj:
    EPRJ = _args.eprj
if _args.tool:
    TOOL = _args.tool
elif not _os.path.exists(TOOL):
    TOOL = _os.path.join(REPO, "6_tools", "lceda_sch_reader", "lceda_reader.py")
env = dict(os.environ, PYTHONIOENCODING='utf-8')

POWER_NETS = re.compile(r'^(GND|AGND|DGND|VCC|VDD|VSS|VBUS|3V3|3\.3V|5V|\+3\.3V|\+5V|VBAT|VREF\+|VDDA|VSSA)$', re.I)


def run(*args):
    p = subprocess.run([sys.executable, TOOL, '--eprj', EPRJ] + list(args),
                       capture_output=True, text=True, encoding='utf-8', env=env)
    return p.stdout


def run_json(*args):
    return json.loads(run(*args))


def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)]


MCU = 'U3'
include = ['U1', 'U2', 'U4', 'U5', 'USBC1', 'CN1', 'H1', 'H2', 'H5',
           'LED1', 'LED2', 'LED3', 'LED4', 'LED5', 'BUZZER1']

all_maps = {}
u3_net_pins = {}
for page in ('STM32H743VIT6', '卧贴USB切换串口', '对外连接'):
    for comp in run_json('--json', 'pinmap', page):
        des = comp['designator']
        pinmap = {}
        for p in comp['pins']:
            pinmap[p['pin']] = p
        if des == MCU:
            for pin, v in pinmap.items():
                if v['net']:
                    u3_net_pins.setdefault(v['net'], []).append(pin)
        elif des in include:
            if des not in all_maps:
                all_maps[des] = {}
            all_maps[des].update(pinmap)

lines = []
lines.append('# V1.1 版主控原理图引脚关系（MCU主控-V1.1-2026.05.06）')
lines.append('')
lines.append('> 依据 `1_sch/V1.1版主控原理图/MCU主控-V1.1-2026.05.06.eprj2` 自动提取')
lines.append('> （lceda_reader.py pinmap，实例坐标+PIN坐标精确匹配，非近似）。')
lines.append('> 控制器：**U3 STM32H743VIT6**（LQFP100）。')
lines.append('')
lines.append('表格列：**器件引脚**、**引脚号**、**网络名**、**单片机引脚**、**同网络关联引脚**。')
lines.append('- 网络名为空 = 该引脚网络在原理图中未命名（NC 或经串阻/晶体管间接连接）。')
lines.append('- 关联引脚（wire 列） = 与该引脚同一条导线记录上的其他器件引脚，')
lines.append('  用于识别串阻/耦合电容/晶体管链路（如 LED→R→+5V、Q1 栅极分压）。')
lines.append('- 电源网络(GND/+3.3V 等)的单片机引脚列标注"电源"。')
lines.append('')

lines.append('## U3 STM32H743VIT6（自身引脚网络）')
lines.append('')
lines.append('| 引脚 | # | 网络名 | 引脚 | # | 网络名 |')
lines.append('| --- | --- | --- | --- | --- | --- |')
mcu_pins = []
_seen_nums = set()
for comp in run_json('--json', 'pinmap', 'STM32H743VIT6'):
    if comp['designator'] == 'U3':
        # 多 PART 符号输出多个实例(.1/.2)，按引脚号合并去重
        for p in comp['pins']:
            n = str(p['number'])
            if n not in _seen_nums:
                _seen_nums.add(n)
                mcu_pins.append(p)
mcu_pins.sort(key=lambda x: natkey(x['number'] or ''))
rows2 = []
for i in range(0, len(mcu_pins), 2):
    a = mcu_pins[i]
    b = mcu_pins[i + 1] if i + 1 < len(mcu_pins) else None
    ra = f"{a['pin']} | {a['number']} | {a['net']}"
    rb = f"{b['pin']} | {b['number']} | {b['net']}" if b else '| |'
    rows2.append(f'| {ra} | {rb} |')
lines.append('\n'.join(rows2))
lines.append('')

# 器件型号：从 devmap 取（components/devices display_title）
dev_names = {}
for comp in run_json('--json', 'components'):
    des = comp.get('designator')
    if des in include and comp.get('device'):
        dev_names[des] = comp['device']

for des in include:
    if des not in all_maps:
        continue
    pinmap = all_maps[des]
    title = f"{des} {dev_names.get(des, '')}".strip()
    lines.append(f'## {title}')
    lines.append('')
    lines.append('| 器件引脚 | 引脚号 | 网络名 | 单片机引脚 | 同网络关联引脚 |')
    lines.append('| --- | --- | --- | --- | --- |')
    for pin in sorted(pinmap, key=natkey):
        v = pinmap[pin]
        net = v['net']
        if not net:
            mcu = ''
        elif POWER_NETS.match(net):
            mcu = '电源'
        else:
            mcu = ','.join(sorted(set(u3_net_pins.get(net, []))))
        wp = ','.join(sorted(set(
            list(v.get('peers', [])) + list(v.get('wire_peers', [])))))
        lines.append(f'| {pin} | {v["number"]} | {net} | {mcu} | {wp} |')
    lines.append('')

out_path = _args.out or _os.path.join(REPO, '5_docs', 'V1.1版主控原理图引脚关系.md')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print('written:', out_path, 'lines:', len(lines))
