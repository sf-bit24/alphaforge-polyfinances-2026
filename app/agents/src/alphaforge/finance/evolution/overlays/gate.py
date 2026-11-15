"""Porte de validation hors échantillon d'un overlay, évaluée STRICTEMENT AVANT la fenêtre rejouée.

Simulation mensuelle sur les seuls mois ≤ ``train_end`` (toute date ultérieure demandée lève une erreur) :
- base = rééquilibrage mensuel vers la cible stratégique ;
- overlay = rééquilibrage mensuel vers la cible + delta de l'overlay seul, borné par (a)-(c) de ``base.py``.
  La projection (d) sur les limites linéaires (solveur) est **sautée** ici pour la vitesse. Les dépassements de
  limites linéaires constatés sont rapportés ; ils ne font échouer la porte que si
  ``gate.require_no_limit_breach`` est vrai (v0.1 : faux, car le tick les rétablit chaque mois par projection et
  contrôle du Judge, limites de risque comprises).
- coûts : ``cfg.trading.cost_bps`` par unité de rotation aller simple (0,5·Σ|Δw|), dans les deux portefeuilles.

Un rendement manquant (actif pas encore coté) compte pour 0 ce mois-là (HYPOTHESE, identique base/overlay).
Verdict « passe » ssi les quatre conditions tiennent :
- DSR ≥ ``gate.min_dsr``, la déflation comptant ``n_trials_total`` essais (tous les overlays évalués pour le
  persona ; à défaut, la seule grille de cet overlay) ;
- PBO ≤ ``gate.max_pbo``, **exigé** : un PBO non calculable (moins de ``MIN_PBO_TRIALS`` essais, aucun Sharpe fini
  ou historique commun trop court) fait échouer la porte ; les variantes sont alignées sur leurs mois communs ;
- mois d'entraînement ≥ ``gate.min_train_months`` ;
- si ``gate.require_no_limit_breach``, aucun dépassement de limite.
Sinon l'overlay est « testé, non retenu ». Non testé en v0.1 : le « même rang en CAD depuis 1977 et en USD depuis
1946 » demandé par la décision D4 (à confirmer).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ...backtest import metrics as bt_metrics
from ...backtest import validation_dsr
from ...contracts import PolicySpec
from ...contracts.evolution import ComparatorRow, OverlayState
from ..config import EvolutionConfig
from .base import (
    EPS,
    OverlayContext,
    _add,
    _catalog_tags,
    context_from,
    equity_share,
    linear_breaches,
    simple_bounds,
    update_stop_levels,
)
from .registry import REGISTRY

MIN_PBO_TRIALS = 4  # CSCV : au moins 4 essais, sinon PBO non calculable et la porte échoue


@dataclass(frozen=True)
class _GateInputs:
    """Données communes à toutes les variantes simulées d'un overlay (historique ≤ ``train_end``)."""

    returns: pd.DataFrame
    base_target: dict[str, float]
    policy: PolicySpec
    asset_class: dict[str, str]
    asset_tags: dict[str, list[str]] | None
    cfg: EvolutionConfig
    need_floor_cad: float | None
    value_cad: float


@dataclass(frozen=True)
class _GateStats:
    """Mesures de la configuration évaluée (``param_grid[0]``) et de sa grille, lues par le verdict."""

    dsr: float
    sharpe_ann: float
    pbo: float | None
    pbo_na: str | None  # raison pour laquelle le PBO n'est pas calculable, sinon None
    breaches: list[str]
    n_train: int
    n_used: int  # essais comptés dans la déflation du DSR
    n_grid: int
    n_common: int  # mois communs à toutes les variantes (PBO)
    train_end: pd.Timestamp


def _variants(v: int | float, *, wide: bool) -> list[int | float]:
    if isinstance(v, int):
        step = (2 if v >= 6 else 1) * (2 if wide else 1)
        return [v + step, max(1, v - step)] if wide else [max(1, v - step), v + step]
    return [round(v * 1.5, 6), round(v * 0.5, 6)] if wide else [round(v * 0.75, 6), round(v * 1.25, 6)]


def default_grid(cfg: EvolutionConfig, name: str) -> list[dict]:
    """Paramètres du YAML, puis une variante basse et une haute par paramètre numérique (ex. ma 8 / 10 / 12).

    Si la grille compte moins de ``MIN_PBO_TRIALS`` essais (ex. ``take_profit``, un seul paramètre), un second
    anneau est ajouté (±2 pas pour un entier, ×1,5 puis ×0,5 pour un réel, côté haut d'abord) jusqu'à
    ``MIN_PBO_TRIALS`` essais, pour que le PBO, exigé par la porte, soit calculable."""
    base = {k: v for k, v in cfg.overlay(name).items() if k != "enabled"}
    numeric = [(k, v) for k, v in base.items() if not isinstance(v, bool) and isinstance(v, int | float)]
    grid = [dict(base)]
    for k, v in numeric:
        for x in _variants(v, wide=False):
            if x != v:
                grid.append({**base, k: x})
    for k, v in numeric:
        for x in _variants(v, wide=True):
            cand = {**base, k: x}
            if len(grid) < MIN_PBO_TRIALS and x != v and cand not in grid:
                grid.append(cand)
    return grid


