"""Socle des overlays dynamiques bornés (SIMULATION SEULEMENT, jamais un conseil ni un ordre).

Un overlay est une **règle systématique** calculée uniquement à partir des rendements passés (≤ ``as_of``,
point-in-time). Il propose un déplacement de la cible stratégique (``delta``, somme nulle) ; il ne relâche
**jamais** une limite du profil : ``apply_overlays`` borne la somme des déplacements dans cet ordre :

(a) déplacement total des actions limité à ±``max_equity_shift`` autour de la part actions de la cible de base ;
(b) part actions dans [e_min, e_cap] de la limite ``alloc.growth`` du PolicySpec (prioritaire sur (a)) ;
(c) cœur de FNB (``etf_equity``) ≥ ``core_etf_min`` des actions ;
(d) projection finale sur toutes les limites linéaires du PolicySpec (``portfolio.optimizer.project`` étendue aux
    contraintes (a)-(c), pour qu'une limite ne soit pas réparée au prix d'une autre).

Le code calcule, le modèle n'explique qu'à partir des ``Fact`` produits ici.

Déterminisme : toute itération qui alimente un calcul parcourt les ensembles en ordre **trié** et les sommes de
poids passent par ``math.fsum`` (arrondi exact, indépendant de l'ordre) ; le résultat ne dépend donc ni de
``PYTHONHASHSEED`` ni de l'ordre d'insertion des dictionnaires fournis par l'appelant.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd

from ...contracts import Fact, PolicySpec, Source
from ...contracts.evolution import OverlayState
from ..config import EvolutionConfig

EQUITY_CLASSES_DEFAULT = ("equity_us", "equity_ca", "etf_equity", "sector_us", "equity_single", "crypto")
SATELLITE_CLASSES = frozenset({"equity_single", "crypto"})
CORE_CLASSES = frozenset({"etf_equity"})
CASH_CLASSES = frozenset({"cash"})
BOND_CLASSES = frozenset({"etf_bond", "bond_synthetic", "bond"})
CASH_FALLBACK_ASSETS = ("ZST.TO",)
PIT_DATASET = "pit:monthly_returns"
EPS = 1e-12


# ---------------------------------------------------------------- contexte et signal


@dataclass(frozen=True)
class OverlayContext:
    """Tout ce qu'un overlay a le droit de lire au mois ``as_of`` (rien au-delà)."""

    as_of: pd.Timestamp  # fin de mois
    returns_upto: pd.DataFrame  # rendements mensuels, index ≤ as_of seulement
    target: dict[str, float]  # cible stratégique de base
    weights: dict[str, float]  # poids courants (après dérive)
    policy: PolicySpec
    asset_class: dict[str, str]
    equity_assets: frozenset[str]
    satellites: frozenset[str]
    core_etfs: frozenset[str]
    cash_like: frozenset[str]
    cfg: EvolutionConfig
    entry_prices: dict[str, float] = field(default_factory=dict)  # niveau d'entrée (unités de ``price_level``)
    peaks: dict[str, float] = field(default_factory=dict)  # plus haut depuis l'entrée (mêmes unités)
    need_floor_cad: float | None = None
    value_cad: float = 0.0
    e_min: float = 0.0
    e_cap: float = 1.0

    def __post_init__(self):
        if len(self.returns_upto.index) and self.returns_upto.index.max() > self.as_of:
            raise ValueError(f"point-in-time violé : rendements après {self.as_of.date()}")


@dataclass
class OverlaySignal:
    name: str
    signal: float | None
    delta: dict[str, float]
    reason_fr: str
    facts: list[Fact] = field(default_factory=list)


class Overlay(Protocol):
    name: str

    def compute(self, ctx: OverlayContext) -> OverlaySignal: ...


# ---------------------------------------------------------------- dérivation des ensembles


def _limit(policy: PolicySpec, rule_id: str):
    return next((lim for lim in policy.limits if lim.rule_id == rule_id), None)


