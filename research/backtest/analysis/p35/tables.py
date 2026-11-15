"""Persona 35 - markdown tables for reports/p35-denise.md, read from the latest traces (no new number invented).
Writes results/p35_analysis/tables.md and tables.json. SIMULATION ONLY."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd

import common as C
from engine import metrics as M
from engine.data import load_inflation

md = []


def T(trace: Path):
    t = json.loads(trace.read_text())
    return t, pd.DataFrame(t["results"])


def wfmt(w: dict, thr=0.03) -> str:
    return ", ".join(f"{k} {v:.2f}" for k, v in sorted(w.items(), key=lambda x: -x[1]) if v > thr)


def per_window(trace: Path, chosen: str, extra: list[str] = ()):
    t, d = T(trace)
    md.append(f"\n### {trace.parent.name}/{trace.name}  (choix robuste du run : `{t['summary']['robust_choice']}`)\n")
    md.append(f"| fenêtre | ORACLE, poids (> 3 %) | ORACLE richesse réelle finale | ORACLE maxDD | meilleure ex-ante (a posteriori) | sa richesse réelle | {chosen} richesse réelle | {chosen} maxDD | {chosen} réel ann. (panier) | " + " | ".join(f"{e} richesse" for e in extra) + " |")
    md.append("|" + "---|" * (9 + len(extra)))
    for w, g in d.groupby("window", sort=False):
        o = g[g.hindsight].iloc[0] if g.hindsight.any() else None
        ex = g[~g.hindsight]
        b = ex.loc[ex.score.idxmax()]
        c = ex[ex.strategy == chosen].iloc[0]
        cells = [w, wfmt(o.avg_weights) if o is not None else "—", f"{o.final_real_wealth:.3f}" if o is not None else "—",
                 f"{o.max_drawdown:.3f}" if o is not None else "—", b.strategy, f"{b.final_real_wealth:.3f}",
                 f"{c.final_real_wealth:.3f}", f"{c.max_drawdown:.3f}", f"{c.ann_real_return:.4f}"]
        for e in extra:
            ee = ex[ex.strategy == e].iloc[0]
            cells.append(f"{ee.final_real_wealth:.3f}")
        md.append("| " + " | ".join(cells) + " |")


def robust(trace: Path, n=12):
    t, d = T(trace)
    r = pd.DataFrame(t["robust_selection"]).set_index("strategy")
    ex = d[~d.hindsight]
    fw = ex.groupby("strategy")["final_real_wealth"].agg(lambda s: s.quantile(.1))
    fwmin = ex.groupby("strategy")["final_real_wealth"].min()
    md.append(f"\n**{trace.parent.name}/{trace.name}** — {len(t['windows'])} fenêtres\n")
    md.append("| rang | stratégie | p10 score | médiane score | richesse réelle finale p10 | pire richesse réelle | pire maxDD | taux de violation | P(sous la cible) | éligible |")
    md.append("|---|---|---|---|---|---|---|---|---|---|")
    for s, x in r.head(n).iterrows():
        md.append(f"| {int(x['rank'])} | {s} | {x.score_p10:.3f} | {x.score_median:.3f} | {fw[s]:.3f} | {fwmin[s]:.3f} | "
                  f"{x.max_drawdown_worst:.3f} | {x.breach_rate:.3f} | {x.shortfall_prob:.3f} | {x.eligible} |")
    return r


def bnc_rank(trace: Path):
    t, d = T(trace)
    r = pd.DataFrame(t["robust_selection"]).set_index("strategy")
    b = r[r.index.str.startswith("bnc")]
    return {s: {"rank": int(x["rank"]), "score_p10": float(x.score_p10), "breach_rate": float(x.breach_rate),
                "max_drawdown_worst": float(x.max_drawdown_worst), "eligible": bool(x.eligible)} for s, x in b.iterrows()}


def oracle_ranges(trace: Path) -> dict:
    t = json.loads(trace.read_text())
    W = pd.DataFrame([o["weights"] for o in t["oracle"]]).fillna(0)
    return {a: {"p10": float(W[a].quantile(.1)), "median": float(W[a].median()), "p90": float(W[a].quantile(.9))}
            for a in W.columns}


def two_currency(trace: Path, strategies: list[str]):
    """Re-deflate the engine portfolio returns (from the windows' weights we cannot) -> recompute from the
    trace rows: we have ann_return (nominal CAD); real in CAD / USD use the CPI and FX of the same months."""
    t, d = T(trace)
    rows = []
    fx = C.fx_monthly()
    for s in strategies:
        x = d[(d.strategy == s) & (~d.hindsight)].iloc[0]
        n = int(x.n_months)
        st, en = pd.Timestamp(x.start) + pd.offsets.MonthEnd(0), pd.Timestamp(x.end) + pd.offsets.MonthEnd(0)
        pc = load_inflation("CAD").loc[st:en].values
        pu = load_inflation("USD").loc[st:en].values
        f = (fx / fx.shift(1) - 1).loc[st:en].values
        nom = (1 + x.ann_return) ** (n / 12)
        cad_real = (nom / np.prod(1 + pc)) ** (12 / n) - 1
        usd_nom = (nom / np.prod(1 + f)) ** (12 / n) - 1
        usd_real = (nom / np.prod(1 + f) / np.prod(1 + pu)) ** (12 / n) - 1
        rows.append({"strategy": s, "nominal_cad": float(x.ann_return), "real_cad_cpi_ca": float(cad_real),
                     "nominal_usd": float(usd_nom), "real_usd_cpi_us": float(usd_real),
                     "real_basket_s05": float(x.ann_real_return), "max_drawdown_cad": float(x.max_drawdown),
                     "final_real_wealth_basket_with_4pct": float(x.final_real_wealth)})
    return rows


if __name__ == "__main__":
    out = {}
    tr15 = C.latest("p35_B_cad", "*_rolling_h15.json")
    trn15 = C.latest("p35_B_cad", "*_non_overlapping_h15.json")
    tr20 = C.latest("p35_B_cad", "*_rolling_h20.json")
    trn20 = C.latest("p35_B_cad", "*_non_overlapping_h20.json")
    t15 = json.loads(tr15.read_text())
    chosen = t15["summary"]["robust_choice"]
    md.append("## Tableaux par fenêtre (poche B, CAD 1977+, panier s = 0,5, retraits 4 %)")
    per_window(trn15, chosen, ["bnc_pondere", "bnc_equilibre", "e40_u50"])
    per_window(trn20, chosen, ["bnc_pondere", "bnc_equilibre", "e40_u50"])
    md.append("\n## Sélection robuste")
    for tr in [tr15, trn15, tr20, trn20, C.latest("p35_B_cad_s03", "*h15.json"), C.latest("p35_B_cad_s07", "*h15.json"),
               C.latest("p35_B_cad_h10", "*h10.json"), C.latest("p35_B_usd1926", "*_rolling_h15.json"),
               C.latest("p35_B_usd1926", "*_non_overlapping_h15.json")]:
        robust(tr, 10)
        out[f"bnc_{tr.parent.name}_{tr.stem}"] = bnc_rank(tr)
    md.append("\n## Walk-forward")
    for tr in [tr15, tr20, C.latest("p35_B_cad_h10", "*h10.json"), C.latest("p35_B_usd1926", "*_rolling_h15.json")]:
        t = json.loads(tr.read_text())
        wf = pd.DataFrame(t["walk_forward"])
        if len(wf):
            md.append(f"- `{tr.parent.name}/{tr.name}` : {t['summary']['walk_forward']} ; choix : {wf.chosen.value_counts().to_dict()}")
    out["oracle_ranges_B15"] = oracle_ranges(tr15)
    out["oracle_ranges_B20"] = oracle_ranges(tr20)
    out["oracle_ranges_A"] = oracle_ranges(C.latest("p35_A_usd", "*_rolling_h0.5.json"))
    md.append("\n## Plages des poids ORACLE (p10 / médiane / p90)")
    for k in ("oracle_ranges_B15", "oracle_ranges_B20", "oracle_ranges_A"):
        md.append(f"- {k} : " + "; ".join(f"{a} {v['p10']:.2f}/{v['median']:.2f}/{v['p90']:.2f}" for a, v in out[k].items()))
    trt = C.latest("p35_B_tickers", "*.json")
    tt, dt_ = T(trt)
    md.append(f"\n## Tickers réels `{trt.parent.name}/{trt.name}`")
    names = [chosen if chosen in set(dt_.strategy) else "e40_u50_gold15", "e40_u50", "e40_u50_gold10", "e40_u50_def10_gold10",
             "bnc_prudent", "bnc_conservateur", "bnc_pondere", "bnc_equilibre", "bnc_croissance", "bnc_actions",
             "bnc_pondere_usdfi", "e40_u0", "e40_u100", "e40_u50_cash10"]
    names = [n for n in dict.fromkeys(names) if n in set(dt_.strategy)]
    rows = two_currency(trt, names)
    out["tickers_two_currency"] = rows
    md.append("| stratégie | nominal CAD | réel CAD (IPC CA) | nominal USD | réel USD (CPI US) | réel panier s=0,5 | maxDD CAD | richesse réelle finale (retraits 4 %) |")
    md.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        md.append(f"| {r['strategy']} | {r['nominal_cad']:.4f} | {r['real_cad_cpi_ca']:.4f} | {r['nominal_usd']:.4f} | "
                  f"{r['real_usd_cpi_us']:.4f} | {r['real_basket_s05']:.4f} | {r['max_drawdown_cad']:.3f} | {r['final_real_wealth_basket_with_4pct']:.3f} |")
    o = dt_[dt_.hindsight].iloc[0]
    md.append(f"\nORACLE tickers : {wfmt(o.avg_weights)} ; richesse réelle {o.final_real_wealth:.3f} ; maxDD {o.max_drawdown:.3f}")
    (C.OUT / "tables.md").write_text("\n".join(md))
    p = C.write_trace("tables", out, {"traces": [str(x) for x in (tr15, trn15, tr20, trn20, trt)]}, "tables.py")
    print("\n".join(md))
    print(json.dumps(C._clean({k: v for k, v in out.items() if k.startswith("bnc")}), indent=0)[:5000])
