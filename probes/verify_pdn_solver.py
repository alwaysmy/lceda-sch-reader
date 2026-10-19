"""PDN 求解器校验：解析直导线 + 真实板 smoke test。"""
import math
import os
import sys

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve

ROOT = r"D:\WorkDesigns\3_WorkTools\sch_review_tool\lceda_sch_reader"
sys.path.insert(0, ROOT)

from pcb_workbench import pdn
from pcb_workbench.v4 import load_epcb2


def strip_resistance():
    """单层直导线：R = rho*L/(w*t)，与 FDM 解比较。"""
    H, W = 20, 200
    h_mm = 0.1
    t_um = 35.0
    t_m = t_um * 1e-6
    G = pdn.SIGMA_CU * t_m
    mask = np.ones((H, W), bool)
    ids = np.full(mask.shape, -1, np.int32)
    ids[mask] = np.arange(mask.size)
    edges = pdn._edge_arrays(ids, mask, G)
    ri = np.concatenate([e[0] for e in edges])
    cj = np.concatenate([e[1] for e in edges])
    gd = np.full(len(ri), G)
    A = sparse.coo_matrix(
        (np.concatenate([gd, gd, -gd, -gd]),
         (np.concatenate([ri, cj, ri, cj]),
          np.concatenate([ri, cj, cj, ri]))),
        shape=(mask.size, mask.size)).tocsr()
    fixed = np.zeros(mask.size, bool)
    fixed[ids[:, 0]] = True
    b = np.zeros(mask.size)
    b[ids[:, -1]] = -1.0 / H
    free = ~fixed
    V = np.ones(mask.size)
    V[free] = spsolve(A[free][:, free].tocsc(),
                      b[free] - A[free][:, fixed] @ V[fixed])
    r_solver = (1.0 - float(np.mean(V[ids[:, -1]]))) / 1.0
    r_analytic = pdn.analytic_trace_resistance(
        W * h_mm, H * h_mm, t_um)
    err = abs(r_solver - r_analytic) / r_analytic
    print("strip R solver=%.6f ohm analytic=%.6f ohm err=%.3f%%"
          % (r_solver, r_analytic, err * 100))
    assert err < 0.02


def real_board():
    pcb = (r"C:\Users\dell\Documents\LCEDA-Pro\projects"
           r"\Fresnel_V2.1_LaserDriver_EVM\pcb\PCB1.epcb2")
    if not os.path.exists(pcb):
        print("real board skipped (not found)")
        return
    d = load_epcb2(pcb)
    spec = {
        "net": "TEC_NEG", "voltage": 1.0, "current": 0.5,
        "source": {"designator": "U602", "pad": "2"},
        "sinks": [{"designator": "U900", "pad": "14"}],
        "layers": [1, 2], "grid_mm": 0.1, "board_mm": 1.6,
        "copper_um": {"1": 35, "2": 35},
    }
    res = pdn.solve_pdn(d, spec)
    r = (res["Vsrc"] - res["sink_v"]) / spec["current"]
    print("board TEC_NEG: drop=%.4f mV  R=%.4f ohm  P=%.4f W  Jmax=%.2f A/mm2"
          % ((res["Vsrc"] - res["sink_v"]) * 1000, r, res["power_total"],
             res["max_j"]))
    assert res["Vsrc"] - res["sink_v"] > 1e-4
    assert 0 < res["power_total"] < 10
    assert 0 < res["max_j"] < 1000
    assert res["kept_nodes"] > 0


if __name__ == "__main__":
    strip_resistance()
    real_board()
    print("PDN solver verify OK")
