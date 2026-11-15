"""Poids des lentilles d'explication (timeline, risk, diversity, constraints) depuis emphasis.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

EMPHASIS_FILE = Path(__file__).with_name("emphasis.yaml")
LENSES = ("timeline", "risk", "diversity", "constraints")
_OPERATORS = {
    "is_true": lambda signal, _threshold: bool(signal),
    "lt": lambda signal, threshold: signal < threshold,
    "le": lambda signal, threshold: signal <= threshold,
    "gt": lambda signal, threshold: signal > threshold,
    "ge": lambda signal, threshold: signal >= threshold,
}


def load_rules(path: str | Path | None = None) -> dict:
    with open(path or EMPHASIS_FILE, encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def compute_emphasis(
    signals: dict[str, Any], path: str | Path | None = None
) -> tuple[dict[str, float], list[str], list[dict]]:
    """Retourne (poids normalises, ids des regles declenchees, trace)."""
    config = load_rules(path)
    version = config["version"]
    raw_weights = {lens: float(config["base"][lens]) for lens in LENSES}
    fired, trace = [], []
    for index, rule in enumerate(config["rules"]):
        if rule["lens"] not in raw_weights:
            raise ValueError(f"emphasis.yaml : lentille inconnue {rule['lens']}")
        if rule["signal"] not in signals:
            raise KeyError(f"emphasis.yaml : signal inconnu {rule['signal']}")
        signal = signals[rule["signal"]]
        is_triggered = signal is not None and _OPERATORS[rule["op"]](signal, rule.get("value"))
        if is_triggered:
            raw_weights[rule["lens"]] += float(rule["bonus"])
            fired.append(rule["id"])
            trace.append(
                {
                    "rule": f"emphasis.{rule['id']}",
                    "inputs": {rule["signal"]: signal, "op": rule["op"], "value": rule.get("value")},
                    "output": {rule["lens"]: float(rule["bonus"])},
                    "yaml_path": f"emphasis.yaml@{version}#rules[{index}]",
                }
            )
    total = sum(raw_weights.values())
    weights = {lens: raw_weights[lens] / total for lens in LENSES}
    trace.append(
        {
            "rule": "emphasis.normalize",
            "inputs": raw_weights,
            "output": weights,
            "yaml_path": f"emphasis.yaml@{version}#base",
        }
    )
    return weights, fired, trace
