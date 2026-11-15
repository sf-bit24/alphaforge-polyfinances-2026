"""Walk-forward of the withdrawal-sustainability choice (USD 1926+): at each annual start t, choose the constant mix
with the best worst-case PWR (SAFEMAX) over windows COMPLETED before t (start + H <= t), then evaluate it on the
window starting at t (out of sample). Compared with the hindsight best mix (ORACLE, hindsight=True) and fixed mixes.
SIMULATION ONLY."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np

from common import era_data, port_returns, pwr_all, write_trace
from swr import eras


def main():
    E = eras()[0]
    R, infl = E["R"]
    iv = infl.values
    out = {}
    for H in (30, 40):
        n = 12 * H
        names = list(E["pf"])
        P = np.array([pwr_all(port_returns(R, E["pf"][k]), iv, n) for k in names])
        jan = [i for i in range(P.shape[1]) if R.index[i].month == 1]
        rows = []
        for i in jan:
            past = [j for j in range(P.shape[1]) if j + n <= i]
            if len(past) < 12:          # at least 12 completed monthly windows
                continue
            k = int(np.argmax(P[:, past].min(1)))
            rows.append({"start": str(R.index[i].date()), "chosen": names[k], "pwr_chosen": float(P[k, i]),
                         "pwr_oracle": float(P[:, i].max()), "oracle": names[int(P[:, i].argmax())],
                         "pwr_eq60": float(P[names.index("eq60_UST_5Y"), i]), "pwr_eq100": float(P[names.index("eq100_UST_TBILL"), i]),
                         "n_past_windows": len(past)})
        pc = np.array([r["pwr_chosen"] for r in rows])
        out[str(H)] = {"n_oos": len(rows), "first": rows[0]["start"] if rows else None, "last": rows[-1]["start"] if rows else None,
                       "choices": dict(Counter(r["chosen"] for r in rows)), "oracle_choices": dict(Counter(r["oracle"] for r in rows)),
                       "oos_pwr_min": float(pc.min()), "oos_pwr_p10": float(np.quantile(pc, .1)),
                       "oos_fail_3.5": float(np.mean(pc < .035)), "oos_fail_4.0": float(np.mean(pc < .04)),
                       "mean_gap_oracle_minus_chosen": float(np.mean([r["pwr_oracle"] - r["pwr_chosen"] for r in rows])),
                       "eq60_min_same_starts": float(min(r["pwr_eq60"] for r in rows)),
                       "eq100_min_same_starts": float(min(r["pwr_eq100"] for r in rows)), "rows": rows}
        print(H, {k: v for k, v in out[str(H)].items() if k != "rows"})
    print(write_trace("wf_swr", out, {"doc": __doc__}))


if __name__ == "__main__":
    main()
