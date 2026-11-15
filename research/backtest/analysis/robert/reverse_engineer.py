"""Reverse engineering of Robert's oracle / ex-ante winners vs variables observable AT THE START of each window.

Inputs: latest engine traces in results/robert_coarse_{usd,cad}/ (coarse hindsight oracle: equity x duration)
and results/robert_long_usd/, results/robert_cad/ (full ex-ante strategy sets).
Features (all known at the end of the month BEFORE the window starts):
  infl_12m      trailing 12-month CPI inflation (engine inflation series, US CPI-U or Canada CPI)
  short_rate    12 x last monthly return of the cash asset (approx. annualised bill yield)
  long_rate     Shiller 'Rate GS10' (USD) / OECD IRLTLT01CAM156N (CAD), percent -> decimal
  slope         long_rate - short_rate ;  d_long_12m = 12-month change of long_rate
  real_short    short_rate - infl_12m
  eq_mom_12m    trailing 12-month total return of the broad equity proxy ; eq_above_ma10 (0/1)
  cape          Shiller CAPE (USD only; NOT point-in-time: earnings are published with a lag)
Targets: coarse-oracle equity share, bond-weighted maturity (years), cash+2y share;
         ex-ante: score difference short-vs-long duration static mixes, and the ex-post best strategy family.
Statistics: Spearman rho with p-value on NON-OVERLAPPING windows (independent-ish, small N);
rolling windows overlap (effective N ~ N / horizon) -> reported as consistency check only.
Label: robuste = same sign in both eras AND p < 0.05 in at least one non-overlapping sample AND |rho| >= 0.3
       in the other era's rolling sample; fragile = significant in one era only; non concluante = otherwise.
Run: .venv/bin/python -I analysis/robert/reverse_engineer.py
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from common import BT, write_trace
from engine.data import load_inflation, load_returns

MAT = {"UST_TBILL": 1 / 12, "CA_TBILL": 0.25, "UST_2Y": 2, "UST_5Y": 5, "UST_10Y": 10, "UST_20Y": 20,
       "CA_GOV_10Y": 10, "CORP_AAA": 20}
EQ = {"US_MKT", "CA_EQ", "US_IND_NODUR", "US_IND_UTILS", "US_IND_HLTH"}


def latest(d: str, mode: str, h: int) -> Path:
    fs = sorted(glob.glob(str(BT / "results" / d / f"*_{mode}_h{h}.json")))
    if not fs:
        raise FileNotFoundError(f"{d} {mode} h{h}")
    return Path(fs[-1])


def shiller() -> pd.DataFrame:
    x = pd.read_excel(BT / "data/raw/shiller/ie_data.xls", sheet_name="Data", header=None, skiprows=8)
    x = x[[0, 6, 12]].dropna(subset=[0])
    x = x[pd.to_numeric(x[0], errors="coerce").notna()]
    y = x[0].astype(float)
    yr, mo = y.astype(int), ((y - y.astype(int)) * 100).round().astype(int)
    idx = pd.to_datetime(dict(year=yr, month=mo, day=1)) + pd.offsets.MonthEnd(0)
    return pd.DataFrame({"long_rate": pd.to_numeric(x[6], errors="coerce").values / 100,
                         "cape": pd.to_numeric(x[12], errors="coerce").values}, index=idx)


def fred_ca_long(name: str = "IRLTLT01CAM156N") -> pd.Series:
    s = pd.read_csv(BT / f"data/raw/fred/{name}.csv")
    s.index = pd.to_datetime(s.iloc[:, 0]) + pd.offsets.MonthEnd(0)
    return pd.to_numeric(s.iloc[:, 1], errors="coerce") / 100


def features(era: str) -> pd.DataFrame:
    if era == "usd":
        R = load_returns(["US_MKT", "UST_TBILL"], currency="USD")
        eq, cash, infl = R["US_MKT"], R["UST_TBILL"], load_inflation("USD")
        sh = shiller()
        long_rate, cape = sh["long_rate"].dropna().combine_first(fred_ca_long("GS10")), sh["cape"]  # GS10 after Shiller ends
    else:
        R = load_returns(["CA_EQ", "CA_TBILL"], currency="CAD")
        eq, cash, infl = R["CA_EQ"], R["CA_TBILL"], load_inflation("CAD")
        long_rate, cape = fred_ca_long(), pd.Series(dtype=float)
    infl = infl.reindex(R.index)
    f = pd.DataFrame(index=R.index)
    f["infl_12m"] = (1 + infl).rolling(12).apply(np.prod, raw=True) - 1
    f["short_rate"] = 12 * cash
    f["long_rate"] = long_rate.reindex(R.index)
    f["slope"] = f["long_rate"] - f["short_rate"]
    f["d_long_12m"] = f["long_rate"].diff(12)
    f["real_short"] = f["short_rate"] - f["infl_12m"]
    f["eq_mom_12m"] = (1 + eq).rolling(12).apply(np.prod, raw=True) - 1
    idx = (1 + eq).cumprod()
    f["eq_above_ma10"] = (idx > idx.rolling(10).mean()).astype(float)
    f["cape"] = cape.reindex(R.index) if len(cape) else np.nan
    return f


def oracle_targets(trace: dict) -> pd.DataFrame:
    rows = []
    for o in trace["oracle"]:
        w = o["weights"]
        eq = sum(v for a, v in w.items() if a in EQ)
        bonds = {a: v for a, v in w.items() if a in MAT}
        bw = sum(bonds.values())
        rows.append({"window": o["window"], "start": pd.Timestamp(o["window"].split("..")[0]) + pd.offsets.MonthEnd(0),
                     "oracle_equity": eq,
                     "oracle_bond_maturity": sum(MAT[a] * v for a, v in bonds.items()) / bw if bw > 1e-6 else np.nan,
                     "oracle_short_share": sum(v for a, v in w.items() if a in ("UST_TBILL", "CA_TBILL", "UST_2Y")),
                     "oracle_score": o["metrics"]["score"]})
    return pd.DataFrame(rows)


def exante_targets(trace: dict, short: str, long: str) -> pd.DataFrame:
    df = pd.DataFrame(trace["results"])
    df = df[~df["hindsight"]]
    piv = df.pivot(index="window", columns="strategy", values="score")
    best = piv.idxmax(axis=1)
    fam = best.map(lambda s: "cash/short" if s.startswith(("cash", "ladder")) else
                   "bonds" if s.startswith("bonds") else
                   "dynamic" if s.startswith(("trend", "momentum", "risk_parity", "min_var", "mean_var", "glide")) else
                   "static_equity")
    return pd.DataFrame({"window": piv.index, "dur_spread": piv[short] - piv[long], "best_exante": best.values,
                         "best_family": fam.values}).reset_index(drop=True)


def corr_table(df: pd.DataFrame, feats: list[str], targets: list[str]) -> list[dict]:
    out = []
    for t in targets:
        for f in feats:
            d = df[[f, t]].dropna()
            if len(d) < 6 or d[f].nunique() < 3:
                continue
            rho, p = spearmanr(d[f], d[t])
            out.append({"target": t, "feature": f, "n": len(d), "rho": float(rho), "p": float(p)})
    return out


def regimes(df: pd.DataFrame, feats: list[str], targets: list[str]) -> list[dict]:
    out = []
    for f in feats:
        d = df.dropna(subset=[f])
        if d[f].nunique() < 2:
            continue
        med = d[f].median()
        binary = set(d[f].unique()) <= {0.0, 1.0}
        hi, lo = (d[d[f] == 1.0], d[d[f] == 0.0]) if binary else (d[d[f] > med], d[d[f] <= med])
        for lab, sub in (("high", hi), ("low", lo)):
            row = {"feature": f, "split": lab, "threshold_median": float(med), "n": len(sub)}
            for t in targets:
                row[f"mean_{t}"] = float(sub[t].mean()) if t in sub and sub[t].notna().any() else None
            if "best_family" in sub:
                row["best_family_counts"] = sub["best_family"].value_counts().to_dict()
            out.append(row)
    return out


def main():
    feats = ["infl_12m", "short_rate", "long_rate", "slope", "d_long_12m", "real_short", "eq_mom_12m",
             "eq_above_ma10", "cape"]
    targets = ["oracle_equity", "oracle_bond_maturity", "oracle_short_share", "dur_spread"]
    payload, files = {}, {}
    for era, coarse, full, short, long in (("usd", "robert_coarse_usd", "robert_long_usd", "ladder_tbill_2y", "bonds_20y"),
                                            ("cad", "robert_coarse_cad", "robert_cad", "cash_100", "bonds_ca10y")):
        F = features(era)
        for mode in ("non_overlapping", "rolling"):
            pc, pf = latest(coarse, mode, 4), latest(full, mode, 4)
            files[f"{era}_{mode}"] = {"coarse_oracle": str(pc.relative_to(BT)), "exante": str(pf.relative_to(BT))}
            o = oracle_targets(json.loads(pc.read_text()))
            e = exante_targets(json.loads(pf.read_text()), short, long)
            df = o.merge(e, on="window", how="left")
            prev = df["start"] - pd.offsets.MonthEnd(1)
            df = pd.concat([df.reset_index(drop=True), F.reindex(prev).reset_index(drop=True)], axis=1)
            key = f"{era}_{mode}"
            payload[key] = {"table": df.drop(columns=["start"]).to_dict(orient="records"),
                            "spearman": corr_table(df, feats, targets),
                            "regimes": regimes(df, feats, ["oracle_equity", "oracle_bond_maturity", "dur_spread"]),
                            "oracle_stability": {t: {"mean": float(df[t].mean()), "std": float(df[t].std()),
                                                     "p10": float(df[t].quantile(.1)), "p90": float(df[t].quantile(.9))}
                                                 for t in ["oracle_equity", "oracle_bond_maturity", "oracle_short_share"]}}
            if era == "usd":  # sub-period stability of correlations (1926-1975 vs 1975-2026)
                for lab, sub in (("pre1975", df[df["start"] < "1975-01-01"]), ("post1975", df[df["start"] >= "1975-01-01"])):
                    payload[key][f"spearman_{lab}"] = corr_table(sub, feats, targets)
            print(f"\n===== {key} (n={len(df)}) =====")
            print(df[["window", "oracle_equity", "oracle_bond_maturity", "oracle_short_share", "dur_spread", "best_exante",
                      "infl_12m", "short_rate", "long_rate", "slope", "d_long_12m", "eq_mom_12m", "cape"]]
                  .to_string(index=False, float_format=lambda v: f"{v:.3f}"))
            ct = pd.DataFrame(payload[key]["spearman"])
            print(ct[ct["p"] < 0.10].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
            print("stability:", json.dumps(payload[key]["oracle_stability"], indent=0))
    # robustness labels
    labels = []
    a = pd.DataFrame(payload["usd_non_overlapping"]["spearman"]).set_index(["target", "feature"])
    b = pd.DataFrame(payload["cad_non_overlapping"]["spearman"]).set_index(["target", "feature"])
    ar = pd.DataFrame(payload["usd_rolling"]["spearman"]).set_index(["target", "feature"])
    br = pd.DataFrame(payload["cad_rolling"]["spearman"]).set_index(["target", "feature"])
    pre = pd.DataFrame(payload["usd_non_overlapping"]["spearman_pre1975"]).set_index(["target", "feature"])
    post = pd.DataFrame(payload["usd_non_overlapping"]["spearman_post1975"]).set_index(["target", "feature"])
    for k in a.index.union(b.index):
        ra = a["rho"].get(k, np.nan); pa = a["p"].get(k, np.nan)
        rb = b["rho"].get(k, np.nan); pb = b["p"].get(k, np.nan)
        rar = ar["rho"].get(k, np.nan); rbr = br["rho"].get(k, np.nan)
        rpre = pre["rho"].get(k, np.nan); rpost = post["rho"].get(k, np.nan)
        same = np.sign(ra) == np.sign(rb) if np.isfinite(ra) and np.isfinite(rb) else False
        sig_a, sig_b = (pa < 0.05) if np.isfinite(pa) else False, (pb < 0.05) if np.isfinite(pb) else False
        if same and (sig_a or sig_b) and ((sig_a and abs(rbr) >= 0.3) or (sig_b and abs(rar) >= 0.3)) \
                and (not np.isfinite(rpre) or not np.isfinite(rpost) or np.sign(rpre) == np.sign(rpost)):
            lab = "robuste"
        elif sig_a or sig_b:
            lab = "fragile"
        else:
            lab = "non concluante"
        labels.append({"target": k[0], "feature": k[1], "rho_usd_nonov": ra, "p_usd_nonov": pa, "rho_cad_nonov": rb,
                       "p_cad_nonov": pb, "rho_usd_roll": rar, "rho_cad_roll": rbr, "rho_usd_pre1975": rpre,
                       "rho_usd_post1975": rpost, "label": lab})
    L = pd.DataFrame(labels)
    print("\n===== LABELS =====")
    print(L.sort_values(["label", "target"]).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    p = write_trace("reverse_engineer", {"by_sample": payload, "labels": labels, "input_traces": files},
                    {"features": feats, "targets": targets, "horizon_years": 4})
    print("trace:", p)


if __name__ == "__main__":
    main()
