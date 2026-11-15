"""Facts on the tech look-through of the US market (KF BusEq share of US market cap) used for Amira's
human-capital argument; and the max weight of a cap-weighted US fund compatible with the derived cap.
    uv run --group finance python -I analysis/amira/lookthrough_facts.py
SIMULATION / RESEARCH ONLY."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amira_common import RESULTS, write_json  # noqa: E402
from alphaforge.finance.backtest.data import load_lookthrough  # noqa: E402

cap = json.loads((RESULTS / "amira_sweep_tech" / "derived_thresholds.json").read_text())["result"]["derived"]["tech_cap"]
s = load_lookthrough()["US_IND_BUSEQ"]
pts = {d: float(s.loc[:d].iloc[-1]) for d in ["1926-07-31", "1929-08-31", "1968-12-31", "1972-12-31", "1990-12-31",
                                              "2000-02-29", "2002-09-30", "2007-10-31", "2013-12-31", "2021-12-31",
                                              "2026-09-30"]}
out = {"tech_cap": cap, "buseq_share_at": pts, "max": float(s.max()), "max_date": str(s.idxmax().date()),
       "min": float(s.min()), "min_date": str(s.idxmin().date()),
       "share_months_above_cap": float((s > cap).mean()), "first_month_above_cap": str(s[s > cap].index.min().date())
       if (s > cap).any() else None,
       "max_us_mkt_weight_under_cap_now": cap / float(s.iloc[-1]),
       "note": "KF 12-industry BusEq (SIC computers, software, electronics) != GICS IT; GOOGL/AMZN/META classification "
               "depends on SIC codes. SPY/ESGV approximated by US_MKT."}
print(json.dumps(out, indent=1))
print(write_json(out, RESULTS / "amira_analysis" / "lookthrough_facts.json", ["data/long/lookthrough_us_mkt.parquet"]))
