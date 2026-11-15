"""Coarse ORACLE (hindsight=True, NON investable) in the 'equity share x bond duration' space.

The full-universe oracle picks single sectors (unstable, hard to read). For reverse engineering we
re-run the engine oracle on a reduced universe (broad equity + the Treasury curve) with the SAME
objective and derived risk limits as Robert's profiles. Uses engine.run.run_profile (unmodified).
Run: .venv/bin/python -I analysis/robert/oracle_coarse.py
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BT  # noqa: E402

from engine.profile import load_profile, validate  # noqa: E402
from engine.run import run_profile  # noqa: E402

CASES = {
    "robert_coarse_usd": ("robert_long_usd", ["US_MKT", "UST_TBILL", "UST_2Y", "UST_5Y", "UST_10Y", "UST_20Y"], "UST_TBILL"),
    "robert_coarse_cad": ("robert_cad", ["CA_EQ", "US_MKT", "CA_TBILL", "UST_2Y", "UST_5Y", "CA_GOV_10Y"], "CA_TBILL"),
}


def main():
    for cid, (base, uni, cash) in CASES.items():
        p = copy.deepcopy(load_profile(base))
        p.pop("_path", None)
        p.update(id=cid, universe=uni, cash_asset=cash, fallback_weights=None,
                 description=f"Coarse hindsight oracle for reverse engineering (universe {uni}); base profile {base}",
                 strategies=[{"name": "cash_100", "type": "static", "params": {"weights": {cash: 1.0}}}])
        p = validate(p)
        for mode in ("non_overlapping", "rolling"):
            r = run_profile(p, mode=mode, step_months=12, out_dir=BT / "results" / cid, verbose=False)
            print(cid, mode, r["trace_path"])


if __name__ == "__main__":
    main()
