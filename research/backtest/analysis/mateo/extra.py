"""Extra stage-B numbers: walk-forward with breach filter, specific signal correlations, robust-strategy weights.
Writes results/mateo_analysis/extra.json. SIMULATION ONLY."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa
import numpy as np, pandas as pd
import lib
from engine.validation import walk_forward, robust_table

out = {"walk_forward_breach025": [], "corr": [], "weights": []}
for era in ("usd_long", "usd_gold", "cad"):
    for var in ("esg", "base"):
        for mode in ("rolling", "non_overlapping"):
            tp = lib.trace_path(f"mateo_{era}_{var}", mode, 10, "1")
            df = lib.rows(tp)
            for mbr in (0.25, None):
                wf = walk_forward(df, 0.10, mbr, 3)
                if len(wf):
                    out["walk_forward_breach025"].append({"era": era, "variant": var, "mode": mode, "max_breach_rate": mbr,
                        "n_oos": len(wf), "mean_oos": wf.chosen_score.mean(), "p10_oos": wf.chosen_score.quantile(0.1),
                        "oos_shortfall": float(wf.chosen_missed_target.astype(float).mean()),
                        "mean_oracle_gap": float((wf.oracle_score - wf.chosen_score).mean()),
                        "mean_gap_best_expost": float((wf.best_ex_post_score - wf.chosen_score).mean()),
                        "chosen": wf.chosen.value_counts().to_dict(), "trace": tp})
            if var == "esg" and mode == "rolling":
                ex = df[~df.hindsight]
                for st in ("risk_parity_iv36", "static_eq60_gold", "dual_mom12_top2", "static_eq60"):
                    g = ex[ex.strategy == st]
                    if len(g):
                        W = pd.DataFrame(list(g.avg_weights)).mean()
                        out["weights"].append({"era": era, "strategy": st, "trace": tp,
                                               "avg_weights": {k: round(float(v), 4) for k, v in W.items() if v > 0.005},
                                               "vol_median": g.volatility.median(), "maxdd_median": g.max_drawdown.median(),
                                               "cvar5_median": g.cvar_5.median(), "recovery_p90": g.recovery_months.quantile(0.9),
                                               "real_median": g.ann_real_return.median(), "real_p10": g.ann_real_return.quantile(0.1),
                                               "real_worst": g.ann_real_return.min(),
                                               "oracle_gap_median": float((df[df.hindsight].set_index('window').ann_real_return
                                                                           - g.set_index('window').ann_real_return).median())})
C = pd.read_csv(lib.OUT / "reverse_corr.csv")
sel = C[(C.universe == "classes") & C.signal.isin(["cape", "mom12_us", "trend10_us", "slope_us", "infl12_us", "long_us", "real_short_us", "d_long_12m_us"]) & C.target.isin(["equity_total", "bonds_total", "duration_long_share", "gold"])]
out["corr"] = sel.to_dict(orient="records")
(lib.OUT / "extra.json").write_text(json.dumps(out, indent=1, default=str))
pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_rows", 200)
print(pd.DataFrame(out["walk_forward_breach025"]).drop(columns=["trace"]).to_string(float_format=lambda x: f"{x:.4f}"))
for w in out["weights"]:
    print(w["era"], w["strategy"], {k: round(v, 4) if isinstance(v, float) else v for k, v in w.items() if k not in ("trace",)})
print(sel.pivot_table(index=["target", "signal"], columns=["era", "mode"], values="spearman").to_string(float_format=lambda x: f"{x:.2f}"))
