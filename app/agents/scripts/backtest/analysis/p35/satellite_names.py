"""Persona 35 - pocket B: size cap of a single 'titre connu' (status satellite for actions CA / actions US).

Base: e40/u50 proxies (CA_EQ .2, US_MKT .2, CA_GOV_10Y .3, UST_5Y .3), CAD, annual rebalancing.
Add x = 0..15 % (step 1) of one name, taken pro-rata. Period: name listing (>= 1995) -> 2026-09, rolling
windows of 10 years step 12 (15y gives too few windows on 1995+).
Rule (proposal, same spirit as Robert's): x_cap = largest x such that, for x and all smaller sizes,
 (a) worst max drawdown over all windows <= L_final (0.15, derive_b.json), and
 (b) stress: base worst maxDD + x * D_H <= L_final, D_H = the name's own worst drawdown (CAD, since listing),
 (c) total loss: base worst maxDD + x <= L_final  (survivorship: failed names are not in the universe).
Citable cap = min(a, b); (c) reported. Outputs results/p35_analysis/satellite_names.json. SIMULATION ONLY.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np

import common as C
from derive_b import sim
from alphaforge.finance.backtest import metrics as M
from alphaforge.finance.backtest.data import load_returns

NAMES = ["RY.TO", "TD.TO", "FTS.TO", "ENB.TO", "JNJ", "PG"]
BASE = {"CA_EQ": .2, "US_MKT": .2, "CA_GOV_10Y": .3, "UST_5Y": .3}

if __name__ == "__main__":
    L = json.loads((C.OUT / "derive_b.json").read_text())["results"]["L_final"]
    out = {"L_final": L, "names": {}}
    for nm in NAMES:
        R = load_returns(list(BASE) + [nm], "1995-01", "2026-09", "CAD")
        D_H = M.max_drawdown(R[nm].values)
        n = 120
        rows = []
        for x in np.round(np.arange(0, 0.1501, 0.01), 2):
            w = {k: v * (1 - x) for k, v in BASE.items()}
            w[nm] = x
            r = sim(R, w)
            dds = [M.max_drawdown(r[i:i + n]) for i in range(0, len(r) - n + 1, 12)]
            rows.append({"x": float(x), "worst_maxdd": float(max(dds)), "n_windows": len(dds)})
        base_dd = rows[0]["worst_maxdd"]
        xa = 0.0
        for r_ in rows[1:]:
            if r_["worst_maxdd"] <= L:
                xa = r_["x"]
            else:
                break
        xb = max(0.0, (L - base_dd) / D_H)
        xc = max(0.0, L - base_dd)
        out["names"][nm] = {"period": [str(R.index.min().date()), str(R.index.max().date())], "D_H": D_H,
                            "base_worst_maxdd": base_dd, "x_a_path": xa, "x_b_stress": float(xb),
                            "x_c_total_loss": float(xc), "citable_cap": float(min(xa, np.floor(xb * 100) / 100)),
                            "rows": rows}
        print(nm, out["names"][nm]["period"], f"D_H={D_H:.3f} base={base_dd:.3f} a={xa} b={xb:.3f} c={xc:.3f} cap={out['names'][nm]['citable_cap']}")
    p = C.write_trace("satellite_names", out, {"base": BASE, "window_months": 120, "step": 12}, "satellite_names.py")
    print(p)
