import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
p = (r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
     r"\lceda_reader.py")
src = open(p, encoding="utf-8").read()
old = ("        if \"双路DAC\" in str(s):\n"
       "            print(\"[probe]\", s, (x, y), fill or f[\"color\"],\n"
       "                  file=sys.stderr)\n"
       "            traceback.print_stack(file=sys.stderr)\n")
new = ("        if \"双路DAC\" in str(s):\n"
       "            print(\"[probe]\" + \"|\".join(\n"
       "                x.strip() for x in traceback.format_stack()[-6:-1]))\n")
assert old in src
src = src.replace(old, new, 1)
open(p, "w", encoding="utf-8", newline="\n").write(src)
print("re-patched")
