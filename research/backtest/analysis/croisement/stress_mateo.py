"""Helper for stress_anchor.py: monthly return series of Mateo's strategies on one long window, run through
analysis/mateo/common.py (data_ext with US_MKT_XEN, delayed_glidepath registered) exactly like the Mateo runs.
Separate process because common.py repoints the engine data directory. SIMULATION ONLY."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mateo"))
import common as mc  # noqa: E402  (sets ALPHAFORGE_BT_DATA before the engine data module is used)

sys.path.insert(0, str(HERE))
import importlib.util  # noqa: E402

spec_ = importlib.util.spec_from_file_location("ccommon", HERE / "common.py")
cc = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(cc)


def main():
    out = {}
    for pid in ("mateo_cad_esg", "mateo_usd_long_esg"):
        p = mc.inject_glide_params(mc.load_profile(pid))
        for name in ("risk_parity_iv36", "static_eq60_gold" if pid == "mateo_cad_esg" else "static_eq60"):
            spec = next(s for s in p["strategies"] if s["name"] == name)
            s = cc.simulate_long(p, spec, 37 if spec["type"] == "risk_parity" else 1)
            out[f"{pid}|{name}"] = {"index": [str(d.date()) for d in s.index], "returns": [float(x) for x in s.values],
                                    "fallback_months": s.attrs["fallback_months"]}
            print(pid, name, s.index[0].date(), s.index[-1].date(), s.attrs["fallback_months"])
    print(cc.write("stress_mateo_series", out, [f"profiles/{p}.yaml" for p in ("mateo_cad_esg", "mateo_usd_long_esg")],
                   {"doc": __doc__, "data_dir": str(mc.D.DATA_DIR)}))


if __name__ == "__main__":
    main()
