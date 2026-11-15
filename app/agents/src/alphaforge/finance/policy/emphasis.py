"""Poids des lentilles d'explication (timeline, risk, diversity, constraints) depuis emphasis.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

EMPHASIS_FILE = Path(__file__).with_name("emphasis.yaml")
LENSES = ("timeline", "risk", "diversity", "constraints")
_OPS = {
    "is_true": lambda s, v: bool(s),
    "lt": lambda s, v: s < v,
    "le": lambda s, v: s <= v,
    "gt": lambda s, v: s > v,
    "ge": lambda s, v: s >= v,
}


def load_rules(path: str | Path | None = None) -> dict:
    with open(path or EMPHASIS_FILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def compute_emphasis(
    signals: dict[str, Any], path: str | Path | None = None
) -> tuple[dict[str, float], list[str], list[dict]]:
    """Retourne (poids normalises, ids des regles declenchees, trace)."""
    cfg = load_rules(path)
    ver = cfg["version"]
    raw = {k: float(cfg["base"][k]) for k in LENSES}
    fired, trace = [], []
    for i, r in enumerate(cfg["rules"]):
        if r["lens"] not in raw:
            raise ValueError(f"emphasis.yaml : lentille inconnue {r['lens']}")
        if r["signal"] not in signals:
            raise KeyError(f"emphasis.yaml : signal inconnu {r['signal']}")
        s = signals[r["signal"]]
        hit = s is not None and _OPS[r["op"]](s, r.get("value"))
        if hit:
            raw[r["lens"]] += float(r["bonus"])
            fired.append(r["id"])
            trace.append(
                {
                    "rule": f"emphasis.{r['id']}",
                    "inputs": {r["signal"]: s, "op": r["op"], "value": r.get("value")},
                    "output": {r["lens"]: float(r["bonus"])},
                    "yaml_path": f"emphasis.yaml@{ver}#rules[{i}]",
                }
            )
    total = sum(raw.values())
    weights = {k: raw[k] / total for k in LENSES}
    trace.append(
        {"rule": "emphasis.normalize", "inputs": raw, "output": weights, "yaml_path": f"emphasis.yaml@{ver}#base"}
    )
    return weights, fired, trace
