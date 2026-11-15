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
DEFAULT_AS_OF = "2026-09-30"
# Classes du catalogue qui servent d'historique de remplacement : jamais dans un portefeuille réel.
PROXY_CLASSES = {"bond_synthetic", "equity_us", "equity_ca", "cash", "sector_us"}
RISKY_CLASSES = ("etf_equity", "equity_single", "crypto")
LARGEST_WEIGHTS_SHOWN = 6


def load_emit(yaml_path: str, expand_path: str, repo_root: str):
    # Compatibilité : les scripts de F1 écrits avant l'intégration importent « contracts.policy ».
    import alphaforge.finance.contracts as contracts_package
    import alphaforge.finance.contracts.policy as policy_module

    sys.modules.setdefault("contracts", contracts_package)
    sys.modules.setdefault("contracts.policy", policy_module)
    os.environ["RISK_YAML"], os.environ["AF_REPO"] = yaml_path, repo_root
    with contextlib.redirect_stdout(io.StringIO()):
        return runpy.run_path(expand_path)["emit"]


def real_universe() -> list[str]:
    catalog = bt_data.load_assets()
    return [
        asset_id
        for asset_id in catalog.index
        if catalog.at[asset_id, "asset_class"] not in PROXY_CLASSES and asset_id != "GOLD"
    ]


def build_policy(level: str, limits, risk_levels: dict, universe: list[str]) -> PolicySpec:
    exposure_overrides = {
        asset_id: {
            tag: ExposureOverride(value=entry["value"], source=entry["source"], status=entry.get("status", "HYPOTHESE"))
            for tag, entry in tags.items()
        }
        for asset_id, tags in (risk_levels.get("exposure_overrides") or {}).items()
        if asset_id in universe
    }
    history_proxies = {
        asset_id: HistoryProxy(proxy=entry["proxy"], source=entry["source"])
        for asset_id, entry in (risk_levels.get("history_proxies") or {}).items()
        if asset_id in universe
    }
    crypto_delta = risk_levels["satellites"]["crypto"]["delta"]
    loss_bounds = {asset_id: crypto_delta for asset_id in risk_levels.get("no_proxy") or [] if asset_id in universe}
    defaults = risk_levels.get("policy_defaults") or {}
    return PolicySpec(
        policy_id=f"feasibility-{level}",
        profile_id="table",
        profile_version=1,
        created_utc=datetime.now(UTC),
        universe=universe,
        limits=limits,
        exposure_overrides=exposure_overrides,
        history_proxies=history_proxies,
        loss_bounds=loss_bounds,
        loss_bounds_source="risk_levels.yaml satellites.crypto.delta" if loss_bounds else None,
        lookback_months=defaults.get("lookback_months", 120),
        cvar_beta=defaults.get("cvar_beta", 0.95),
        risk_measure=defaults.get("risk_measure", "CVAR"),
        objective=defaults.get("objective", "min_risk"),
    )


def _risky_weight(weights: dict[str, float]) -> float:
    catalog = bt_data.load_assets()
    return sum(weight for asset_id, weight in weights.items() if catalog.at[asset_id, "asset_class"] in RISKY_CLASSES)


def _largest_weights(weights: dict[str, float]) -> dict[str, float]:
    ranked = sorted(weights.items(), key=lambda pair: -pair[1])
    return {asset_id: round(weight, 3) for asset_id, weight in ranked[:LARGEST_WEIGHTS_SHOWN]}


def _measured_risks(report) -> dict[str, float]:
    """Valeur mesurée par le Judge pour chaque limite de risque."""
    return {
        risk_check.rule_id: next(fact.value for fact in report.facts if fact.fact_id == risk_check.value_fact_id)
        for risk_check in report.checks
        if risk_check.rule_id.startswith("risk.")
    }


def _judged(weights: dict[str, float], policy: PolicySpec, as_of: str) -> dict:
    report = check(weights, policy, as_of)
    return {
        "verdict": report.verdict,
        "blocking": list(report.blocking_violations),
        "equity": round(_risky_weight(weights), 3),
        "top": _largest_weights(weights),
        "measured": _measured_risks(report),
    }


def run(yaml_path: str, expand_path: str, as_of: str, repo_root: str) -> list[dict]:
    with open(yaml_path) as handle:
        risk_levels = yaml.safe_load(handle)
    emit = load_emit(yaml_path, expand_path, repo_root)
    universe = real_universe()
    rows = []
    for level in LEVELS:
        for variant, dropped_rules in (("base", {"risk.cdar_m"}), ("avec_cdar", set())):
            limits = [limit for limit in emit(level) if limit.rule_id not in dropped_rules]
            policy = build_policy(level, limits, risk_levels, universe)
            result = optimize(policy, as_of)
            row = {
                "level": level,
                "variant": variant,
                "status": result.status,
                "window": result.window,
                "infeasible_rules": result.infeasible_rules,
                "warnings": result.warnings,
            }
            if result.status == "optimal":
                row.update(_judged(result.weights, policy, as_of))
            rows.append(row)
    return rows


def main() -> None:
    yaml_path, expand_path = sys.argv[1], sys.argv[2]
    as_of = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_AS_OF
    for row in run(yaml_path, expand_path, as_of, os.path.abspath(".")):
        print(f"\n== {row['level']} ({row['variant']}) : {row['status']}  fenêtre={row['window']}")
        if row["status"] != "optimal":
            print("   règles en cause :", row["infeasible_rules"])
            continue
        print(f"   Judge : {row['verdict']}  bloquantes={row['blocking']}  actions={row['equity']}")
        print("   principaux poids :", row["top"])
        print("   mesures :", {rule_id: round(value, 4) for rule_id, value in row["measured"].items()})


if __name__ == "__main__":
    main()