def _select(assets: Iterable[str], sel, asset_class: dict[str, str], asset_tags: dict[str, list[str]] | None):
    tags = asset_tags or {}
    return frozenset(
        a
        for a in assets
        if a in sel.assets or asset_class.get(a) in sel.classes or bool(set(tags.get(a, ())) & set(sel.tags_any))
    )


def _catalog_tags(assets: Iterable[str]) -> dict[str, list[str]]:
    """Tags du catalogue de l'engine si disponible (sinon vide : on retombe sur les classes)."""
    try:
        from ...backtest import data as bt_data

        cat = bt_data.load_assets()
    except Exception:  # catalogue absent (CI sans données) : repli documenté
        return {}
    return {a: list(cat.at[a, "tag_list"]) for a in assets if a in cat.index}


def _tags_for(limits: Iterable, investable: list[str], asset_tags: dict[str, list[str]] | None):
    """Tags fournis ; à défaut, ceux du catalogue (chargés une fois) si une des limites sélectionne par tags."""
    if asset_tags is None and any(lim.selector.tags_any for lim in limits if lim is not None):
        return _catalog_tags(investable)
    return asset_tags


def _equity_set(
    growth, investable: list[str], asset_class: dict[str, str], asset_tags
) -> tuple[frozenset, float, float]:
    """Actions et bornes (e_min, e_cap) de la limite ``alloc.growth`` ; sans elle, classes actions par défaut."""
    if growth is None:
        return frozenset(a for a in investable if asset_class.get(a) in EQUITY_CLASSES_DEFAULT), 0.0, 1.0
    equity = _select(investable, growth.selector, asset_class, asset_tags)
    e_min = float(growth.min) if growth.min is not None else 0.0
    e_cap = float(growth.max) if growth.max is not None else 1.0
    return equity, e_min, e_cap


def _cash_set(cash_lim, investable: list[str], asset_class: dict[str, str], asset_tags) -> frozenset[str]:
    """Quasi-liquidités : limite ``alloc.cash_like``, sinon classe ``cash``, sinon ``CASH_FALLBACK_ASSETS``."""
    cash: frozenset[str] = frozenset()
    if cash_lim is not None:
        cash = _select(investable, cash_lim.selector, asset_class, asset_tags)
    if not cash:
        cash = frozenset(a for a in investable if asset_class.get(a) in CASH_CLASSES)
    if not cash:
        cash = frozenset(a for a in CASH_FALLBACK_ASSETS if a in investable)
    return cash


def context_from(  # noqa: PLR0913 - signature publique gelée : replay.py, gate.py et les tests en passent 6 par position
    policy: PolicySpec,
    as_of,
    returns_upto: pd.DataFrame,
    target: dict[str, float],
    weights: dict[str, float],
    asset_class: dict[str, str],
    *,
    cfg: EvolutionConfig | None = None,
    asset_tags: dict[str, list[str]] | None = None,
    entry_prices: dict[str, float] | None = None,
    peaks: dict[str, float] | None = None,
    need_floor_cad: float | None = None,
    value_cad: float = 0.0,
) -> OverlayContext:
    """Construit le contexte du mois ``as_of`` ; les rendements sont **coupés** à ``as_of`` (point-in-time).

    - actions = actifs visés par la limite ``alloc.growth`` (sinon les classes actions par défaut) ;
    - satellites = classes ``equity_single`` et ``crypto`` ; cœur = ``etf_equity`` ;
    - quasi-liquidités = actifs visés par ``alloc.cash_like`` si elle existe (tags ``cash_like``/``cash`` lus dans
      ``asset_tags`` ou, à défaut, dans le catalogue de l'engine), sinon classe ``cash`` puis ``ZST.TO``.
    """
    if cfg is None:
        from ..config import load_config

        cfg = load_config()
    as_of = pd.Timestamp(as_of)
    investable = list(policy.investable)
    growth, cash_lim = _limit(policy, "alloc.growth"), _limit(policy, "alloc.cash_like")
    # une limite sans tags_any ignore les tags : les charger pour l'une ne change pas la sélection de l'autre
    asset_tags = _tags_for((growth, cash_lim), investable, asset_tags)
    equity, e_min, e_cap = _equity_set(growth, investable, asset_class, asset_tags)
    cash = _cash_set(cash_lim, investable, asset_class, asset_tags)
    return OverlayContext(
        as_of=as_of,
        returns_upto=returns_upto.loc[returns_upto.index <= as_of],
        target=_sorted(target),
        weights=_sorted(weights),
        policy=policy,
        asset_class=dict(asset_class),
        equity_assets=equity,
        satellites=frozenset(a for a in equity if asset_class.get(a) in SATELLITE_CLASSES),
        core_etfs=frozenset(a for a in equity if asset_class.get(a) in CORE_CLASSES),
        cash_like=cash - equity,
        cfg=cfg,
        entry_prices=dict(entry_prices or {}),
        peaks=dict(peaks or {}),
        need_floor_cad=need_floor_cad,
        value_cad=float(value_cad),
        e_min=e_min,
        e_cap=e_cap,
    )