def _warmup(params: dict) -> int:
    ints = [int(v) for k, v in params.items() if isinstance(v, int) and not isinstance(v, bool)]
    return max([13, *[i + 1 for i in ints]])


def _drift(w: dict[str, float], rr: pd.Series) -> tuple[dict[str, float], float]:
    g = {a: w[a] * (1 + float(rr.get(a, 0.0))) for a in sorted(w)}
    tot = math.fsum(g.values())
    ret = tot - 1.0
    return ({a: v / tot for a, v in g.items()} if tot > EPS else dict(w)), ret


def _turnover(a: dict[str, float], b: dict[str, float]) -> float:
    return 0.5 * math.fsum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in sorted(set(a) | set(b)))


def _new_breaches(ctx: OverlayContext, tgt: dict[str, float], inputs: _GateInputs, base_breach: set[str]) -> set[str]:
    """Limites linéaires dépassées par la cible de l'overlay mais pas par la cible de base, plus ``alloc.growth``."""
    new = set(linear_breaches(tgt, inputs.policy, inputs.asset_class, inputs.asset_tags)) - base_breach
    eq = equity_share(tgt, ctx.equity_assets)
    if eq < ctx.e_min - 1e-6 or eq > ctx.e_cap + 1e-6:
        new.add("alloc.growth")
    return new


def _simulate(name: str, params: dict, inputs: _GateInputs):
    """Retourne (rendements base, rendements overlay, rotations overlay, dépassements nouveaux)."""
    ov = REGISTRY[name](params)
    r, base_target = inputs.returns, inputs.base_target
    cost = inputs.cfg.trading.cost_bps / 1e4
    rr_all = r.fillna(0.0)
    base_breach = set(linear_breaches(base_target, inputs.policy, inputs.asset_class, inputs.asset_tags))
    warm = _warmup(params)
    w_b, w_o = dict(base_target), dict(base_target)
    entry, peaks = {}, {}
    value = inputs.value_cad
    rb, ro, turns, breaches = [], [], [], set()
    for i in range(warm - 1, len(r) - 1):
        ctx = context_from(
            inputs.policy,
            r.index[i],
            r.iloc[: i + 1],
            base_target,
            w_o,
            inputs.asset_class,
            cfg=inputs.cfg,
            asset_tags=inputs.asset_tags,
            entry_prices=entry,
            peaks=peaks,
            need_floor_cad=inputs.need_floor_cad,
            value_cad=value,
        )
        sig = ov.compute(ctx)
        tgt = simple_bounds(ctx, _add(base_target, sig.delta)) if sig.delta else dict(base_target)
        breaches |= _new_breaches(ctx, tgt, inputs, base_breach)
        t_o, t_b = _turnover(tgt, w_o), _turnover(base_target, w_b)
        entry, peaks = update_stop_levels(r.iloc[: i + 1], w_o, tgt, ctx.satellites, entry, peaks)
        nxt = rr_all.iloc[i + 1]
        w_o, g_o = _drift(tgt, nxt)
        w_b, g_b = _drift(base_target, nxt)
        ro.append(g_o - t_o * cost)
        rb.append(g_b - t_b * cost)
        turns.append(t_o)
        value *= 1 + ro[-1]
    idx = r.index[warm : len(r)]
    return pd.Series(rb, index=idx), pd.Series(ro, index=idx), np.asarray(turns), sorted(breaches)


def _disabled(name: str) -> tuple[OverlayState, ComparatorRow]:
    reason = "désactivé par evolution.yaml (enabled: false) : comparateur seulement, jamais appliqué"
    return (
        OverlayState(name=name, active=False, gate="desactive", gate_reason_fr=reason),
        ComparatorRow(
            name=name,
            applied=False,
            n_trials=1,
            sharpe=None,
            dsr=None,
            pbo=None,
            cagr=None,
            max_drawdown=None,
            turnover_ann=None,
            verdict_fr=reason,
        ),
    )


def _short_history(name: str, train_end: pd.Timestamp, n_train: int, n_used: int) -> tuple[OverlayState, ComparatorRow]:
    reason = f"historique insuffisant avant {train_end.date()} ({n_train} mois) : testé, non retenu"
    return (
        OverlayState(name=name, active=False, gate="echoue", gate_reason_fr=reason),
        ComparatorRow(
            name=name,
            applied=False,
            n_trials=n_used,
            sharpe=None,
            dsr=None,
            cagr=None,
            max_drawdown=None,
            turnover_ann=None,
            verdict_fr=reason,
        ),
    )


