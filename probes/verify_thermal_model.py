"""热模型校验：实际叠层 + 严格输入门 + 合成封装网络 + 能量平衡。"""
import json
import os
import sys

ROOT = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
sys.path.insert(0, ROOT)

from pcb_workbench import thermal
from pcb_workbench.v4 import load_epcb2

PCB = (r"C:\Users\dell\Documents\LCEDA-Pro\projects"
       r"\Fresnel_V2.1_LaserDriver_EVM\pcb\PCB1.epcb2")

SYNTH = {
    "grid_mm": 1.0, "ambient_c": 25,
    "convection": {"top_w_m2k": 10, "bottom_w_m2k": 10,
                   "edge_w_m2k": 5},
    "radiation_emissivity": 0.0,
    "components": [{
        "designator": "U601", "power_w": 0.1, "model": "three_node",
        "theta_jb": 10.0, "theta_jc": 2.0, "theta_ca": 30.0,
        "source": "SYNTHETIC TEST ONLY", "data_quality": "test",
    }],
}


def main():
    d = load_epcb2(PCB)
    st = d.stackup()
    assert len(st) == 7, st
    total = sum(x["thickness_mil"] for x in st) * 0.0254
    assert abs(total - 1.586) < 0.02, total
    assert sum(1 for x in st if x["is_copper"]) == 4
    print("stackup: 7 layers, %.3f mm, 4 copper" % total)

    tmpl = json.load(open(os.path.join(
        ROOT, "pcb_workbench", "specs", "thermal_fresnel.template.json"),
        encoding="utf-8"))
    errs = thermal.validate(d, tmpl)
    assert errs, "template must be rejected"
    assert any("power_w" in e for e in errs)
    print("strict gate: %d missing-data errors" % len(errs))

    res = thermal.solve(d, SYNTH)
    qin, qout = res["q_in_w"], res["q_out_w"]
    assert qin > 0
    assert abs(qin - qout) / qin < 1e-5, (qin, qout)
    c = res["components"][0]
    assert c["Tj_c"] > c["Tboard_c"] > 25.0, c
    assert c["Tj_c"] > c["Tc_c"] > 25.0, c
    print("synthetic U601: Tj=%.3f Tc=%.3f Tboard=%.3f q=%.4f/%.4f"
          % (c["Tj_c"], c["Tc_c"], c["Tboard_c"], qin, qout))
    print("thermal model verify OK")


if __name__ == "__main__":
    main()
