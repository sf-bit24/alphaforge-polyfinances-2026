"""Tableaux Markdown générés à partir des sorties (``tables.md``) : le rapport VALIDATION.md n'en recopie que des
extraits, chaque chiffre vient donc d'un fichier produit par ce module."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

MODEL_ORDER = [
    "sbb",
    "sbb_ca",
    "iid",
    "iid_ca",
    "hmm_rs",
    "hmm_rs_ca",
    "hmm_rs_fl",
    "sbb_L06",
    "sbb_L12",
    "sbb_L48",
    "sbb_L96",
    "hist_emp",
    "stress_2022",
]


def _pct(x, d=0):
    return "" if x is None or not np.isfinite(x) else f"{100 * x:.{d}f}"


def _ci(m, lo, hi, d=0):
    if m is None or not np.isfinite(m):
        return "n/a"
    return f"{_pct(m, d)} [{_pct(lo, d)}; {_pct(hi, d)}]"


def _num(x, d=3):
    return "" if x is None or not np.isfinite(x) else f"{x:.{d}f}"


def md(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(vide)_\n"
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines) + "\n"


def _order(df: pd.DataFrame) -> pd.DataFrame:
    rank = {m: i for i, m in enumerate(MODEL_ORDER)}
    return df.assign(_r=df["model"].map(lambda m: rank.get(m, 99))).sort_values(["_r"]).drop(columns="_r")


def pooled_table(pooled: pd.DataFrame, family: str, H: int, models=None) -> str:
    g = pooled[(pooled["family"] == family) & (pooled["H"] == H)]
    if models:
        g = g[g["model"].isin(models)]
    g = _order(g)
    rows = []
    for _, r in g.iterrows():
        rows.append(
            {
                "modèle": r["model"],
                "n orig. (indép.)": f"{r['n_origins']} ({r['n_nonoverlap']})",
                "couv. 80 % rend.": _ci(r["in80_ret"], r["in80_ret_lo"], r["in80_ret_hi"]),
                "couv. 90 % rend.": _ci(r["in90_ret"], r["in90_ret_lo"], r["in90_ret_hi"]),
                "rend. < p10": _ci(r["below_ret_q10"], r["below_ret_q10_lo"], r["below_ret_q10_hi"]),
                "couv. 80 % MDD": _ci(r["in80_mdd"], r["in80_mdd_lo"], r["in80_mdd_hi"]),
                "MDD > p90": _ci(r["exc_mdd_q90"], r["exc_mdd_q90_lo"], r["exc_mdd_q90_hi"]),
                "CRPSS rend.": _ci(
                    r.get("crps_ret_skill", np.nan), r.get("crps_ret_skill_lo"), r.get("crps_ret_skill_hi")
                ),
                "CRPSS MDD": _ci(
                    r.get("crps_mdd_skill", np.nan), r.get("crps_mdd_skill_lo"), r.get("crps_mdd_skill_hi")
                ),
                "Brier (6 év.)": _num(r["brier_all"], 4),
                "BSS": _pct(r.get("brier_skill", np.nan)),
            }
        )
    return md(pd.DataFrame(rows))


def per_mix_table(per_mix: pd.DataFrame, family: str, H: int, models) -> str:
    g = per_mix[(per_mix["family"] == family) & (per_mix["H"] == H) & per_mix["model"].isin(models)]
    rows = []
    for _, r in _order(g).sort_values(["mix"], kind="stable").iterrows():
        rows.append(
            {
                "mélange (actions/RF)": r["mix"],
                "modèle": r["model"],
                "n": r["n_origins"],
                "couv. 80 % rend.": _ci(r["in80_ret"], r["in80_ret_lo"], r["in80_ret_hi"]),
                "rend. < p10": _pct(r["below_ret_q10"]),
                "MDD > p90": _pct(r["exc_mdd_q90"]),
                "P̄(MDD>20) prévu": _pct(r["pbar_mdd_gt_20"], 1),
                "fréq. obs. MDD>20": _pct(r["obar_mdd_gt_20"], 1),
                "Brier MDD>20": _num(r["brier_mdd_gt_20"], 3),
                "KS rend. p (déc. 0 / min)": (
                    f"{_num(r.get('ks_pit_ret_p', np.nan), 2)} / "
                    f"{_num(r.get('ks_pit_ret_pmin_offsets', np.nan), 2)} (n={r.get('ks_pit_ret_n', '')})"
                ),
            }
        )
    return md(pd.DataFrame(rows))


def write_tables(out: Path, pooled, per_mix, rel, rr, rec, hmm, hb, mono, dups, la, fits, ks=None) -> None:
    parts = ["# Tableaux générés (volet C)\n", "Valeurs en %, IC 90 % par bootstrap par blocs sur les origines.\n"]
    core = ["sbb", "sbb_ca", "iid", "iid_ca", "hmm_rs", "hmm_rs_ca", "hmm_rs_fl", "hist_emp", "stress_2022"]
    for fam in ("CAD77", "CAD71", "USD1926", "USD1953"):
        for H in (1, 3, 5, 10):
            if ((pooled["family"] == fam) & (pooled["H"] == H)).any():
                parts.append(f"\n## Agrégé {fam}, H = {H} ans\n")
                parts.append(pooled_table(pooled, fam, H, core))
    for fam in ("CAD77", "USD1926"):
        for H in (1, 3, 5, 10):
            parts.append(f"\n## Borne de bloc {fam}, H = {H}\n")
            parts.append(pooled_table(pooled, fam, H, ["sbb_L06", "sbb_L12", "sbb", "sbb_L48", "sbb_L96", "iid"]))
    for fam in ("CAD77", "USD1926"):
        for H in (5, 10):
            parts.append(f"\n## Par mélange {fam}, H = {H}\n")
            parts.append(per_mix_table(per_mix, fam, H, ["sbb", "sbb_ca", "hmm_rs", "hist_emp", "stress_2022"]))
    parts.append("\n## Mélanges risqués seulement (sans cash) : rendement sous p10 et MDD au-dessus de p90\n")
    sub = pooled[pooled["model"].isin(core)].copy()
    sub["rend<p10 (sans cash)"] = [
        _ci(a, b, c)
        for a, b, c in zip(sub["below_ret_q10_nc"], sub["below_ret_q10_nc_lo"], sub["below_ret_q10_nc_hi"], strict=True)
    ]
    sub["couv80 rend (sans cash)"] = [
        _ci(a, b, c) for a, b, c in zip(sub["in80_ret_nc"], sub["in80_ret_nc_lo"], sub["in80_ret_nc_hi"], strict=True)
    ]
    sub["MDD>p90"] = [
        _ci(a, b, c) for a, b, c in zip(sub["exc_mdd_q90"], sub["exc_mdd_q90_lo"], sub["exc_mdd_q90_hi"], strict=True)
    ]
    sub["Brier [IC]"] = [
        f"{a:.4f} [{b:.4f}; {c:.4f}]"
        for a, b, c in zip(sub["brier_all"], sub["brier_all_lo"], sub["brier_all_hi"], strict=True)
    ]
    parts.append(
        md(
            _order(sub)[
                ["family", "H", "model", "couv80 rend (sans cash)", "rend<p10 (sans cash)", "MDD>p90", "Brier [IC]"]
            ].sort_values(["family", "H"], kind="stable")
        )
    )
    for mixname in ("eq00_fi100", "eq100_fi00"):
        parts.append(f"\n## Mélange {mixname} : rendement sous p10, MDD au-dessus de p90, P(MDD>20) prévu / observé\n")
        g = per_mix[(per_mix["mix"] == mixname) & per_mix["model"].isin(["sbb", "sbb_ca", "hmm_rs", "iid", "hist_emp"])]
        g = g.assign(
            below=g["below_ret_q10"].map(_pct),
            exc=g["exc_mdd_q90"].map(_pct),
            p20=g["pbar_mdd_gt_20"].map(lambda x: _pct(x, 1)),
            o20=g["obar_mdd_gt_20"].map(lambda x: _pct(x, 1)),
        )
        parts.append(
            md(
                _order(g)[["family", "H", "model", "n_origins", "below", "exc", "p20", "o20"]].sort_values(
                    ["family", "H"], kind="stable"
                )
            )
        )
    if ks is not None and not ks.empty:
        parts.append("\n## KS du PIT (sous-ensemble non chevauchant), mélanges rejetés à 5 % sur 5 (hors cash)\n")
        parts.append(md(ks[ks["model"].isin(core)]))
    parts.append("\n## Fiabilité (événements MDD > 10/20/30 %, tous H, sans cash)\n")
    r = rel[(rel["events"] == "mdd") & rel["model"].isin(["sbb", "sbb_ca", "hmm_rs", "hist_emp"])].copy()
    r["mean_forecast"] = r["mean_forecast"].map(lambda x: _pct(x, 1))
    r["observed_freq"] = r["observed_freq"].map(lambda x: _pct(x, 1))
    parts.append(md(r))
    parts.append("\n## Fiabilité (événements perte cumulée > 0/10/20 %, tous H, sans cash)\n")
    r = rel[(rel["events"] == "loss") & rel["model"].isin(["sbb", "sbb_ca", "hmm_rs", "hist_emp"])].copy()
    r["mean_forecast"] = r["mean_forecast"].map(lambda x: _pct(x, 1))
    r["observed_freq"] = r["observed_freq"].map(lambda x: _pct(x, 1))
    parts.append(md(r))
    parts.append("\n## (i) Hausse des taux (fenêtres finissant <= 1981)\n")
    rr2 = rr[rr["model"].isin(["sbb", "sbb_ca", "hmm_rs", "hmm_rs_ca", "iid", "hist_emp"])].copy()
    for c in ("mean_pit_ret", "mean_pit_mdd"):
        rr2[c] = rr2[c].map(lambda x: _num(x, 2))
    for c in ("cov80_ret", "below_q10_ret", "exc_q90_mdd", "mean_y_ret", "mean_q10_ret", "mean_y_mdd", "mean_q90_mdd"):
        rr2[c] = rr2[c].map(lambda x: _pct(x, 1))
    parts.append(md(rr2))
    parts.append("\n## (i) 2021-2023\n")
    rec2 = rec[rec["model"].isin(["sbb", "sbb_ca", "hmm_rs", "hmm_rs_ca", "hist_emp", "stress_2022"])].copy()
    for c in (
        "y_ret",
        "ret_q05",
        "ret_q10",
        "y_mdd",
        "mdd_q90",
        "mdd_q95",
        "p_mdd_gt_10",
        "p_mdd_gt_20",
        "p_loss_gt_10",
    ):
        rec2[c] = rec2[c].map(lambda x: _pct(x, 1))
    for c in ("pit_ret", "pit_mdd"):
        rec2[c] = rec2[c].map(lambda x: _num(x, 3))
    parts.append(md(rec2))
    parts.append("\n## (ii) Longueur de bloc brute (Politis-White) aux origines\n")
    f = fits[fits["model"] == "sbb"].groupby("family")["block_raw"].describe()[["count", "min", "50%", "max"]]
    parts.append(md(f.reset_index().round(1)))
    parts.append("\n## (iii) HMM USD1926 / USD1953 (toute la fenêtre)\n")
    parts.append("```json\n" + __import__("json").dumps(hmm, indent=1) + "\n```\n")
    parts.append("\n## (v) Fenêtres historiques glissantes, perte max. > 20 %\n")
    hb2 = hb.copy()
    hb2["freq_mdd_gt_20"] = hb2["freq_mdd_gt_20"].map(lambda x: _pct(x, 1))
    hb2["max_mdd"] = hb2["max_mdd"].map(lambda x: _pct(x, 1))
    parts.append(md(hb2))
    if not mono.empty:
        parts.append("\n## (v) Monotonie de P(MDD > x) le long de la ligne actions/obligations (run de référence)\n")
        s = mono.groupby(["model_id", "family"]).agg(
            n=("monotone_increasing", "size"),
            non_monotone=("monotone_increasing", lambda x: int((~x).sum())),
            argmin_eq_median=("argmin_equity_share", "median"),
        )
        parts.append(md(s.reset_index()))
        ex = mono[(mono["metric"] == "p_mdd_gt_20") & (mono["H"] == 5) & (mono["family"] == "CAD77")]
        parts.append(
            "\nExemple CAD77, H = 5, P(MDD > 20 %) :\n\n"
            + md(ex[["model_id", "equity_shares", "values", "argmin_equity_share"]])
        )
    if dups:
        parts.append(f"\n## Doublons dans sensitivity_block_length.csv du run de référence\n\n{dups}\n")
    parts.append("\n## Look-ahead (vraies données, mois postérieurs corrompus)\n")
    parts.append(md(pd.DataFrame(la)))
    (out / "tables.md").write_text("\n".join(parts), encoding="utf-8")
