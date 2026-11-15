"""Persona 35 - pocket A (USD winter reserve): coverage of 6 monthly USD payments (Nov..Apr) funded at the end
of October with exactly the CAD needed at that day's rate (no buffer), 1971/72 -> 2025/26 winters.

Options (USD returns; holding a CAD asset and converting each month = 'tranches'):
  usd_tbill / usd_2y / usd_5y : convert everything at t0 (lump sum), hold in USD
  cad_tbill / cad_10y         : keep CAD, convert each month what is needed (monthly tranches)
  half                        : 50 % converted at t0 (T-bills USD), 50 % monthly tranches (CA T-bills)
  zst / agg (2011+ / 2003+)   : real ETFs (ZST.TO tranches, AGG lump)
Payments indexed to US CPI. Coverage = 1 + end balance / sum of payments (1 = exactly covered, < 1 = shortfall).
Also: 'prefund' variant (reserve set aside at end of April, 6 months before the winter).
Derived threshold: buffer needed so that the worst historical winter is covered (capacity of pocket A).

Outputs: results/p35_analysis/pocket_a.json. SIMULATION ONLY. No FX forecast.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd

import common as C
from alphaforge.finance.backtest.data import load_inflation, load_returns

OPTS = {"usd_tbill": {"UST_TBILL": 1.0}, "usd_2y": {"UST_2Y": 1.0}, "usd_5y": {"UST_5Y": 1.0},
        "cad_tbill_tranches": {"CA_TBILL": 1.0}, "cad_10y_tranches": {"CA_GOV_10Y": 1.0},
        "half_usd_tbill_half_cad_tranches": {"UST_TBILL": 0.5, "CA_TBILL": 0.5}}
OPTS_ETF = {"usd_tbill": {"UST_TBILL": 1.0}, "agg_lump": {"AGG": 1.0}, "zst_tranches": {"ZST.TO": 1.0},
            "cad_tbill_tranches": {"CA_TBILL": 1.0}, "xbb_tranches": {"XBB.TO": 1.0},
            "half_usd_tbill_half_zst": {"UST_TBILL": 0.5, "ZST.TO": 0.5}}


def coverage(Ru: pd.DataFrame, cpi: pd.Series, w: dict, t0: pd.Timestamp, wait: int = 0, n_pay: int = 6) -> float:
    """Separate sub-accounts per asset (each funds its share w of every payment) -> no implicit rebalancing."""
    idx = Ru.index
    i0 = idx.get_loc(t0)
    months = idx[i0 + 1: i0 + 1 + wait + n_pay]
    if len(months) < wait + n_pay:
        return np.nan
    pay_months = months[wait:]
    base = cpi.loc[t0]
    L = np.array([cpi.loc[m] / base for m in pay_months])     # USD payments, US-CPI indexed, L0 = 1
    tot_need = L.sum()
    end = 0.0
    for a, share in w.items():
        bal = share * n_pay                                     # funded with nominal need at t0 (no buffer)
        k = 0
        for m in months:
            bal *= 1 + Ru.at[m, a]
            if m in pay_months:
                bal -= share * L[k]
                k += 1
        end += bal
    return 1 + end / tot_need


def regret(F: pd.Series, t0: pd.Timestamp, n_pay: int = 6) -> dict:
    i0 = F.index.get_loc(t0)
    path = F.iloc[i0 + 1: i0 + 1 + n_pay]
    return {"rate_lump": float(F.loc[t0]), "rate_tranches_avg": float(path.mean()),
            "tranche_vs_lump": float(path.mean() / F.loc[t0] - 1)}


def summarize(x: pd.Series) -> dict:
    x = x.dropna()
    return {"n": int(len(x)), "mean": float(x.mean()), "p10": float(x.quantile(.1)), "median": float(x.median()),
            "worst": float(x.min()), "worst_winter": str(x.idxmin().date()) if len(x) else None,
            "best": float(x.max()), "std": float(x.std()), "share_below_1": float((x < 1 - 1e-9).mean()),
            "buffer_to_cover_worst": float(max(0.0, 1 / x.min() - 1)),
            "buffer_to_cover_p10": float(max(0.0, 1 / x.quantile(.1) - 1))}


def run(opts: dict, start: str, label: str) -> dict:
    assets = sorted({a for w in opts.values() for a in w})
    Ru = load_returns(assets, start, "2026-09", "USD")
    cpi = (1 + load_inflation("USD")).cumprod()
    F = C.fx_monthly()
    octs = [d for d in Ru.index if d.month == 10]
    aprs = [d for d in Ru.index if d.month == 4]
    res = {"period": [str(Ru.index.min().date()), str(Ru.index.max().date())], "options": {}}
    for name, w in opts.items():
        cov = pd.Series({t0: coverage(Ru, cpi, w, t0) for t0 in octs})
        pre = pd.Series({t0: coverage(Ru, cpi, w, t0, wait=6) for t0 in aprs})
        anym = pd.Series({t0: coverage(Ru, cpi, w, t0) for t0 in Ru.index[:-6]})
        res["options"][name] = {"weights": w, "winter_funded_end_october": summarize(cov),
                                "prefunded_end_april": summarize(pre), "any_start_month_6m": summarize(anym),
                                "per_winter": {str(k.date()): float(v) for k, v in cov.dropna().items()}}
    reg = pd.DataFrame({t0: regret(F, t0) for t0 in octs if F.index.get_loc(t0) + 6 < len(F)}).T
    tv = reg["tranche_vs_lump"]
    res["lump_vs_tranches_rate"] = {
        "definition": "average USDCAD paid by monthly tranches Nov..Apr / USDCAD at end of October - 1 "
                      "(> 0: tranches were dearer ex post, < 0: cheaper)",
        "n_winters": int(len(tv)), "median": float(tv.median()), "p10": float(tv.quantile(.1)),
        "p90": float(tv.quantile(.9)), "min": float(tv.min()), "max": float(tv.max()),
        "share_tranches_cheaper": float((tv < 0).mean()), "abs_mean": float(tv.abs().mean()),
        "worst_regret_lump": {"winter": str(tv.idxmin().date()), "value": float(tv.min())},
        "worst_regret_tranches": {"winter": str(tv.idxmax().date()), "value": float(tv.max())}}
    return res


if __name__ == "__main__":
    out = {"proxies_1971": run(OPTS, "1971-02", "proxies"), "etf_2011": run(OPTS_ETF, "2011-03", "etf"),
           "etf_real_period_2021": run(OPTS_ETF, "2021-11", "etf_real")}
    p = C.write_trace("pocket_a", out, {"payments": "6 monthly USD payments Nov..Apr, US-CPI indexed",
                                         "funding": "exactly the need at t0 rate, no buffer",
                                         "accounts": "one sub-account per asset, no rebalancing"}, "pocket_a.py")
    for k, v in out.items():
        print("==", k, v["period"])
        for n, o in v["options"].items():
            a, b, c = o["winter_funded_end_october"], o["prefunded_end_april"], o["any_start_month_6m"]
            print(f"  {n:34s} oct: n={a['n']} p10={a['p10']:.4f} worst={a['worst']:.4f} ({a['worst_winter']}) "
                  f"share<1={a['share_below_1']:.2f} buf={a['buffer_to_cover_worst']:.4f} | apr worst={b['worst']:.4f} "
                  f"share<1={b['share_below_1']:.2f} | any worst={c['worst']:.4f} share<1={c['share_below_1']:.2f}")
        print("  regret", {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v["lump_vs_tranches_rate"].items()})
    print(p)
