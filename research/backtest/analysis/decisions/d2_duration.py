"""D2 (Robert, duration du revenu fixe) : durations empiriques de XBB.TO et ZST.TO, choc de taux 2022,
duration d'un mélange XBB/ZST, rappel des chiffres BNC du croisement.

Lecture seule : starter officiel (prices_daily.csv, macro_rates.csv) et results/croisement_analysis/bnc.json.
Écrit results/decisions_analysis/d2_duration.json. SIMULATION UNIQUEMENT, pas un conseil.

Méthode (durée empirique) : régression des rendements de prix hebdomadaires (vendredi, close ajusté des
fractionnements, sans dividendes : un coupon ne dépend pas des taux) sur la variation hebdomadaire du taux
Canada 2 ans et 10 ans (Banque du Canada, BD.CDN.*.DQ.YLD, en points de % / 100). duration ≈ -bêta.
On prend le taux le plus proche de la maturité moyenne : 2 ans pour ZST.TO (ultra-court), et le meilleur
ajustement d'un mélange 2 ans / 10 ans pour XBB.TO (indice universel, maturité moyenne ≈ 9,5 ans).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

BT = Path(__file__).resolve().parents[2]
STARTER = Path("/mnt/c/Users/User/Desktop/ecole/hackoton/source/Datathon2026/Datathon2026/alphaforge_starter")
OUT = BT / "results" / "decisions_analysis" / "d2_duration.json"


def weekly(series: pd.Series) -> pd.Series:
    return series.sort_index().resample("W-FRI").last().dropna()


def main() -> None:
    px = pd.read_csv(STARTER / "prices_daily.csv", parse_dates=["date"])
    mac = pd.read_csv(STARTER / "macro_rates.csv", parse_dates=["date"])
    y2 = mac[mac.series_id == "BD.CDN.2YR.DQ.YLD"].set_index("date")["value"].astype(float) / 100
    y10 = mac[mac.series_id == "BD.CDN.10YR.DQ.YLD"].set_index("date")["value"].astype(float) / 100
    boc = mac[mac.series_id == "V39079"].set_index("date")["value"].astype(float)
    dy2, dy10 = weekly(y2).diff(), weekly(y10).diff()
    out: dict = {"source": {"prices": str(STARTER / "prices_daily.csv"), "rates": str(STARTER / "macro_rates.csv")},
                 "method": "OLS weekly price return (close) on weekly change in GoC 2y / 10y yields; duration = -beta",
                 "assets": {}}
    for tk in ["XBB.TO", "ZST.TO", "AGG", "TLT"]:
        s = px[px.ticker == tk].set_index("date")["close"].astype(float)
        r = weekly(s).pct_change()
        df = pd.concat({"r": r, "d2": dy2, "d10": dy10}, axis=1).dropna()
        res = {"n_weeks": int(len(df)), "start": str(df.index.min().date()), "end": str(df.index.max().date())}
        for k in ["d2", "d10"]:
            b = np.polyfit(df[k], df["r"], 1)[0]
            rr = np.corrcoef(df[k], df["r"])[0, 1] ** 2
            res[f"duration_vs_{k}"] = round(float(-b), 2)
            res[f"r2_vs_{k}"] = round(float(rr), 3)
        # blended: best mix a*d2 + (1-a)*d10
        best = None
        for a in np.linspace(0, 1, 21):
            x = a * df["d2"] + (1 - a) * df["d10"]
            b = np.polyfit(x, df["r"], 1)[0]
            rr = np.corrcoef(x, df["r"])[0, 1] ** 2
            if best is None or rr > best[2]:
                best = (a, b, rr)
        res["duration_vs_best_mix"] = {"weight_2y": round(float(best[0]), 2), "duration": round(float(-best[1]), 2),
                                       "r2": round(float(best[2]), 3)}
        y22 = px[(px.ticker == tk) & (px.date.dt.year == 2022)].set_index("date")["adj_close"].astype(float)
        prev = px[(px.ticker == tk) & (px.date < "2022-01-01")].set_index("date")["adj_close"].astype(float)
        res["total_return_2022_adj_close"] = round(float(y22.iloc[-1] / prev.iloc[-1] - 1), 4)
        out["assets"][tk] = res

    def lvl(s: pd.Series, d: str, before: bool = True) -> float:
        s = s.sort_index()
        return float(s.loc[:d].iloc[-1]) if before else float(s.loc[d:].iloc[0])
    out["rates_2022"] = {
        "boc_policy_rate_2021_12_31": lvl(boc, "2021-12-31"), "boc_policy_rate_2022_12_30": lvl(boc, "2022-12-30"),
        "goc_2y_2021_12_31": round(lvl(y2, "2021-12-31") * 100, 2), "goc_2y_2022_12_30": round(lvl(y2, "2022-12-30") * 100, 2),
        "goc_10y_2021_12_31": round(lvl(y10, "2021-12-31") * 100, 2), "goc_10y_2022_12_30": round(lvl(y10, "2022-12-30") * 100, 2),
    }
    # duration of a XBB/ZST blend using the issuer duration for XBB (iShares, 6.74 y at 2026-11-12) and the
    # empirical ZST duration (BMO page not reachable from here)
    d_xbb_issuer = 6.74
    d_zst = out["assets"]["ZST.TO"]["duration_vs_d2"]
    out["blend_duration"] = {
        "assumption": "XBB.TO effective duration 6.74 y (iShares page, as of 2026-11-12); ZST.TO = empirical vs 2y",
        "100_xbb": d_xbb_issuer,
        "50_xbb_50_zst": round(0.5 * d_xbb_issuer + 0.5 * d_zst, 2),
        "30_xbb_40_zst_of_70": round((0.3 * d_xbb_issuer + 0.4 * d_zst) / 0.7, 2),
        "fixed_income_share_of_portfolio_for_conservateur": 0.70,
        "portfolio_level_rate_sensitivity_100_xbb": round(0.70 * d_xbb_issuer, 2),
        "portfolio_level_rate_sensitivity_50_50": round(0.70 * (0.5 * d_xbb_issuer + 0.5 * d_zst), 2),
    }
    bnc = json.loads((BT / "results" / "croisement_analysis" / "bnc.json").read_text())
    out["bnc_json_top_level_keys"] = list(bnc.keys())[:20]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
