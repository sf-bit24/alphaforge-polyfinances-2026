"""Structural cost of the fossil-fuel sector exclusion on the US equity core, per 10y window (non-overlapping and
rolling step 12): US_MKT vs US_MKT_XEN (both from the data, USD and CAD), energy share removed, tech share drift,
effective number of industries, tracking error. Writes results/mateo_analysis/esg_struct.json. SIMULATION ONLY."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from alphaforge.finance.backtest import metrics as M  # noqa: E402
from alphaforge.finance.backtest.data import data_version, load_inflation, load_lookthrough, load_returns  # noqa: E402
from alphaforge.finance.backtest.run import engine_hash  # noqa: E402
from alphaforge.finance.backtest.windows import windows  # noqa: E402


def run(currency, start):
    R = load_returns(["US_MKT", "US_MKT_XEN"], start, None, currency)
    infl = load_inflation(currency)
    R = R.loc[: infl.index.max()]
    lt = load_lookthrough()
    out = {}
    for mode in ("non_overlapping", "rolling"):
        recs = []
        for w in windows(10, R.index.min(), R.index.max(), mode, 12, index=R.index):
            x = R.loc[w.start:w.end]
            inf = infl.reindex(x.index).values
            s0 = lt.loc[:w.start - pd.offsets.MonthEnd(1)]
            s0 = s0.iloc[-1] if len(s0) else lt.iloc[0]
            sh_x = s0.drop("US_IND_ENRGY") / (1 - s0["US_IND_ENRGY"])
            m, e = x["US_MKT"].values, x["US_MKT_XEN"].values
            recs.append({"window": w.label, "energy_share_start": float(s0["US_IND_ENRGY"]),
                         "tech_share_mkt_start": float(s0["US_IND_BUSEQ"]), "tech_share_xen_start": float(sh_x["US_IND_BUSEQ"]),
                         "eff_n_industries_mkt": float(1 / (s0 ** 2).sum()), "eff_n_industries_xen": float(1 / (sh_x ** 2).sum()),
                         "real_mkt": M.annualized_real_return(m, inf), "real_xen": M.annualized_real_return(e, inf),
                         "vol_mkt": M.volatility(m), "vol_xen": M.volatility(e),
                         "maxdd_mkt": M.max_drawdown(m), "maxdd_xen": M.max_drawdown(e),
                         "tracking_error": float(np.std(e - m, ddof=1) * np.sqrt(12))})
        d = pd.DataFrame(recs)
        d["real_diff_xen_minus_mkt"] = d.real_xen - d.real_mkt
        d["vol_diff"] = d.vol_xen - d.vol_mkt
        d["maxdd_diff"] = d.maxdd_xen - d.maxdd_mkt
        summ = {"n_windows": len(d), "real_diff_median": d.real_diff_xen_minus_mkt.median(),
                "real_diff_p10": d.real_diff_xen_minus_mkt.quantile(0.1), "real_diff_p90": d.real_diff_xen_minus_mkt.quantile(0.9),
                "real_diff_min": d.real_diff_xen_minus_mkt.min(), "real_diff_max": d.real_diff_xen_minus_mkt.max(),
                "share_windows_xen_better": float((d.real_diff_xen_minus_mkt > 0).mean()),
                "vol_diff_median": d.vol_diff.median(), "maxdd_diff_median": d.maxdd_diff.median(),
                "maxdd_diff_max": d.maxdd_diff.max(), "te_median": d.tracking_error.median(),
                "tech_drift_median": (d.tech_share_xen_start - d.tech_share_mkt_start).median(),
                "tech_drift_max": (d.tech_share_xen_start - d.tech_share_mkt_start).max(),
                "eff_n_loss_median": (d.eff_n_industries_mkt - d.eff_n_industries_xen).median()}
        out[mode] = {"summary": summ, "rows": d.to_dict(orient="records")}
    return out, R.attrs["info"]


def main():
    res = {}
    for ccy, st in (("USD", "1926-07"), ("CAD", "1977-01")):
        r, info = run(ccy, st)
        res[ccy] = {"data_info": info, **r}
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trace = {"run_id": f"esg_struct_{stamp}", "engine_sha256": engine_hash(), "data_version": data_version(),
             "patch_note": common.PATCH_NOTE, "results": res}
    p = common.BT / "results" / "mateo_analysis" / "esg_struct.json"
    p.write_text(json.dumps(trace, indent=1, default=str))
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(p)
    for ccy in res:
        for mode in ("non_overlapping", "rolling"):
            print(ccy, mode, json.dumps({k: round(v, 4) for k, v in res[ccy][mode]["summary"].items()}))
    d = pd.DataFrame(res["USD"]["non_overlapping"]["rows"])
    print(d[["window", "energy_share_start", "tech_share_mkt_start", "tech_share_xen_start", "real_mkt", "real_xen",
             "real_diff_xen_minus_mkt", "vol_diff", "maxdd_diff", "tracking_error"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    d = pd.DataFrame(res["CAD"]["non_overlapping"]["rows"])
    print(d[["window", "energy_share_start", "real_mkt", "real_xen", "real_diff_xen_minus_mkt", "vol_diff", "maxdd_diff"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
