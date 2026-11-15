"""Glidepath / de-risking start sensitivity (end-of-horizon risk for a fixed liquidation date).
For each era (ESG variant), rolling 10y windows step 12: runs static and (delayed) glidepath strategies with
engine.backtest.run_window and measures the risk in the LAST 36 months (max drawdown, real return) - the
quantity that matters when the money is needed at a fixed date. Writes results/mateo_analysis/glide_<era>.json.
SIMULATION ONLY."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import metrics as M  # noqa: E402
from engine.backtest import ConstraintProvider, run_window  # noqa: E402
from engine.data import data_version, load_inflation, load_returns  # noqa: E402
from engine.run import engine_hash  # noqa: E402
from engine.strategies import build_strategy  # noqa: E402
from engine.windows import windows  # noqa: E402

OUT = common.BT / "results" / "mateo_analysis"


def main(era, var="esg", horizon=10, freq="annual"):
    p = common.load_profile(f"mateo_{era}_{var}")
    for s_ in p["strategies"]:
        if s_["type"] in ("glidepath", "delayed_glidepath"):
            s_["rebalancing"] = {"frequency": freq}
    p = common.inject_glide_params(p, horizon)
    R = load_returns(p["universe"], p["period"]["start"], None, p["currency"], p["fx_fill"])
    infl = load_inflation(p["currency"])
    R = R.loc[: infl.index.max()]
    prov = ConstraintProvider(p["universe"], p["constraints"])
    wins = windows(horizon, R.index.min(), R.index.max(), "rolling", 12, index=R.index)
    names = ["static_eq40", "static_eq60", "static_eq70", "glidepath_lin_70_40"] + \
        [s["name"] for s in p["strategies"] if s["type"] == "delayed_glidepath"]
    strats = [build_strategy(s) for s in p["strategies"] if s["name"] in names]
    # engine fix 2026-11-14: progress = i / last decision -> glides now reach end weights with any frequency.
    eqcls = {"equity_us", "sector_us", "equity_ca"}
    from engine.data import load_assets
    cat = load_assets()
    eqmask = np.array([cat.at[a, "asset_class"] in eqcls for a in R.columns])
    recs = []
    for w in wins:
        for s in strats:
            res = run_window(R, infl, w, s, p, prov, None, None)
            r = res["returns"].values
            inf = infl.reindex(res["returns"].index).values
            last = r[-36:]
            recs.append({"window": w.label, "strategy": s.name, "ann_real_return": res["metrics"]["ann_real_return"],
                         "max_drawdown": res["metrics"]["max_drawdown"],
                         "last36_maxdd": M.max_drawdown(last),
                         "last36_real_return_cum": float(np.prod((1 + last) / (1 + inf[-36:])) - 1),
                         "last24_real_return_cum": float(np.prod((1 + r[-24:]) / (1 + inf[-24:])) - 1),
                         "avg_equity": float(res["weights"].values[:, eqmask].sum(axis=1).mean())})
    df = pd.DataFrame(recs)
    g = df.groupby("strategy")
    summ = pd.DataFrame({
        "avg_equity": g["avg_equity"].mean(),
        "real_p10": g["ann_real_return"].quantile(0.1), "real_median": g["ann_real_return"].median(),
        "p_real_below_0": g["ann_real_return"].apply(lambda s: float((s < 0).mean())),
        "last36_maxdd_p90": g["last36_maxdd"].quantile(0.9), "last36_maxdd_worst": g["last36_maxdd"].max(),
        "last24_real_p10": g["last24_real_return_cum"].quantile(0.1),
        "p_last24_real_loss_gt10": g["last24_real_return_cum"].apply(lambda s: float((s < -0.10).mean())),
    }).sort_values("avg_equity")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trace = {"run_id": f"glide_{era}_{var}_{stamp}", "disclaimer": "Simulation historique uniquement, pas un conseil.",
             "engine_sha256": engine_hash(), "data_version": data_version(), "patch_note": common.PATCH_NOTE,
             "profile": f"profiles/mateo_{era}_{var}.yaml", "glide_rebalancing": freq, "mode": "rolling", "step_months": 12, "horizon": horizon,
             "n_windows": len(wins), "data_info": R.attrs["info"],
             "summary": summ.reset_index().to_dict(orient="records"), "rows": df.to_dict(orient="records")}
    path = OUT / f"glide_{era}_{var}_{freq}.json"
    path.write_text(json.dumps(trace, indent=1, default=str))
    pd.set_option("display.width", 220, "display.max_columns", 20)
    print(path, len(wins), "windows")
    print(summ.to_string(float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "esg", 10, sys.argv[3] if len(sys.argv) > 3 else "annual")
