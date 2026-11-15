"""Compilation d'un PolicySpec en contraintes linéaires nommées (une ligne = un rule_id).

Chaque ligne garde son ``rule_id`` pour que l'optimiseur (F2) rende un prix par contrainte et
que le Judge (F4) rende un ``ConstraintCheck`` par règle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..backtest import data as bt_data
from ..contracts import Limit, PolicySpec

BROAD_TAGS = {"broad_market", "tech_heavy"}


@dataclass(frozen=True)
class LinearRow:
    rule_id: str  # ex. « max_titre[NVDA] » pour une limite par actif
    parent_rule_id: str  # rule_id du Limit d'origine
    vector: np.ndarray  # coefficients sur les actifs investissables
    lo: float | None
    hi: float | None
    limit: Limit


@dataclass(frozen=True)
class RiskRow:
    rule_id: str
    measure: str  # CVAR | CDAR | VOL | MDD
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


def _matches(asset: str, selector, catalog: pd.DataFrame) -> bool:
    return (
        asset in selector.assets
        or catalog.at[asset, "asset_class"] in selector.classes
        or bool(set(catalog.at[asset, "tag_list"]) & set(selector.tags_any))
    )


def exposure_overrides_for(policy: PolicySpec, tag: str, assets: list[str]) -> dict[str, dict[str, float]]:
    """Expositions à ``tag`` déclarées par le mandat pour ``assets``, au format de ``bt_data.exposure_vector``."""
    return {
        asset: {tag: declared[tag].value}
        for asset, declared in policy.exposure_overrides.items()
        if tag in declared and asset in assets
    }


def unknown_exposures(assets: list[str], vector: np.ndarray, overrides: dict, catalog: pd.DataFrame) -> list[str]:
    """Actifs larges comptés 0 faute de donnée : ni déclaration du mandat, ni look-through de l'engine
    (seuls US_MKT et ses proxys en ont un)."""
    return [
        asset
        for asset, x in zip(assets, vector, strict=True)
        if x == 0
        and asset not in overrides
        and BROAD_TAGS & set(catalog.at[asset, "tag_list"])
        and not (asset == "US_MKT" or catalog.at[asset, "proxy_for_ticker"] == "US_MKT")
    ]


@dataclass
class _Compiler:
    """Traduit les limites linéaires d'un mandat en lignes sur les actifs investissables."""

    policy: PolicySpec
    as_of: Any
    catalog: pd.DataFrame
    assets: list[str]
    warnings: list[str] = field(default_factory=list)

    def rows(self, limit: Limit) -> list[LinearRow]:
        if limit.kind == "asset_weight":
            return self._asset_rows(limit)
        vector = self._group_vector(limit) if limit.kind == "group_weight" else self._exposure_vector(limit)
        return [LinearRow(limit.rule_id, limit.rule_id, np.asarray(vector, float), limit.min, limit.max, limit)]

    def _asset_rows(self, limit: Limit) -> list[LinearRow]:
        """Une ligne par actif visé."""
        targeted = [asset for asset in self.assets if _matches(asset, limit.selector, self.catalog)]
        if not targeted:
            self.warnings.append(f"{limit.rule_id}: aucun actif investissable visé")
        return [
            LinearRow(f"{limit.rule_id}[{asset}]", limit.rule_id, self._unit_vector(asset), limit.min, limit.max, limit)
            for asset in targeted
        ]

    def _unit_vector(self, asset: str) -> np.ndarray:
        vector = np.zeros(len(self.assets))
        vector[self.assets.index(asset)] = 1.0
        return vector

    def _group_vector(self, limit: Limit) -> np.ndarray:
        vector = np.array([1.0 if _matches(asset, limit.selector, self.catalog) else 0.0 for asset in self.assets])
        if not vector.any():
            self.warnings.append(f"{limit.rule_id}: groupe vide dans l'univers investissable")
        return vector

    def _exposure_vector(self, limit: Limit) -> np.ndarray:
        """Look-through : part de chaque actif exposée au thème, déclarations du mandat d'abord."""
        tag = limit.selector.exposure_tag
        overrides = exposure_overrides_for(self.policy, tag, self.assets)
        vector = bt_data.exposure_vector(self.assets, tag, date=self.as_of, overrides=overrides)
        blind = unknown_exposures(self.assets, vector, overrides, self.catalog)
        if blind:
            self.warnings.append(
                f"{limit.rule_id}: exposition « {tag} » inconnue pour {blind} "
                f"(comptée 0) ; ajouter une exposure_override sourcée"
            )
        for asset, declared in self.policy.exposure_overrides.items():
            if tag in declared and declared[tag].status == "HYPOTHESE":
                self.warnings.append(
                    f"{limit.rule_id}: exposition « {tag} » de {asset} = HYPOTHESE ({declared[tag].source})"
                )
        return vector


def compile_policy(policy: PolicySpec, as_of=None) -> CompiledPolicy:
    catalog = bt_data.load_assets()
    assets = policy.investable
    missing = [asset for asset in assets if asset not in catalog.index]
    if missing:
        raise KeyError(f"actifs inconnus de l'engine : {missing}")
    compiler = _Compiler(policy, as_of, catalog, assets)
    rows: list[LinearRow] = []
    risk_rows: list[RiskRow] = []
    for limit in policy.limits:
        if limit.kind == "risk":
            risk_rows.append(RiskRow(limit.rule_id, limit.selector.measure, float(limit.max), limit))
        else:
            rows.extend(compiler.rows(limit))
    return CompiledPolicy(assets, rows, risk_rows, compiler.warnings)