# ---------------------------------------------------------------- aides de calcul (déterministes)


def _sorted(d: dict[str, float]) -> dict[str, float]:
    """Copie aux clés triées (ordre canonique, indépendant de l'appelant et de ``PYTHONHASHSEED``)."""
    return {a: float(d[a]) for a in sorted(d)}


def equity_share(w: dict[str, float], equity_assets: Iterable[str]) -> float:
    eq = set(equity_assets)
    return float(math.fsum(v for a, v in w.items() if a in eq))


def _pro_rata(amount: float, pool: dict[str, float]) -> dict[str, float]:
    """Répartit ``amount`` sur ``pool`` au prorata des poids (à parts égales si tous nuls), clés triées."""
    if not pool or abs(amount) < EPS:
        return {}
    keys = sorted(pool)
    tot = math.fsum(max(pool[a], 0.0) for a in keys)
    if tot <= EPS:
        return {a: amount / len(keys) for a in keys}
    return {a: amount * max(pool[a], 0.0) / tot for a in keys}


def _add(d: dict[str, float], other: dict[str, float]) -> dict[str, float]:
    out = dict(d)
    for a, v in other.items():
        out[a] = out.get(a, 0.0) + v
    return out


def move_equity(
    w: dict[str, float],
    shift: float,
    equity_assets: Iterable[str],
    cash_like: Iterable[str],
    ref: dict[str, float] | None = None,
) -> dict[str, float]:
    """Delta (somme nulle) qui déplace ``shift`` de poids vers (+) ou depuis (−) les actions.

    Côté actions : au prorata des poids actions de ``w``. Contrepartie : quasi-liquidités au prorata de ``ref``
    (la cible, par défaut ``w``) ; sans quasi-liquidités, les autres actifs non actions (obligations…).
    Une hausse est limitée au poids disponible en contrepartie, une baisse au poids actions (pas de vente à découvert).
    """
    eq = set(equity_assets)
    ref = ref or w
    in_universe = set(w) | set(ref)
    universe = sorted(in_universe)  # ordre trié : sommes reproductibles
    cash = [a for a in sorted(cash_like) if a in in_universe and a not in eq]
    counter = cash or [a for a in universe if a not in eq]
    eq_pool = {a: w.get(a, 0.0) for a in universe if a in eq}
    if shift < 0:
        shift = -min(-shift, math.fsum(max(v, 0.0) for v in eq_pool.values()))
        if not counter:
            return {}
        d = _pro_rata(shift, eq_pool)
        return _add(d, _pro_rata(-shift, {a: ref.get(a, 0.0) for a in counter}))
    # hausse : on puise d'abord dans les quasi-liquidités, puis dans les autres non-actions
    avail = {a: max(w.get(a, 0.0), 0.0) for a in counter}
    others = {a: max(w.get(a, 0.0), 0.0) for a in universe if a not in eq and a not in avail}
    avail_tot = math.fsum(avail.values())
    take = min(shift, avail_tot + math.fsum(others.values()))
    if take <= EPS:
        return {}
    first = min(take, avail_tot)
    d = _pro_rata(-first, avail) if first > EPS else {}
    if take - first > EPS:
        d = _add(d, _pro_rata(-(take - first), others))
    if not eq_pool or math.fsum(eq_pool.values()) <= EPS:
        eq_pool = {a: ref.get(a, 0.0) for a in universe if a in eq}
    return _add(d, _pro_rata(take, eq_pool))


