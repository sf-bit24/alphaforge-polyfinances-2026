"""Amira selection rule applied to existing engine traces (engine.validation functions, no new simulation):
  robust choice = best 10th-percentile real return among strategies whose drawdown-budget breach rate is
  <= 10 % (consistent with the budget's definition: the p90 drawdown of the reference policy).
Also recomputes the walk-forward under the same rule.

    uv run --group finance python -I analysis/amira/select_amira.py <trace.json> [...]
Writes results/amira_analysis/<profile>__<run_id>_select.json. SIMULATION ONLY.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amira_common import RESULTS, rel, write_json  # noqa: E402
from alphaforge.finance.backtest.validation import robust_table, walk_forward  # noqa: E402

MAX_BREACH = 0.10


def main(paths):
    for p in paths:
        p = Path(p).resolve()
        tr = json.loads(p.read_text())
        rows = pd.DataFrame(tr["results"])
        rows["missed_target"] = rows["missed_target"].astype(object)
        rt = robust_table(rows, 0.10, MAX_BREACH)
        wf = walk_forward(rows, 0.10, MAX_BREACH, 3)
        summ = {"rule": f"max score_p10, breach_rate <= {MAX_BREACH}", "robust_choice": rt.index[0],
                "n_eligible": int(rt["eligible"].sum()),
                "wf_n": int(len(wf)), "wf_mean": float(wf["chosen_score"].mean()) if len(wf) else None,
                "wf_p10": float(wf["chosen_score"].quantile(0.1)) if len(wf) else None,
                "wf_worst": float(wf["chosen_score"].min()) if len(wf) else None,
                "wf_oracle_gap_mean": float((wf["oracle_score"] - wf["chosen_score"]).mean()) if len(wf) else None,
                "wf_best_ex_post_gap_mean": float((wf["best_ex_post_score"] - wf["chosen_score"]).mean()) if len(wf) else None,
                "wf_choices": wf["chosen"].value_counts().to_dict() if len(wf) else {}}
        out = {"trace": rel(p), "summary": summ, "robust": rt.reset_index().to_dict(orient="records"),
               "walk_forward": wf.to_dict(orient="records")}
        dest = RESULTS / "amira_analysis" / f"{tr['profile']['id']}__{tr['run_id']}_select.json"
        print(write_json(out, dest, [rel(p)]))
        print(json.dumps(summ))
        print(rt.head(6)[["score_p10", "score_median", "max_drawdown_worst", "breach_rate", "eligible"]].round(4).to_string())


if __name__ == "__main__":
    main(sys.argv[1:])
