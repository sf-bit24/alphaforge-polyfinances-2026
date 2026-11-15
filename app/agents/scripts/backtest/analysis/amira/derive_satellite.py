"""Derive single-name and crypto caps from the satellite sweeps (proposals for the team to validate).

Rule R-IDIO (same rule for any concentrated satellite, written before reading the outputs):
  b = idiosyncratic loss budget = 10 % of the derived drawdown budget (dd_budget, derived_thresholds.json).
  Diversifiable risk is not rewarded on average, so a single satellite may only 'spend' a small fraction
  of the drawdown the core is allowed to take. 10 % is a CONVENTION -> sensitivity b in {2, 4, 6, 8} points.
  cap = largest k of the grid such that, in EVERY window and for EVERY satellite of the family
        (all tech names / both crypto baskets) and every horizon, max drawdown(k) - max drawdown(0) <= b.
Second rule R-RISK (crypto only): the crypto pocket may not carry a larger share of portfolio risk (Euler
  contribution, full sample) than the riskiest single name at the single-name cap. Final crypto proposal =
  min(R-IDIO with disciplined monthly rebalancing, R-RISK), per basket; R-IDIO with annual rebalancing reported.
Writes results/amira_sat_single/derived_single_name_cap.json and results/amira_sat_crypto*/derived_crypto_cap.json.
SIMULATION ONLY.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amira_common import BT, RESULTS, write_json  # noqa: E402

DD = json.loads((RESULTS / "amira_sweep_tech" / "derived_thresholds.json").read_text())["result"]["derived"]["dd_budget"]
BUDGETS = [0.02, 0.04, 0.06, 0.08]


def caps(summary: dict, budget: float):
    per = {}
    for key, v in summary.items():
        if "increments" not in v:
            continue
        t = pd.DataFrame(v["increments"]).set_index("k").sort_index()
        ok = t["d_maxdd_worst"] <= budget + 1e-12
        # largest k such that all smaller k are also ok (monotone admissible prefix)
        kmax = 0.0
        for k, good in ok.items():
            if not good:
                break
            kmax = k
        per[key] = {"k_max": kmax, "n_windows": v["n_windows"], "trace": v["trace"]}
    binding = min(per, key=lambda k: per[k]["k_max"]) if per else None
    return {"cap": per[binding]["k_max"] if binding else None, "binding": binding, "per_satellite": per}


def run(kind: str, folders: list[str]):
    out = {"rule": __doc__.split("Rule R-IDIO")[1].split("Writes")[0].strip(), "dd_budget": DD,
           "budget_main": round(0.1 * DD, 4), "variants": {}}
    inputs = []
    for f in folders:
        p = RESULTS / f / f"sat_{kind}_summary.json"
        if not p.exists():
            continue
        inputs.append(p.relative_to(BT).as_posix())
        s = json.loads(p.read_text())["result"]
        out["variants"][f] = {f"b={b:.2f}": caps(s, b) for b in BUDGETS}
        out["variants"][f]["main"] = caps(s, 0.1 * DD)
        out["variants"][f]["risk_share"] = {k: v for k, v in s.items() if k.endswith("risk_contrib")}
    name = "derived_single_name_cap.json" if kind == "single" else "derived_crypto_cap.json"
    path = write_json(out, RESULTS / folders[0] / name, inputs)
    for f, v in out["variants"].items():
        print(kind, f, {b: (c["cap"], c["binding"]) for b, c in v.items() if b != "risk_share"})
    print(path)


def crypto_proposal():
    sn = json.loads((RESULTS / "amira_sat_single" / "derived_single_name_cap.json").read_text())["result"]
    cr = json.loads((RESULTS / "amira_sat_crypto" / "derived_crypto_cap.json").read_text())["result"]
    cap_n = sn["variants"]["amira_sat_single"]["main"]["cap"]
    rs = sn["variants"]["amira_sat_single"]["risk_share"]
    ref = max(v[f"{cap_n:.3f}"]["sat_risk_share"] for v in rs.values())
    ref_name = max(rs, key=lambda k: rs[k][f"{cap_n:.3f}"]["sat_risk_share"])
    out = {"single_name_cap": cap_n, "risk_share_ref": ref, "risk_share_ref_name": ref_name, "baskets": {}}
    mon = cr["variants"]["amira_sat_crypto_monthly"]["main"]["per_satellite"]
    ann = cr["variants"]["amira_sat_crypto"]["main"]["per_satellite"]
    for b in ("BTC", "BTC_ETH"):
        k_dd_m = min(v["k_max"] for k, v in mon.items() if k.startswith(b + "_h") and not (b == "BTC" and "ETH" in k))
        k_dd_a = min(v["k_max"] for k, v in ann.items() if k.startswith(b + "_h") and not (b == "BTC" and "ETH" in k))
        shares = cr["variants"]["amira_sat_crypto"]["risk_share"][f"{b}_risk_contrib"]
        k_rs = max([float(k) for k, v in shares.items() if k[0] == "0" and v["sat_risk_share"] <= ref + 1e-12])
        out["baskets"][b] = {"k_dd_monthly": k_dd_m, "k_dd_annual": k_dd_a, "k_risk_share": k_rs,
                             "proposal_monthly_or_bands": min(k_dd_m, k_rs), "proposal_annual": min(k_dd_a, k_rs)}
    print(json.dumps(out, indent=1))
    print(write_json(out, RESULTS / "amira_sat_crypto" / "crypto_proposal.json",
                     ["results/amira_sat_single/derived_single_name_cap.json",
                      "results/amira_sat_crypto/derived_crypto_cap.json"]))


if __name__ == "__main__":
    run("single", ["amira_sat_single"])
    run("crypto", ["amira_sat_crypto", "amira_sat_crypto_monthly"])
    crypto_proposal()
