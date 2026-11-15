"""Faisabilité de la table de risque (F1) par niveau : optimiseur F2 puis contrôle du Judge F4.

Usage :
    cd app/agents
    uv run --group finance python -I scripts/finance/feasibility_levels.py <risk_levels.yaml> <expand.py> [as_of]

Les limites viennent de la fonction ``emit`` du script d'expansion de F1 (non recopiée ici).
La limite conditionnelle ``risk.cdar_m`` (biais d'aversion aux pertes) est testée à part.
SIMULATION SEULEMENT.
"""
from __future__ import annotations

import contextlib
import io
import os
import runpy
import sys
from datetime import UTC, datetime

import yaml

from alphaforge.finance.contracts import ExposureOverride, HistoryProxy, PolicySpec
from alphaforge.finance.portfolio import check, optimize
from alphaforge.finance.portfolio._engine import bt_data

LEVELS = ["N0", "N1", "N2", "N3", "N4", "N5"]


def load_emit(yaml_path: str, expand_path: str, repo_root: str):
    # Compatibilité : les scripts de F1 écrits avant l'intégration importent « contracts.policy ».
    import alphaforge.finance.contracts as _c
    import alphaforge.finance.contracts.policy as _cp
    sys.modules.setdefault("contracts", _c)
    sys.modules.setdefault("contracts.policy", _cp)
    os.environ["RISK_YAML"], os.environ["AF_REPO"] = yaml_path, repo_root
    with contextlib.redirect_stdout(io.StringIO()):
        return runpy.run_path(expand_path)["emit"]


def real_universe() -> list[str]:
    cat = bt_data.load_assets()
    proxies = {"bond_synthetic", "equity_us", "equity_ca", "cash", "sector_us"}
    return [a for a in cat.index if cat.at[a, "asset_class"] not in proxies and a != "GOLD"]


def build_policy(level: str, limits, Y: dict, universe: list[str]) -> PolicySpec:
    ov = {a: {t: ExposureOverride(value=v["value"], source=v["source"], status=v.get("status", "HYPOTHESE"))
              for t, v in tags.items()} for a, tags in (Y.get("exposure_overrides") or {}).items() if a in universe}
    hp = {a: HistoryProxy(proxy=v["proxy"], source=v["source"])
          for a, v in (Y.get("history_proxies") or {}).items() if a in universe}
    delta = Y["satellites"]["crypto"]["delta"]
    lb = {a: delta for a in Y.get("no_proxy") or [] if a in universe}
    d = Y.get("policy_defaults") or {}
    return PolicySpec(policy_id=f"feasibility-{level}", profile_id="table", profile_version=1,
                      created_utc=datetime.now(UTC), universe=universe, limits=limits,
                      exposure_overrides=ov, history_proxies=hp, loss_bounds=lb,
                      loss_bounds_source="risk_levels.yaml satellites.crypto.delta" if lb else None,
                      lookback_months=d.get("lookback_months", 120), cvar_beta=d.get("cvar_beta", 0.95),
                      risk_measure=d.get("risk_measure", "CVAR"), objective=d.get("objective", "min_risk"))


def run(yaml_path: str, expand_path: str, as_of: str, repo_root: str) -> list[dict]:
    Y = yaml.safe_load(open(yaml_path))
    emit = load_emit(yaml_path, expand_path, repo_root)
    uni = real_universe()
    rows = []
    for level in LEVELS:
        for variant, drop in (("base", {"risk.cdar_m"}), ("avec_cdar", set())):
            lims = [lim for lim in emit(level) if lim.rule_id not in drop]
            p = build_policy(level, lims, Y, uni)
            res = optimize(p, as_of)
            row = {"level": level, "variant": variant, "status": res.status, "window": res.window,
                   "infeasible_rules": res.infeasible_rules, "warnings": res.warnings}
            if res.status == "optimal":
                rep = check(res.weights, p, as_of)
                eq = sum(x for a, x in res.weights.items()
                         if bt_data.load_assets().at[a, "asset_class"] in ("etf_equity", "equity_single", "crypto"))
                row.update(verdict=rep.verdict, blocking=list(rep.blocking_violations), equity=round(eq, 3),
                           top={a: round(x, 3) for a, x in sorted(res.weights.items(), key=lambda t: -t[1])[:6]},
                           measured={c.rule_id: next(f.value for f in rep.facts if f.fact_id == c.value_fact_id)
                                     for c in rep.checks if c.rule_id.startswith("risk.")})
            rows.append(row)
    return rows


if __name__ == "__main__":
    yp, ep = sys.argv[1], sys.argv[2]
    as_of = sys.argv[3] if len(sys.argv) > 3 else "2026-09-30"
    root = os.path.abspath(".")
    for r in run(yp, ep, as_of, root):
        print(f"\n== {r['level']} ({r['variant']}) : {r['status']}  fenêtre={r['window']}")
        if r["status"] != "optimal":
            print("   règles en cause :", r["infeasible_rules"])
            continue
        print(f"   Judge : {r['verdict']}  bloquantes={r['blocking']}  actions={r['equity']}")
        print("   principaux poids :", r["top"])
        print("   mesures :", {k: round(v, 4) for k, v in r["measured"].items()})
