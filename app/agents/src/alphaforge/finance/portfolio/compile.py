"""Compilation d'un PolicySpec en contraintes linéaires nommées (une ligne = un rule_id).

Chaque ligne garde son ``rule_id`` pour que l'optimiseur (F2) rende un prix par contrainte et
que le Judge (F4) rende un ``ConstraintCheck`` par règle.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..contracts import Limit, PolicySpec
from ._engine import bt_data

BROAD_TAGS = {"broad_market", "tech_heavy"}


@dataclass(frozen=True)
class LinearRow:
    rule_id: str                 # ex. « max_titre[NVDA] » pour une limite par actif
    parent_rule_id: str          # rule_id du Limit d'origine
    vector: np.ndarray           # coefficients sur les actifs investissables
    lo: float | None
    hi: float | None
    limit: Limit


@dataclass(frozen=True)
class RiskRow:
    rule_id: str
    measure: str                 # CVAR | CDAR | VOL | MDD
    hi: float
    limit: Limit


@dataclass
class CompiledPolicy:
    assets: list[str]
    rows: list[LinearRow]
    risk_rows: list[RiskRow]
    warnings: list[str] = field(default_factory=list)

    def index(self, asset: str) -> int:
        return self.assets.index(asset)


def _matches(asset: str, sel, catalog) -> bool:
    return (asset in sel.assets
            or catalog.at[asset, "asset_class"] in sel.classes
            or bool(set(catalog.at[asset, "tag_list"]) & set(sel.tags_any)))


def compile_policy(policy: PolicySpec, as_of=None) -> CompiledPolicy:
    catalog = bt_data.load_assets()
    assets = policy.investable
    missing = [a for a in assets if a not in catalog.index]
    if missing:
        raise KeyError(f"actifs inconnus de l'engine : {missing}")
    n = len(assets)
    rows: list[LinearRow] = []
    risk_rows: list[RiskRow] = []
    warnings: list[str] = []

    for lim in policy.limits:
        sel = lim.selector
        if lim.kind == "risk":
            risk_rows.append(RiskRow(lim.rule_id, sel.measure, float(lim.max), lim))
            continue
        if lim.kind == "asset_weight":
            hit = [a for a in assets if _matches(a, sel, catalog)]
            if not hit:
                warnings.append(f"{lim.rule_id}: aucun actif investissable visé")
            for a in hit:
                v = np.zeros(n)
                v[assets.index(a)] = 1.0
                rows.append(LinearRow(f"{lim.rule_id}[{a}]", lim.rule_id, v, lim.min, lim.max, lim))
            continue
        if lim.kind == "group_weight":
            v = np.array([1.0 if _matches(a, sel, catalog) else 0.0 for a in assets])
            if not v.any():
                warnings.append(f"{lim.rule_id}: groupe vide dans l'univers investissable")
        else:  # exposure (look-through)
            tag = sel.exposure_tag
            overrides = {a: {tag: o[tag].value} for a, o in policy.exposure_overrides.items()
                         if tag in o and a in assets}
            v = bt_data.exposure_vector(assets, tag, date=as_of, overrides=overrides)
            blind = [a for a in assets if a not in overrides and v[assets.index(a)] == 0.0
                     and BROAD_TAGS & set(catalog.at[a, "tag_list"])
                     and not (a == "US_MKT" or catalog.at[a, "proxy_for_ticker"] == "US_MKT")]
            if blind:
                warnings.append(f"{lim.rule_id}: exposition « {tag} » inconnue pour {blind} "
                                f"(comptée 0) ; ajouter une exposure_override sourcée")
            for a, o in policy.exposure_overrides.items():
                if tag in o and o[tag].status == "HYPOTHESE":
                    warnings.append(f"{lim.rule_id}: exposition « {tag} » de {a} = HYPOTHESE ({o[tag].source})")
        rows.append(LinearRow(lim.rule_id, lim.rule_id, np.asarray(v, float), lim.min, lim.max, lim))

    return CompiledPolicy(assets, rows, risk_rows, warnings)