def _fmt(x, f=".2f") -> str:
    return "n/d" if x is None or (isinstance(x, float) and not math.isfinite(x)) else format(x, f)


def _finite_or_none(x: float) -> float | None:
    return x if math.isfinite(x) else None


def _train_returns(returns: pd.DataFrame, train_end: pd.Timestamp, months: list | None) -> pd.DataFrame:
    """Mois d'entraînement (``months`` s'il est donné), triés ; une date > ``train_end`` lève ValueError."""
    if months is not None:
        late = [pd.Timestamp(m) for m in months if pd.Timestamp(m) > train_end]
        if late:
            raise ValueError(f"porte hors échantillon violée : mois {late[0].date()} > train_end {train_end.date()}")
        r = returns.loc[returns.index.isin(pd.DatetimeIndex(months))]
    else:
        r = returns.loc[returns.index <= train_end]
    if len(r.index) and r.index.max() > train_end:  # garde-fou : jamais de mois après train_end
        raise ValueError("porte hors échantillon violée : données après train_end")
    return r.sort_index()


def _pbo(excess: list[pd.Series], n_grid: int, *, any_finite: bool) -> tuple[float | None, str | None, int]:
    """PBO (CSCV) sur les mois COMMUNS des variantes (jointure interne sur les dates : les préchauffages diffèrent).
    Rend (PBO ou None, raison s'il n'est pas calculable, nombre de mois communs)."""
    common = pd.concat(excess, axis=1, join="inner").dropna(how="any")
    if n_grid < MIN_PBO_TRIALS:
        return None, f"PBO non calculable ({n_grid} essais < {MIN_PBO_TRIALS})", len(common)
    if not any_finite:
        return None, "PBO non calculable (aucun Sharpe fini parmi les essais)", len(common)
    pbo = _finite_or_none(validation_dsr.pbo_cscv(common.to_numpy()))
    if pbo is None:
        return None, f"PBO non calculable ({len(common)} mois communs aux essais)", len(common)
    return pbo, None, len(common)


def _grid_stats(name: str, grid: list[dict], inputs: _GateInputs, n_used: int, train_end: pd.Timestamp):
    """Simule chaque variante de la grille ; rend (mesures, rendements et rotations de ``grid[0]``)."""
    excess: list[pd.Series] = []
    srs = []
    first = None
    for k, params in enumerate(grid):
        rb, ro, turns, breaches = _simulate(name, params, inputs)
        ex = ro - rb
        excess.append(ex)
        srs.append(validation_dsr.sharpe_ratio(ex.to_numpy(), periods=1))
        if k == 0:
            first = (ro, turns, breaches, ex.to_numpy())
    ro, turns, breaches, ex0 = first
    finite = [s for s in srs if math.isfinite(s)]
    var_sr = float(np.var(finite, ddof=1)) if len(finite) >= 2 else 0.0
    n_obs, skew, kurt = validation_dsr.moments(ex0)
    dsr = validation_dsr.deflated_sharpe(srs[0], n_used, n_obs, skew, kurt, var_sr)
    pbo, pbo_na, n_common = _pbo(excess, len(grid), any_finite=bool(finite))
    stats = _GateStats(
        dsr=dsr,
        sharpe_ann=validation_dsr.sharpe_ratio(ex0, periods=12),
        pbo=pbo,
        pbo_na=pbo_na,
        breaches=breaches,
        n_train=len(inputs.returns),
        n_used=n_used,
        n_grid=len(grid),
        n_common=n_common,
        train_end=train_end,
    )
    return stats, ro, turns


def _failures(stats: _GateStats, cfg: EvolutionConfig) -> list[str]:
    """Conditions de la porte non tenues (vide ssi la porte passe : un PBO non calculable compte comme un échec)."""
    g = cfg.gate
    why = []
    if not (math.isfinite(stats.dsr) and stats.dsr >= g.min_dsr):
        why.append(
            f"DSR {_fmt(stats.dsr)} < {g.min_dsr:.2f}"
            if math.isfinite(stats.dsr)
            else "aucun effet mesurable (DSR n/d)"
        )
    if stats.n_train < g.min_train_months:
        why.append(f"{stats.n_train} mois d'entraînement < {g.min_train_months}")
    if g.require_no_limit_breach and stats.breaches:
        why.append(f"limites dépassées : {', '.join(stats.breaches)}")
    if stats.pbo_na is not None:
        why.append(stats.pbo_na)
    elif stats.pbo > g.max_pbo:  # pbo_na None : PBO calculé
        why.append(f"PBO {_fmt(stats.pbo)} > {g.max_pbo:.2f} (sur-ajustement probable)")
    return why