def basket_returns(returns: pd.DataFrame, weights: dict[str, float], assets: Iterable[str]) -> pd.Series:
    """Rendements mensuels d'un panier pondéré par ``weights`` (renormalisé sur les actifs ayant une donnée).
    Colonnes en ordre trié : la somme ligne à ligne ne dépend pas de l'ordre d'un ensemble."""
    cols = sorted(a for a in set(assets) if a in returns.columns and weights.get(a, 0.0) > 0)
    if not cols:
        return pd.Series(dtype=float)
    r = returns[cols]
    w = pd.Series({a: weights[a] for a in cols})
    avail = r.notna()
    wsum = avail.mul(w, axis=1).sum(axis=1)
    out = r.fillna(0.0).mul(w, axis=1).sum(axis=1) / wsum.replace(0.0, np.nan)
    return out.dropna()


def price_level(returns: pd.DataFrame | pd.Series, asset: str | None = None) -> pd.Series:
    """Indice de prix (rendement total) = Π(1+r) depuis la première donnée. Les niveaux d'entrée et de plus haut
    des stops doivent être exprimés dans ces unités, sur un historique dont le début reste fixe."""
    s = returns[asset] if asset is not None else returns
    s = s.dropna()
    return (1 + s).cumprod()


def momentum_12_1(r: pd.Series, lookback: int, skip: int) -> float | None:
    """Rendement composé des mois [t−lookback−skip+1, t−skip] (12-1 par défaut) ; None si historique court."""
    r = r.dropna()
    if len(r) < lookback + skip:
        return None
    x = r.iloc[len(r) - lookback - skip : len(r) - skip]
    return float((1 + x).prod() - 1)


def update_stop_levels(  # noqa: PLR0913 - signature publique gelée : replay.py et gate.py passent les six par position
    returns_upto: pd.DataFrame,
    prev_weights: dict[str, float],
    new_weights: dict[str, float],
    satellites: Iterable[str],
    entry: dict[str, float],
    peaks: dict[str, float],
):
    """Tenue des niveaux d'entrée et de plus haut des satellites, à appeler par le tick après chaque mois.

    Entrée enregistrée quand un satellite passe de 0 à > 0 (ou s'il est détenu sans niveau connu) ; plus haut =
    max(plus haut, niveau courant) ; effacés quand le satellite est soldé. Retourne (entry, peaks) mis à jour.
    """
    entry, peaks = dict(entry), dict(peaks)
    for a in sorted(satellites):
        if a not in returns_upto.columns:
            continue
        lvl = price_level(returns_upto, a)
        if lvl.empty:
            continue
        cur = float(lvl.iloc[-1])
        held = new_weights.get(a, 0.0) > 1e-9
        if not held:
            entry.pop(a, None)
            peaks.pop(a, None)
            continue
        if a not in entry or prev_weights.get(a, 0.0) <= 1e-9:
            entry[a] = cur
            peaks[a] = cur
        peaks[a] = max(peaks.get(a, cur), cur)
    return entry, peaks


