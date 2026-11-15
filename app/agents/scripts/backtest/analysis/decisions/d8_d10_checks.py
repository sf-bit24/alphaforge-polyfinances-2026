"""D8 (ESGV « non backtesté ») et D10 (CNQ.TO 2022-08-22) : contrôles chiffrés.

D8 : historique disponible pour juger ESGV sur 10 ans — ETF (données partagées, USD) et indice FTSE US All Cap
Choice (base 2015-03-20, lancement 2018-08-13 d'après la fiche FTSE Russell du 2026-10-30 ; rendements annuels
recopiés de cette fiche, avec la mention « hypothetical » avant le lancement).
D10 : reconstitution du 2022-08-22 à partir du starter (close, adj_close, corporate_actions) et des communiqués
CNQ (dividende spécial de 1,50 $ CA par action, record 2022-08-23 ; fractionnement 2 pour 1, ex 2024-06-11).

Écrit results/decisions_analysis/d8_d10_checks.json. SIMULATION UNIQUEMENT, pas un conseil.
"""
from __future__ import annotations

import json
from pathlib import Path
from alphaforge.finance.backtest.paths import starter_dir

import pandas as pd

BT = Path(__file__).resolve().parents[2]
STARTER = starter_dir()  # official starter, committed in the app
OUT = BT / "results" / "decisions_analysis" / "d8_d10_checks.json"

# FTSE Russell factsheet "FTSE US All Cap Choice Index", data as at 30 October 2026 (downloaded 2026-11-14),
# calendar total returns in USD; "Returns shown before the index launch date reflect hypothetical historical performance".
FTSE_CHOICE = {2016: 11.2, 2017: 23.0, 2018: -3.6, 2019: 33.5, 2020: 25.8, 2021: 26.5, 2022: -24.0, 2023: 30.8,
               2024: 24.8, 2025: 16.6}
FTSE_PARENT = {2016: 12.5, 2017: 21.5, 2018: -5.2, 2019: 31.3, 2020: 21.1, 2021: 25.7, 2022: -19.2, 2023: 26.3,
               2024: 23.8, 2025: 17.2}


def n_windows(start: str, end: str, years: int = 10, step: int = 12) -> list[str]:
    idx = pd.period_range(start, end, freq="M")
    out, i = [], 0
    while i + 12 * years <= len(idx):
        out.append(f"{idx[i]}..{idx[i + 12 * years - 1]}")
        i += step
    return out


def d8() -> dict:
    from alphaforge.finance.backtest.data import load_returns
    R = load_returns(["ESGV", "SPY", "US_MKT"], start="2018-10", currency="USD")
    diff = {y: round(FTSE_CHOICE[y] - FTSE_PARENT[y], 1) for y in FTSE_CHOICE}
    y22 = (1 + R.loc["2022"]).prod() - 1
    return {
        "etf_months_in_data": int(len(R)), "etf_period": [str(R.index.min().date()), str(R.index.max().date())],
        "etf_full_10y_windows": n_windows(str(R.index.min().to_period("M")), str(R.index.max().to_period("M"))),
        "index_live_since_launch_full_10y_windows": n_windows("2018-09", "2026-10"),
        "index_incl_backtest_full_10y_windows": n_windows("2015-04", "2026-10"),
        "backtest_months_in_first_index_window": len(pd.period_range("2015-04", "2018-08", freq="M")),
        "ftse_choice_minus_parent_calendar_pts": diff,
        "ftse_choice_minus_parent_live_years_mean_pts": round(sum(diff[y] for y in range(2019, 2026)) / 7, 2),
        "etf_2022_usd": {k: round(float(v), 4) for k, v in y22.items()},
        "monthly_corr_esgv_spy": round(float(R["ESGV"].corr(R["SPY"])), 4),
        "ann_return_gap_esgv_minus_spy_pts": round(100 * float(((1 + R["ESGV"]).prod() ** (12 / len(R)) - 1)
                                                         - ((1 + R["SPY"]).prod() ** (12 / len(R)) - 1)), 2),
    }


def d10() -> dict:
    px = pd.read_csv(STARTER / "prices_daily.csv", parse_dates=["date"])
    ca = pd.read_csv(STARTER / "corporate_actions.csv", parse_dates=["ex_date"])
    c = px[px.ticker == "CNQ.TO"].set_index("date").sort_index()
    t0, t1 = pd.Timestamp("2022-08-19"), pd.Timestamp("2022-08-22")
    ev = ca[(ca.ticker == "CNQ.TO") & (ca.ex_date.isin([t1, pd.Timestamp("2024-06-11")]))]
    split_2024 = 2.0
    fake_split = float(ev[(ev.action == "split") & (ev.ex_date == t1)]["value"].iloc[0])
    div_starter = float(ev[(ev.action == "dividend") & (ev.ex_date == t1)]["value"].iloc[0])
    # unadjusted (as traded in 2022) prices: Yahoo divides pre-event closes by every later split factor
    raw0 = float(c.at[t0, "close"]) * split_2024 * fake_split
    raw1 = float(c.at[t1, "close"]) * split_2024
    div_raw = 1.50  # CNQ press release 2022-08-04 (EDGAR 6-K 0001017413-22-000049)
    tr = (raw1 + div_raw) / raw0 - 1
    return {
        "starter_rows": {"close_2022_08_19": float(c.at[t0, "close"]), "close_2022_08_22": float(c.at[t1, "close"]),
                         "adj_close_2022_08_19": float(c.at[t0, "adj_close"]), "adj_close_2022_08_22": float(c.at[t1, "adj_close"])},
        "starter_corporate_actions": ev.astype(str).to_dict("records"),
        "dividend_in_starter_equals_1_50_over_2024_split": abs(div_starter - div_raw / split_2024) < 1e-9,
        "implied_unadjusted_close_2022_08_19": round(raw0, 2), "implied_unadjusted_close_2022_08_22": round(raw1, 2),
        "price_only_return": round(raw1 / raw0 - 1, 5),
        "true_total_return_with_1_50_dividend": round(tr, 5),
        "close_return_starter": round(float(c.at[t1, "close"] / c.at[t0, "close"] - 1), 5),
        "adj_close_return_starter": round(float(c.at[t1, "adj_close"] / c.at[t0, "adj_close"] - 1), 5),
        "dividend_yield_on_ex_date": round(div_raw / raw0, 5), "one_minus_1_over_fake_split": round(1 - 1 / fake_split, 5),
        "double_count_pts": round(100 * (float(c.at[t1, "adj_close"] / c.at[t0, "adj_close"] - 1) - tr), 2),
    }


def main() -> None:
    out = {"disclaimer": "SIMULATION ONLY", "d8_esgv": d8(), "d10_cnq": d10()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
