"""Cross-era robust choice among ETF-implementable strategies (rule fixed before reading the output):
  for each run r (CAD 1977+ and USD 1926+, non-overlapping 15y, rolling 15y, rolling 20y) and strategy s:
    regret(s, r) = best eligible p10(r) - p10(s, r)   (eligible = DD-budget breach rate <= 10 %)
  retained = strategy present in all runs, eligible in all runs, with the smallest WORST regret (minimax regret).
  Static mixes are compared through their family (US share 100 % in the USD era; best member reported separately).
Writes results/amira_analysis/cross_era_etf.json. SIMULATION ONLY.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amira_common import BT, RESULTS, write_json  # noqa: E402


def _best_static(col: pd.Series) -> dict:
    st = col.filter(regex=r"^E\d").dropna()
    return {"strategy": st.idxmax(), "p10": float(st.max())} if len(st) else {"strategy": None, "p10": None,
                                                                              "note": "no eligible static mix"}


def main():
    files = sorted(glob.glob(str(RESULTS / "amira_analysis" / "amira_etf*_select.json")))
    p10, elig, inputs = {}, {}, []
    for f in files:
        d = json.loads(Path(f).read_text())["result"]
        r = pd.DataFrame(d["robust"]).set_index("strategy")
        tr = json.loads((BT / d["trace"]).read_text())
        key = f"{tr['profile']['id']}|{tr['profile']['mode']}|h{tr['profile']['horizon_years']:g}"
        p10[key] = r["score_p10"]
        elig[key] = r["eligible"]
        inputs.append(Path(f).relative_to(BT).as_posix())
    P = pd.DataFrame(p10)
    E = pd.DataFrame(elig).fillna(False).astype(bool)
    best = P.where(E).max()
    regret = best - P
    common = P.dropna().index
    ok = [s for s in common if E.loc[s].all()]
    tab = pd.DataFrame({"worst_regret": regret.loc[ok].max(axis=1), "mean_regret": regret.loc[ok].mean(axis=1),
                        "min_p10": P.loc[ok].min(axis=1)}).sort_values("worst_regret")
    out = {"rule": __doc__.split("rule fixed before reading the output):")[1].split("Writes")[0].strip(),
           "runs": list(P.columns), "best_eligible_p10_per_run": best.to_dict(),
           "retained": tab.index[0], "table": tab.reset_index().rename(columns={"index": "strategy"}).to_dict(orient="records"),
           "p10_matrix": P.loc[ok].reset_index().rename(columns={"index": "strategy"}).to_dict(orient="records"),
           "best_static_per_run": {c: _best_static(P[c].where(E[c])) for c in P.columns}}
    print(tab.round(4).to_string())
    print(json.dumps(out["best_static_per_run"], indent=1))
    print(write_json(out, RESULTS / "amira_analysis" / "cross_era_etf.json", inputs))


if __name__ == "__main__":
    main()
