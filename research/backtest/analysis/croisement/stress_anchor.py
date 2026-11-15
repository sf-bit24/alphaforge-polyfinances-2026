"""Item 5 bis (request of 2026-11-15) - is the 2022 stress a discriminating anchor for the RISK CATEGORY?
brain/product/questionnaire-profil.md (origin/master, a65a0b3, read only) ties the category to "the highest band
whose 2022 stress loss fits in L = min(capacity, tolerance)". Test with our data:
  portfolios : the 6 BNC target mixes + cash, and our 3 robust strategies (Robert eq20_gold10 / eq20_2y,
               Mateo risk_parity_iv36, Amira Mom_etf_top3), each simulated on ONE long window with the engine
               (engine.backtest.run_window, annual rebalancing for statics, same params as the persona profiles);
  eras       : CAD 1977+ (CA_GOV_10Y / CA_EQ / US_MKT) and USD 1926+ (UST_10Y / US_MKT, CA equity -> US_MKT:
               no Canadian equity before 1977, declared);
  measures   : 2022 calendar loss; loss (peak-to-trough inside the episode) in 1929-32, 1937-38, 1973-74,
               1980-82, 1987, 1994, 2000-02, 2007-09, 2020, 2022; worst calendar year; worst 12 months;
               CVaR95 of rolling 12-month returns; monthly CVaR5; p90 of max drawdown over rolling windows of
               4 / 10 / 15 years (horizons of Robert / Mateo / Amira, step 12 months);
  tests      : Spearman rank correlation between the 2022 loss and each long-history measure across the BNC
               mixes; spread (max - min) across BNC; band each persona would get under each anchor.
SIMULATION ONLY. Month-end data understate intra-month troughs.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
from engine import metrics as M  # noqa: E402
from engine.profile import load_profile  # noqa: E402

BNC = ["bnc_prudent", "bnc_conservateur", "bnc_pondere", "bnc_equilibre", "bnc_croissance", "bnc_actions"]
EPISODES = {"1929-32": ("1929-09", "1932-06"), "1937-38": ("1937-03", "1938-03"), "1973-74": ("1973-01", "1974-12"),
            "1980-82": ("1980-12", "1982-07"), "1987": ("1987-08", "1987-11"), "1994": ("1994-01", "1994-12"),
            "2000-02": ("2000-09", "2002-09"), "2007-09": ("2007-11", "2009-02"), "2020": ("2020-01", "2020-03"),
            "2022": ("2022-01", "2022-12")}
L = {"robert_capacite": 0.23, "robert_volonte": 0.05, "mateo_capacite": 0.20, "mateo_volonte": 0.15,
     "amira_capacite": 0.40, "amira_sens_0.30": 0.30}
H = {"robert": 4, "mateo": 10, "amira": 15}
INPUTS = ["profiles/x_bnc_amira_cap.yaml", "profiles/robert_cad.yaml", "profiles/robert_long_usd.yaml",
          "profiles/amira_etf.yaml", "profiles/amira_etf_long_usd.yaml", "results/croisement_analysis/stress_mateo_series.json"]


def measures(s: pd.Series) -> dict:
    r = s.values
    out = {"period": [str(s.index[0].date()), str(s.index[-1].date())]}
    y = (1 + s).groupby(s.index.year).prod() - 1
    n = s.groupby(s.index.year).size()
    y = y[n == 12]
    out["loss_2022"] = float(-y.loc[2022]) if 2022 in y.index else None
    for k, (a, b) in EPISODES.items():
        seg = s.loc[a:b]
        full = len(seg) and seg.index[0] <= pd.Timestamp(a) + pd.offsets.MonthEnd(0) and seg.index[-1] >= pd.Timestamp(b) + pd.offsets.MonthEnd(0)
        out[f"ep_{k}"] = float(M.max_drawdown(seg.values)) if full else None
    out["worst_year"] = float(-y.min())
    out["worst_year_when"] = int(y.idxmin())
    roll12 = (1 + s).rolling(12).apply(np.prod, raw=True).dropna() - 1
    out["worst_12m"] = float(-roll12.min())
    tail = np.sort(roll12.values)[: max(1, int(np.ceil(0.05 * len(roll12))))]
    out["cvar95_12m"] = float(-tail.mean())
    out["cvar5_monthly"] = float(M.var_cvar(r, 0.05)[1])
    out["maxdd_full"] = float(M.max_drawdown(r))
    for h in (4, 10, 15):
        m = 12 * h
        dds = [M.max_drawdown(r[i:i + m]) for i in range(0, len(r) - m + 1, 12)]
        out[f"p90_maxdd_h{h}"] = float(np.quantile(dds, 0.9)) if dds else None
        out[f"worst_maxdd_h{h}"] = float(np.max(dds)) if dds else None
    out["episode_max"] = float(np.nanmax([v for k, v in out.items() if k.startswith("ep_") and v is not None]))
    out["episode_max_when"] = max(((k, v) for k, v in out.items() if k.startswith("ep_") and v is not None), key=lambda kv: kv[1])[0]
    return out


def bnc_profile(currency):
    p = load_profile("x_bnc_amira_cap")
    if currency == "USD":
        p = copy.deepcopy(p)
        p.update({"currency": "USD", "universe": ["US_MKT", "UST_10Y", "UST_TBILL"], "cash_asset": "UST_TBILL",
                  "period": {"start": "1926-08", "end": None}})
        for s in p["strategies"]:
            w = s["params"]["weights"]
            s["params"]["weights"] = ({"UST_TBILL": 1.0} if "CA_TBILL" in w else
                                      {"UST_10Y": w.get("CA_GOV_10Y", 0), "US_MKT": w.get("CA_EQ", 0) + w.get("US_MKT", 0)})
    return p


def series():
    S = {"CAD": {}, "USD": {}}
    for cur in ("CAD", "USD"):
        p = bnc_profile(cur)
        for spec in p["strategies"]:
            S[cur][spec["name"]] = c.simulate_long(p, spec, 1)
    for cur, pid, st, skip in (("CAD", "robert_cad", "eq20_gold10", 1), ("USD", "robert_long_usd", "eq20_2y", 1),
                               ("CAD", "amira_etf", "Mom_etf_top3", 14), ("USD", "amira_etf_long_usd", "Mom_etf_top3", 14)):
        p = load_profile(pid)
        spec = next(s for s in p["strategies"] if s["name"] == st)
        S[cur][f"{pid.split('_')[0]}:{st}"] = c.simulate_long(p, spec, skip)
    ms = json.loads((c.OUT / "stress_mateo_series.json").read_text())["results"]
    for k, cur in (("mateo_cad_esg|risk_parity_iv36", "CAD"), ("mateo_usd_long_esg|risk_parity_iv36", "USD")):
        d = ms[k]
        S[cur][f"mateo:risk_parity_iv36"] = pd.Series(d["returns"], index=pd.to_datetime(d["index"]))
    return S


def band_under(anchor: dict, lim: float):
    ok = [b for b in BNC if anchor[b] is not None and anchor[b] <= lim]
    return ok[-1] if ok else "aucun (encaisse)"


def main():
    S = series()
    res = {"episodes": EPISODES, "limits_L": L}
    for cur in ("CAD", "USD"):
        T = {k: measures(v) for k, v in S[cur].items()}
        res[cur] = T
        D = pd.DataFrame(T).T
        b = D.loc[BNC]
        keys = [k for k in D.columns if k.startswith(("ep_", "worst_", "cvar", "p90", "maxdd", "episode_max")) and not k.endswith("when")]
        rank = {}
        for k in keys:
            x = b[k].astype(float)
            if x.notna().sum() >= 4 and b["loss_2022"].notna().all():
                rho = spearmanr(b["loss_2022"].astype(float), x, nan_policy="omit")[0]
                rank[k] = {"spearman_vs_2022": round(float(rho), 3), "spread_bnc": round(float(x.max() - x.min()), 4),
                           "prudent": round(float(x.iloc[0]), 4), "actions": round(float(x.iloc[-1]), 4),
                           "ratio_actions_over_prudent": round(float(x.iloc[-1] / x.iloc[0]), 2) if x.iloc[0] else None}
        allp = D.loc[[i for i in D.index if i != "cash_100"]]
        rank_all = {k: round(float(spearmanr(allp["loss_2022"].astype(float), allp[k].astype(float), nan_policy="omit")[0]), 3)
                    for k in keys if allp[k].notna().sum() >= 5}
        res[f"{cur}_rank_tests_9_portfolios"] = {"portfolios": list(allp.index), "spearman_vs_2022": rank_all,
                                                 "rank_by_2022": list(allp["loss_2022"].astype(float).sort_values().index),
                                                 "rank_by_episode_max": list(allp["episode_max"].astype(float).sort_values().index),
                                                 "rank_by_p90_maxdd_h10": list(allp["p90_maxdd_h10"].astype(float).sort_values().index)}
        res[f"{cur}_rank_tests"] = {"loss_2022_bnc": b["loss_2022"].round(4).to_dict(),
                                    "spread_2022_bnc": round(float(b.loss_2022.max() - b.loss_2022.min()), 4),
                                    "measures": rank}
        anchors = {"stress_2022": b["loss_2022"].to_dict(), "episode_max": b["episode_max"].to_dict(),
                   **{f"p90_maxdd_h{h}": b[f"p90_maxdd_h{h}"].to_dict() for h in (4, 10, 15)}}
        res[f"{cur}_bands"] = {lim_name: {a: band_under(v, lim) for a, v in anchors.items()} for lim_name, lim in L.items()}
        print("=====", cur)
        print(D[["loss_2022", "ep_1929-32", "ep_1973-74", "ep_2000-02", "ep_2007-09", "ep_2020", "worst_year", "worst_12m",
                 "cvar95_12m", "cvar5_monthly", "p90_maxdd_h4", "p90_maxdd_h10", "p90_maxdd_h15", "episode_max", "episode_max_when"]].to_string())
        print(json.dumps(res[f"{cur}_rank_tests_9_portfolios"]))
        print(json.dumps(res[f"{cur}_bands"], indent=0))
    print(c.write("stress_anchor", res, INPUTS + ["data/processed/monthly_returns.parquet",
                                                   "brain:origin/master:product/questionnaire-profil.md (a65a0b3, lines ~159-178)"],
                  {"doc": __doc__}))


if __name__ == "__main__":
    main()
