"""基础回归（AGENTS.md 测试规则：脚本入 probes/）。

默认读取 ../../examples/涡流传感器.eprj2（与仓库同机，无外部绝对路径，
换机可用；已实证与旧外部路径文件字节一致，9 项输出逐字节相同）。
可用环境变量 LCEDA_EPRJ 覆盖工程路径（脚本用）。
"""
import subprocess, sys, io, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # lceda_sch_reader/
READER = os.path.join(ROOT, 'lceda_reader.py')
DEFAULT_EPRJ = os.path.normpath(os.path.join(ROOT, '..', 'examples',
                                             '涡流传感器.eprj2'))
EPRJ = os.environ.get('LCEDA_EPRJ', DEFAULT_EPRJ)
env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
tests = [
    ['--json', 'bom', '--board', 'ADDA'],
    ['--json', 'netlist'],
    ['--json', 'find', 'U28'],
    ['--json', 'pins', '板载温度'],
    ['--json', 'datasheets'],
    ['--json', 'components'],
    ['search', 'LTC6655'],
    ['--json', 'search', 'DAC8562'],
    ['nets', '探头温度采集'],
]
if not os.path.isfile(EPRJ):
    print(f'回归工程不存在: {EPRJ}（可用 LCEDA_EPRJ 环境变量覆盖）')
    print('ALL: FAIL')
    sys.exit(1)
print(f'工程: {EPRJ}')
ok = True
for t in tests:
    p = subprocess.run([sys.executable, READER, '--eprj', EPRJ] + t,
                       capture_output=True, text=True, encoding='utf-8',
                       env=env, cwd=ROOT)
    out = p.stdout
    err = p.stderr[-300:] if p.stderr else ''
    status = 'OK' if p.returncode == 0 else 'FAIL'
    if p.returncode != 0:
        ok = False
    # JSON validity check
    if '--json' in t:
        try:
            json.loads(out)
            status += ' json-valid'
        except Exception as e:
            status += f' JSON-INVALID: {e}'
            ok = False
    print(f'{" ".join(t):45s} rc={p.returncode} {status} lines={len(out.splitlines())}')
    if err:
        print('   stderr:', err)
print('ALL:', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