def _verdict_reason(stats: _GateStats, cfg: EvolutionConfig, why: list[str]) -> str:
    g = cfg.gate
    trials = f"{stats.n_used} essais" + (f" dont {stats.n_grid} de cet overlay" if stats.n_used != stats.n_grid else "")
    detail = (
        f"DSR {_fmt(stats.dsr)} (seuil {g.min_dsr:.2f}, {trials}), Sharpe annualisé de l'excès sur la base "
        f"{_fmt(stats.sharpe_ann)}, PBO {_fmt(stats.pbo)} (seuil {g.max_pbo:.2f}, {stats.n_grid} variantes sur "
        f"{stats.n_common} mois communs), {stats.n_train} mois ≤ {stats.train_end.date()} "
        f"(min {g.min_train_months}), coûts {cfg.trading.cost_bps:g} pb par rotation aller simple"
    )
    if stats.breaches and not g.require_no_limit_breach:
        detail += f" ; limites linéaires rétablies par le tick : {', '.join(stats.breaches)}"
    return f"testé, non retenu ({' ; '.join(why)}) : {detail}" if why else f"retenu : {detail}"


def evaluate_gate(  # noqa: PLR0913 - signature publique gelée : replay.py et les tests passent param_grid par position
    overlay_name: str,
    returns: pd.DataFrame,
    train_end,
    base_target: dict[str, float],
    policy: PolicySpec,
    asset_class: dict[str, str],
    cfg: EvolutionConfig,
    param_grid: list[dict] | None = None,
    *,
    months: list | None = None,
    asset_tags: dict[str, list[str]] | None = None,
    need_floor_cad: float | None = None,
    value_cad: float = 100_000.0,
    n_trials_total: int | None = None,
) -> tuple[OverlayState, ComparatorRow]:
    """Évalue l'overlay ``overlay_name`` sur l'historique ≤ ``train_end`` et rend (état de porte, ligne du
    comparateur). ``months`` (optionnel) restreint les mois simulés ; une date > ``train_end`` lève ValueError.
    ``param_grid[0]`` est la configuration évaluée (celle qui serait appliquée) ; les autres sont les essais comptés
    dans le DSR et le PBO.

    ``n_trials_total`` : nombre d'essais compté dans la déflation du Sharpe (DSR). L'appelant doit passer le total
    des essais de **tous** les overlays évalués pour le persona (Σ des tailles de grille), sinon le DSR ne déflate
    que les variantes de cet overlay (défaut). Jamais moins que la grille de cet overlay (on retient le max). La
    variance des Sharpe des essais reste estimée sur les seules variantes de cet overlay (HYPOTHESE).
    ``ComparatorRow.n_trials`` rapporte le nombre effectivement utilisé dans le DSR."""
    if overlay_name not in REGISTRY:
        raise KeyError(f"overlay inconnu : {overlay_name}")
    if n_trials_total is not None and n_trials_total < 1:
        raise ValueError(f"n_trials_total doit être ≥ 1 (reçu {n_trials_total})")
    train_end = pd.Timestamp(train_end)
    if not cfg.overlay(overlay_name).get("enabled", True):
        return _disabled(overlay_name)
    inputs = _GateInputs(
        returns=_train_returns(returns, train_end, months),
        base_target={a: float(base_target[a]) for a in sorted(base_target)},  # ordre canonique (déterminisme)
        policy=policy,
        asset_class=asset_class,
        asset_tags=_catalog_tags(policy.investable) if asset_tags is None else asset_tags,
        cfg=cfg,
        need_floor_cad=need_floor_cad,
        value_cad=value_cad,
    )
    grid = param_grid or default_grid(cfg, overlay_name)
    n_used = max(len(grid), n_trials_total or 0)
    if len(inputs.returns) < _warmup(grid[0]) + 2:
        return _short_history(overlay_name, train_end, len(inputs.returns), n_used)
    stats, ro, turns = _grid_stats(overlay_name, grid, inputs, n_used, train_end)
    why = _failures(stats, cfg)
    passe = not why
    reason = _verdict_reason(stats, cfg, why)
    cagr, mdd = bt_metrics.annualized_return(ro.to_numpy()), bt_metrics.max_drawdown(ro.to_numpy())
    return (
        OverlayState(name=overlay_name, active=passe, gate="passe" if passe else "echoue", gate_reason_fr=reason),
        ComparatorRow(
            name=overlay_name,
            applied=passe,
            n_trials=n_used,
            sharpe=_finite_or_none(stats.sharpe_ann),
            dsr=_finite_or_none(stats.dsr),
            pbo=stats.pbo,
            cagr=_finite_or_none(cagr),
            max_drawdown=_finite_or_none(mdd),
            turnover_ann=float(turns.mean() * 12) if turns.size else None,
            verdict_fr=reason,
        ),
    )