def fact(  # noqa: PLR0913 - signature publique gelée : chaque overlay passe les six premiers par position
    ctx: OverlayContext,
    name: str,
    key: str,
    label_fr: str,
    value,
    unit: str,
    *,
    params: Iterable[str] = (),
    status: str = "FAIT",
    processing: str | None = None,
) -> Fact:
    """Fact ``ov.<name>.<key>`` avec ses sources (rendements point-in-time + paramètres YAML cités)."""
    if isinstance(value, float) and not math.isfinite(value):
        value = None
    srcs = [Source(dataset=PIT_DATASET, processing=processing or f"rendements mensuels ≤ {ctx.as_of.date()}")]
    srcs += [Source(dataset=ctx.cfg.src(f"overlays.{name}.{p}")) for p in params]
    return Fact(
        fact_id=f"ov.{name}.{key}",
        label_fr=label_fr,
        value=value,
        unit=unit,
        as_of=ctx.as_of.date(),
        status=status,
        sources=srcs,
        trace_id=trace_id(ctx, name),
    )


def trace_id(ctx: OverlayContext, name: str) -> str:
    return f"ov:{name}:{ctx.as_of:%Y-%m}"


def params_of(ctx: OverlayContext, name: str, override: dict | None) -> dict:
    return {**ctx.cfg.overlay(name), **(override or {})}


def clean(delta: dict[str, float], tol: float = 1e-12) -> dict[str, float]:
    return {a: float(v) for a, v in delta.items() if abs(v) > tol}


# ---------------------------------------------------------------- bornes


def _apply(w: dict[str, float], d: dict[str, float]) -> dict[str, float]:
    return _add(w, d)


def equity_bounds(ctx: OverlayContext) -> tuple[float, float]:
    """Intervalle admissible de la part actions : (a) ∩ (b) ; si vide, (b) l'emporte (bord le plus proche)."""
    s = float(ctx.cfg.overlays.common["max_equity_shift"])
    base = equity_share(ctx.target, ctx.equity_assets)
    lo, hi = max(ctx.e_min, base - s), min(ctx.e_cap, base + s)
    if lo > hi + 1e-12:
        edge = min(max(base, ctx.e_min), ctx.e_cap)
        lo = hi = edge
    return lo, hi


def simple_bounds(ctx: OverlayContext, adjusted: dict[str, float]) -> dict[str, float]:
    """Bornes (a)-(c) sans solveur (utilisées seules dans la porte de validation, voir ``gate.py``)."""
    w = {a: max(adjusted[a], 0.0) for a in sorted(adjusted)}
    tot = math.fsum(w.values())
    w = {a: v / tot for a, v in w.items()} if tot > EPS else dict(ctx.target)
    lo, hi = equity_bounds(ctx)
    eq = equity_share(w, ctx.equity_assets)
    want = min(max(eq, lo), hi)
    if abs(want - eq) > 1e-12:
        w = _apply(w, move_equity(w, want - eq, ctx.equity_assets, ctx.cash_like, ref=ctx.target))
    core_min = float(ctx.cfg.overlays.common["core_etf_min"])
    cores = [a for a in sorted(ctx.core_etfs) if a in w or a in ctx.target]
    if cores:
        eq = equity_share(w, ctx.equity_assets)
        core = math.fsum(w.get(a, 0.0) for a in cores)
        need = core_min * eq - core
        if need > 1e-12:
            non_core = {
                a: w.get(a, 0.0) for a in sorted(ctx.equity_assets) if a not in ctx.core_etfs and w.get(a, 0.0) > 0
            }
            need = min(need, math.fsum(non_core.values()))
            pool = {a: ctx.target.get(a, 0.0) for a in cores}
            w = _apply(w, _add(_pro_rata(-need, non_core), _pro_rata(need, pool)))
    w = {a: max(w[a], 0.0) for a in sorted(w)}
    tot = math.fsum(w.values())
    return {a: v / tot for a, v in w.items()}


