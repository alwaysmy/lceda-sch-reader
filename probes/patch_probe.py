import io, sys, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
p = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
     r"\lceda_reader.py")
src = open(p, encoding="utf-8").read()
marker = '        return (f\'<text x="{x:.1f}" y="{-y:.1f}" \''
probe = ('        if "双路DAC" in str(s):\n'
         '            print("[probe]", s, (x, y), fill or f["color"],\n'
         '                  file=sys.stderr)\n'
         '            traceback.print_stack(file=sys.stderr)\n')
assert marker in src
src = src.replace(marker, probe + marker, 1)
open(p, "w", encoding="utf-8", newline="\n").write(src)
print("patched")
