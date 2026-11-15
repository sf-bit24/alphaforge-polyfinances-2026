"""Persona 35 - reverse engineering of the ORACLE (hindsight=True, NOT investable) for pockets A and B.

Oracle features per window: USD share (sum of weights of USD assets), equity share, gold weight, duration proxy.
Start-of-window variables (observed at the END of the month BEFORE the window, no look-ahead):
  rate_diff   = CA short rate - US short rate  (12 x monthly return of CA_TBILL - UST_TBILL, CAD/USD local)
  fx_12m      = USDCAD change over the previous 12 months
  fx_vs_med120= USDCAD / its trailing 120-month median - 1 (level vs own past, NOT a 'fair value')
  infl_diff   = CPI CA 12m - CPI US 12m
  eq_rel_12m  = CA_EQ 12m return - US_MKT 12m return (CAD)
Spearman rho on (a) pocket A: non-overlapping 6-month windows (every 6th rolling window, N ~ 110);
(b) pocket B: rolling 15y windows (N = 35, heavily overlapping: effective N ~ 3 -> consistency check only).
Labels: robust = |rho| >= 0.3, p < 0.05 in A non-overlapping AND same sign in both halves (pre/post 1999);
fragile = significant in one sample only; inconclusive otherwise. ~10 tests per sample -> ~0.5 false positives at 5 %.
NO causality. Outputs results/p35_analysis/reverse.json. SIMULATION ONLY - no FX forecast.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import common as C
from alphaforge.finance.backtest.data import load_assets, load_inflation, load_returns

USD_ASSETS = set(load_assets().query("currency == 'USD'").index)
EQ_CLASSES = {"equity_us", "equity_ca", "sector_us", "equity_single", "etf_equity"}
CAT = load_assets()


def start_vars() -> pd.DataFrame:
    Rl = load_returns(["CA_TBILL", "UST_TBILL", "CA_EQ", "US_MKT"], "1971-02", "2026-09", "CAD")
    Ru = load_returns(["UST_TBILL"], "1971-02", "2026-09", "USD")
    ca_loc = load_returns(["CA_TBILL"], "1971-02", "2026-09", "CAD")["CA_TBILL"]
    fx = C.fx_monthly()
    pc, pu = load_inflation("CAD"), load_inflation("USD")
    df = pd.DataFrame(index=ca_loc.index)
    df["rate_diff"] = 12 * (ca_loc - Ru["UST_TBILL"].reindex(df.index))
    df["fx_12m"] = (fx / fx.shift(12) - 1).reindex(df.index)
    df["fx_vs_med120"] = (fx / fx.rolling(120, min_periods=60).median() - 1).reindex(df.index)
    df["infl_diff"] = ((1 + pc).rolling(12).apply(np.prod) - (1 + pu).rolling(12).apply(np.prod)).reindex(df.index)
    eq = Rl[["CA_EQ", "US_MKT"]].reindex(df.index)
    df["eq_rel_12m"] = (1 + eq["CA_EQ"]).rolling(12).apply(np.prod) - (1 + eq["US_MKT"]).rolling(12).apply(np.prod)
    return df


def features(w: dict) -> dict:
    w = {k: float(v) for k, v in w.items()}
    return {"usd_share": sum(v for k, v in w.items() if k in USD_ASSETS),
            "equity_share": sum(v for k, v in w.items() if CAT.at[k, "asset_class"] in EQ_CLASSES),
            "gold": w.get("GOLD", 0.0) + w.get("GLD", 0.0),
            "duration_years": sum(v * (float(CAT.at[k, "maturity_years"]) if str(CAT.at[k, "maturity_years"]).strip() else
                                       (0.1 if CAT.at[k, "asset_class"] == "cash" else 0.0)) for k, v in w.items())}


def oracle_frame(trace: Path) -> pd.DataFrame:
    t = json.loads(trace.read_text())
    rows = []
    for o in t["oracle"]:
        s = pd.Timestamp(o["window"].split("..")[0]) + pd.offsets.MonthEnd(0)
        rows.append({"window": o["window"], "start": s, **features(o["weights"])})
    return pd.DataFrame(rows).set_index("start")


def corr_block(of: pd.DataFrame, sv: pd.DataFrame, targets: list[str]) -> dict:
    X = sv.shift(1).reindex(of.index)   # variable at the end of the month BEFORE the window starts
    out = {}
    for tg in targets:
        for v in sv.columns:
            d = pd.concat([of[tg], X[v]], axis=1).dropna()
            if len(d) < 6 or d[tg].std() == 0:
                continue
            r, p = spearmanr(d[tg], d[v])
            pre = d[d.index.year < 1999]
            post = d[d.index.year >= 1999]
            rp = spearmanr(pre[tg], pre[v])[0] if len(pre) > 5 and pre[tg].std() > 0 else np.nan
            rq = spearmanr(post[tg], post[v])[0] if len(post) > 5 and post[tg].std() > 0 else np.nan
            out[f"{tg}~{v}"] = {"rho": float(r), "p": float(p), "n": int(len(d)), "rho_pre1999": float(rp),
                                "rho_post1999": float(rq)}
    return out


def stability(of: pd.DataFrame) -> dict:
    return {c: {"mean": float(of[c].mean()), "std": float(of[c].std()), "p10": float(of[c].quantile(.1)),
                "p90": float(of[c].quantile(.9)), "share_at_0": float((of[c] < 0.03).mean()),
                "share_at_1": float((of[c] > 0.97).mean())} for c in ("usd_share", "equity_share", "gold", "duration_years")}


def label(a: dict, b: dict | None) -> dict:
    lab = {}
    for k, v in a.items():
        same_halves = np.sign(v["rho_pre1999"]) == np.sign(v["rho_post1999"]) and np.isfinite(v["rho_pre1999"])
        sig = v["p"] < 0.05 and abs(v["rho"]) >= 0.3
        if sig and same_halves:
            lab[k] = "robust"
        elif sig:
            lab[k] = "fragile"
        else:
            lab[k] = "inconclusive"
    return lab


if __name__ == "__main__":
    sv = start_vars()
    trA = C.latest("p35_A_usd", "*_rolling_h0.5.json")
    ofA = oracle_frame(trA)
    ofA_no = ofA.iloc[::6]
    trB = C.latest("p35_B_cad", "*_rolling_h15.json")
    ofB = oracle_frame(trB)
    trB20 = C.latest("p35_B_cad", "*_rolling_h20.json")
    ofB20 = oracle_frame(trB20)
    cA = corr_block(ofA_no, sv, ["usd_share", "duration_years"])
    cB = corr_block(ofB, sv, ["usd_share", "equity_share", "gold"])
    res = {"traces": {"A": str(trA), "B15": str(trB), "B20": str(trB20)},
           "A_stability": stability(ofA), "B15_stability": stability(ofB), "B20_stability": stability(ofB20),
           "A_corr_nonoverlap": cA, "A_labels": label(cA, None), "B15_corr_rolling": cB,
           "B15_labels_consistency_only": label(cB, None),
           "B15_oracle_per_window": ofB.reset_index().astype({"start": str}).to_dict(orient="records")}
    p = C.write_trace("reverse", res, {"note": __doc__.split("Labels:")[0]}, "reverse.py")
    print(json.dumps({k: v for k, v in res.items() if k != "B15_oracle_per_window"}, indent=1, default=str)[:6000])
    print(p)