def bounded_projection(ctx: OverlayContext, adjusted: dict[str, float]) -> dict[str, float]:
    """(d) Poids les plus proches de ``adjusted`` sous TOUTES les limites linéaires du PolicySpec (comme
    ``optimizer.project``) **et** sous (a)-(c). Si ce problème est infaisable, repli sur ``project`` seul, puis
    sur la cible de base (aucun overlay appliqué)."""
    import cvxpy as cp

    from ...portfolio.compile import compile_policy
    from ...portfolio.optimizer import _solve, project

    comp = compile_policy(ctx.policy, ctx.as_of)
    assets = comp.assets
    w0 = np.array([float(adjusted.get(a, 0.0)) for a in assets])
    eqv = np.array([1.0 if a in ctx.equity_assets else 0.0 for a in assets])
    corev = np.array([1.0 if a in ctx.core_etfs else 0.0 for a in assets])
    lo, hi = equity_bounds(ctx)
    w = cp.Variable(len(assets))
    cons = [cp.sum(w) == 1, w >= 0, eqv @ w >= lo - 1e-9, eqv @ w <= hi + 1e-9]
    if corev.any():
        cons.append(corev @ w - float(ctx.cfg.overlays.common["core_etf_min"]) * (eqv @ w) >= 0)
    for row in comp.rows:
        if row.hi is not None:
            cons.append(row.vector @ w <= row.hi)
        if row.lo is not None:
            cons.append(row.vector @ w >= row.lo)
    prob = cp.Problem(cp.Minimize(cp.sum_squares(w - w0)), cons)
    _solve(prob)
    if w.value is not None and prob.status in ("optimal", "optimal_inaccurate"):
        wv = np.clip(w.value, 0, None)
        return {a: float(x) for a, x in zip(assets, wv / wv.sum(), strict=True)}
    try:
        return project(ctx.policy, adjusted, ctx.as_of)
    except ValueError:
        return dict(ctx.target)


def linear_breaches(
    w: dict[str, float],
    policy: PolicySpec,
    asset_class: dict[str, str],
    asset_tags: dict[str, list[str]] | None = None,
    tol: float = 1e-6,
) -> list[str]:
    """Limites ``asset_weight`` / ``group_weight`` violées (sélection par actifs, classes, tags si fournis).
    Contrôle sans catalogue (exposition et risque non évalués ici : c'est le rôle du Judge)."""
    out = []
    for lim in policy.limits:
        if lim.kind not in ("asset_weight", "group_weight"):
            continue
        hit = sorted(_select(w.keys(), lim.selector, asset_class, asset_tags))
        vals = [w.get(a, 0.0) for a in hit] if lim.kind == "asset_weight" else [math.fsum(w.get(a, 0.0) for a in hit)]
        if lim.kind == "group_weight" and not hit:
            continue
        for v in vals:
            if (lim.max is not None and v > lim.max + tol) or (lim.min is not None and v < lim.min - tol):
                out.append(lim.rule_id)
                break
    return out


# ---------------------------------------------------------------- application


def _l1(d: dict[str, float]) -> float:
    return float(math.fsum(abs(v) for v in d.values()))


def _enabled(ctx: OverlayContext, name: str) -> bool:
    return bool(ctx.cfg.overlay(name).get("enabled", True))


