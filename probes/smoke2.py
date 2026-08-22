import subprocess, sys, io, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
os.chdir(r'D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader')
env = dict(os.environ, PYTHONIOENCODING='utf-8')
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
ok = True
for t in tests:
    p = subprocess.run(['python', 'lceda_reader.py', '--eprj', r'D:\WorkDesigns\2_WorkProjects\E_distance\1_sch\涡流传感器.eprj2'] + t,
                       capture_output=True, text=True, encoding='utf-8', env=env)
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