def _proposed_deltas(
    ctx: OverlayContext, overlays: list[Overlay], active: set[str]
) -> tuple[list[tuple[Overlay, OverlaySignal, bool]], dict[str, dict[str, float]], dict[str, float]]:
    """Calcule chaque overlay dans ``cfg.overlays.order`` et somme les deltas des overlays retenus.

    Application séquentielle : un delta est réduit (facteur k ≤ 1) pour ne rendre aucun poids négatif (ex. stop_loss
    et trailing_stop sur le même satellite ne le retirent qu'une fois). Rend (signaux avec leur drapeau « retenu »,
    delta appliqué par overlay retenu, somme brute des deltas appliqués)."""
    order = {n: i for i, n in enumerate(ctx.cfg.overlays.order)}
    sigs: list[tuple[Overlay, OverlaySignal, bool]] = []
    raw_total: dict[str, float] = {}
    applied: dict[str, dict[str, float]] = {}
    for ov in sorted(overlays, key=lambda o: order.get(o.name, len(order))):
        on = _enabled(ctx, ov.name) and ov.name in active
        sig = ov.compute(ctx)
        sigs.append((ov, sig, on))
        if not on:
            continue
        cur = _add(ctx.target, raw_total)
        neg = [cur.get(a, 0.0) / -v for a, v in sig.delta.items() if v < -EPS]
        k = min([1.0, *[max(x, 0.0) for x in neg]])
        scaled = {a: k * v for a, v in sig.delta.items()}
        applied[ov.name] = scaled
        raw_total = _add(raw_total, scaled)
    return sigs, applied, raw_total


def _attribute(
    eff: dict[str, float], raw_total: dict[str, float], on_deltas: list[tuple[str, dict[str, float]]], keys: list[str]
) -> dict[str, dict[str, float]]:
    """Répartit le déplacement effectif ``eff`` entre les overlays retenus (voir ``apply_overlays``)."""
    sizes = {name: _l1(d) for name, d in on_deltas}
    tot_size = math.fsum(sizes.values())
    attributed: dict[str, dict[str, float]] = {name: {} for name, _ in on_deltas}
    for a in keys:
        e = eff.get(a, 0.0)
        if abs(e) <= 1e-10:
            continue
        rs = raw_total.get(a, 0.0)
        for name, d in on_deltas:
            share = (d.get(a, 0.0) / rs) if abs(rs) > 1e-12 else (sizes[name] / tot_size)
            attributed[name][a] = attributed[name].get(a, 0.0) + e * share
    return attributed


def _gate_status(ctx: OverlayContext, name: str, gate_states: dict[str, OverlayState]) -> tuple[str, str]:
    """(statut de porte, raison) : « desactive » si ``enabled: false``, sinon ``gate_states``, sinon « non_evalue »."""
    if not _enabled(ctx, name):
        return "desactive", "désactivé par evolution.yaml (enabled: false)"
    g = gate_states.get(name)
    if g is not None:
        return g.gate, g.gate_reason_fr
    return "non_evalue", "porte de validation non évaluée"


def _overlay_state(
    ctx: OverlayContext,
    computed: tuple[Overlay, OverlaySignal, bool],
    attributed: dict[str, dict[str, float]],
    gate_states: dict[str, OverlayState],
) -> OverlayState:
    """État affiché d'un overlay : delta effectif attribué (vide s'il n'est pas retenu) et drapeau « rogné »."""
    ov, sig, on = computed
    gate, reason = _gate_status(ctx, ov.name, gate_states)
    if gate != "desactive" and not on:
        reason = f"testé, non retenu : {reason}"
    d = clean(attributed.get(ov.name, {}), 1e-10) if on else {}
    clipped = bool(
        on
        and _l1(sig.delta) > EPS
        and _l1({a: d.get(a, 0.0) - sig.delta.get(a, 0.0) for a in sorted(set(d) | set(sig.delta))}) > 1e-8
    )
    return OverlayState(
        name=ov.name,
        active=on,
        gate=gate,
        gate_reason_fr=reason,
        signal=sig.signal,
        delta=d,
        clipped=clipped,
        fact_ids=[f.fact_id for f in sig.facts],
    )


def _bounds_facts(
    ctx: OverlayContext, base: dict[str, float], bounded: dict[str, float], *, clipped_any: bool
) -> list[Fact]:
    """Facts ``ov.bounds.*`` : part actions avant et après, bornes effectives, part du cœur, rognage."""
    lo, hi = equity_bounds(ctx)
    eq_b, eq_f = equity_share(base, ctx.equity_assets), equity_share(bounded, ctx.equity_assets)
    eqf = eq_f if eq_f > EPS else float("nan")
    core_f = math.fsum(bounded.get(a, 0.0) for a in sorted(ctx.core_etfs)) / eqf if ctx.core_etfs else None
    common = ("max_equity_shift", "core_etf_min")
    bsrc = [Source(dataset=ctx.cfg.src(f"overlays.common.{k}")) for k in common]
    bsrc.append(Source(dataset=f"policy:{ctx.policy.policy_id}#alloc.growth"))
    facts = []
    for key, label, val in (
        ("equity_base", "Part actions de la cible de base", eq_b),
        ("equity_after", "Part actions après overlays bornés, avant contrôle du Judge", eq_f),
        ("equity_lo", "Borne basse effective de la part actions", lo),
        ("equity_hi", "Borne haute effective de la part actions", hi),
        ("core_share", "Part du cœur de FNB dans les actions", core_f),
        ("clipped", "Les bornes ont rogné les déplacements (1 = oui)", float(clipped_any)),
    ):
        v = None if val is None or (isinstance(val, float) and not math.isfinite(val)) else float(val)
        facts.append(
            Fact(
                fact_id=f"ov.bounds.{key}",
                label_fr=label,
                value=v,
                unit="ratio",
                as_of=ctx.as_of.date(),
                status="FAIT",
                sources=bsrc,
                trace_id=trace_id(ctx, "bounds"),
            )
        )
    return facts


def apply_overlays(
    ctx: OverlayContext,
    overlays: list[Overlay],
    active: set[str],
    *,
    gate_states: dict[str, OverlayState] | None = None,
    project: bool = True,
) -> tuple[dict[str, float], list[OverlayState], list[Fact]]:
    """Applique les overlays actifs dans ``cfg.overlays.order``, somme leurs deltas puis borne (a)-(d).

    - Un overlay inactif est quand même calculé (signal affiché) mais son delta n'est pas appliqué ; il apparaît
      avec ``active=False`` et le statut de sa porte (``gate_states``, sinon « desactive » si ``enabled: false``,
      sinon « non_evalue »).
    - ``OverlayState.delta`` = déplacement **effectif** après bornes. Attribution au prorata, actif par actif : la
      part de l'overlay dans la somme brute des deltas sur cet actif ; le reliquat créé par les bornes (actif sans
      delta brut) est réparti au prorata de la taille brute (L1) de chaque overlay. La somme des deltas attribués
      égale exactement le déplacement total effectif ; un delta attribué isolé peut ne pas sommer à 0 (indicatif).
    - ``project=False`` saute (d) : réservé à la porte de validation (vitesse) et aux tests sans catalogue.
    """
    sigs, applied, raw_total = _proposed_deltas(ctx, overlays, active)
    base = {a: float(v) for a, v in ctx.target.items()}
    bounded = simple_bounds(ctx, _add(base, raw_total))
    if project:
        bounded = bounded_projection(ctx, bounded)
    bounded = _sorted(bounded)  # ordre canonique de la sortie
    keys = sorted(set(base) | set(bounded))
    all_keys = sorted(set(keys) | set(raw_total))
    eff = clean({a: bounded.get(a, 0.0) - base.get(a, 0.0) for a in keys}, 1e-10)
    clipped_any = _l1({a: eff.get(a, 0.0) - raw_total.get(a, 0.0) for a in all_keys}) > 1e-8
    on_deltas = [(ov.name, applied[ov.name]) for ov, _, on in sigs if on and _l1(applied[ov.name]) > EPS]
    attributed = _attribute(eff, raw_total, on_deltas, all_keys)
    states = [_overlay_state(ctx, computed, attributed, gate_states or {}) for computed in sigs]
    facts = [f for _, sig, _ in sigs for f in sig.facts]
    facts += _bounds_facts(ctx, base, bounded, clipped_any=clipped_any)
    return bounded, states, facts
