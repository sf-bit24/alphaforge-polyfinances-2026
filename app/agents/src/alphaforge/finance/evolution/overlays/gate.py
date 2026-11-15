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

import numpy as np
import pandas as pd

from ...backtest import metrics as M
from ...backtest import validation_dsr as V
from ...contracts import PolicySpec
from ...contracts.evolution import ComparatorRow, OverlayState
from ..config import EvolutionConfig
from .base import (
    EPS,
    _add,
    _catalog_tags,
    context_from,
    equity_share,
    linear_breaches,
    simple_bounds,
    update_stop_levels,
)
from .registry import REGISTRY

MIN_PBO_TRIALS = 4      # CSCV : au moins 4 essais, sinon PBO non calculable et la porte échoue


def _variants(v: int | float, wide: bool) -> list[int | float]:
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


def _simulate(name: str, params: dict, r: pd.DataFrame, base_target: dict[str, float], policy: PolicySpec,
              asset_class: dict[str, str], asset_tags, cfg: EvolutionConfig, need_floor_cad, value0: float):
    """Retourne (rendements base, rendements overlay, rotations overlay, dépassements nouveaux)."""
    ov = REGISTRY[name](params)
    cost = cfg.trading.cost_bps / 1e4
    rr_all = r.fillna(0.0)
    base_breach = set(linear_breaches(base_target, policy, asset_class, asset_tags))
    warm = _warmup(params)
    w_b, w_o = dict(base_target), dict(base_target)
    entry, peaks = {}, {}
    value = value0
    rb, ro, turns, breaches = [], [], [], set()
    for i in range(warm - 1, len(r) - 1):
        as_of = r.index[i]
        ctx = context_from(policy, as_of, r.iloc[: i + 1], base_target, w_o, asset_class, cfg=cfg,
                           asset_tags=asset_tags, entry_prices=entry, peaks=peaks,
                           need_floor_cad=need_floor_cad, value_cad=value)
        sig = ov.compute(ctx)
        tgt = simple_bounds(ctx, _add(base_target, sig.delta)) if sig.delta else dict(base_target)
        new = set(linear_breaches(tgt, policy, asset_class, asset_tags)) - base_breach
        eq = equity_share(tgt, ctx.equity_assets)
        if eq < ctx.e_min - 1e-6 or eq > ctx.e_cap + 1e-6:
            new.add("alloc.growth")
        breaches |= new
        t_o, t_b = _turnover(tgt, w_o), _turnover(base_target, w_b)
        entry, peaks = update_stop_levels(r.iloc[: i + 1], w_o, tgt, ctx.satellites, entry, peaks)
        nxt = rr_all.iloc[i + 1]
        w_o, g_o = _drift(tgt, nxt)
        w_b, g_b = _drift(base_target, nxt)
        ro.append(g_o - t_o * cost)
        rb.append(g_b - t_b * cost)
        turns.append(t_o)
        value *= 1 + ro[-1]
    idx = r.index[warm: len(r)]
    return pd.Series(rb, index=idx), pd.Series(ro, index=idx), np.asarray(turns), sorted(breaches)


def _disabled(name: str) -> tuple[OverlayState, ComparatorRow]:
    reason = "désactivé par evolution.yaml (enabled: false) : comparateur seulement, jamais appliqué"
    return (OverlayState(name=name, active=False, gate="desactive", gate_reason_fr=reason),
            ComparatorRow(name=name, applied=False, n_trials=1, sharpe=None, dsr=None, pbo=None, cagr=None,
                          max_drawdown=None, turnover_ann=None, verdict_fr=reason))


def _fmt(x, f=".2f") -> str:
    return "n/d" if x is None or (isinstance(x, float) and not math.isfinite(x)) else format(x, f)


def evaluate_gate(overlay_name: str, returns: pd.DataFrame, train_end, base_target: dict[str, float],
                  policy: PolicySpec, asset_class: dict[str, str], cfg: EvolutionConfig,
                  param_grid: list[dict] | None = None, *, months: list | None = None,
                  asset_tags: dict[str, list[str]] | None = None, need_floor_cad: float | None = None,
                  value_cad: float = 100_000.0, n_trials_total: int | None = None
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
    if months is not None:
        late = [pd.Timestamp(m) for m in months if pd.Timestamp(m) > train_end]
        if late:
            raise ValueError(f"porte hors échantillon violée : mois {late[0].date()} > train_end {train_end.date()}")
        r = returns.loc[returns.index.isin(pd.DatetimeIndex(months))]
    else:
        r = returns.loc[returns.index <= train_end]
    if len(r.index) and r.index.max() > train_end:          # garde-fou : jamais de mois après train_end
        raise ValueError("porte hors échantillon violée : données après train_end")
    r = r.sort_index()
    if asset_tags is None:
        asset_tags = _catalog_tags(policy.investable)
    base_target = {a: float(base_target[a]) for a in sorted(base_target)}   # ordre canonique (déterminisme)
    grid = param_grid or default_grid(cfg, overlay_name)
    n_used = max(len(grid), n_trials_total or 0)
    n_train = len(r)
    if n_train < _warmup(grid[0]) + 2:
        reason = f"historique insuffisant avant {train_end.date()} ({n_train} mois) : testé, non retenu"
        return (OverlayState(name=overlay_name, active=False, gate="echoue", gate_reason_fr=reason),
                ComparatorRow(name=overlay_name, applied=False, n_trials=n_used, sharpe=None, dsr=None,
                              cagr=None, max_drawdown=None, turnover_ann=None, verdict_fr=reason))

    excess: list[pd.Series] = []
    srs, first = [], None
    for k, params in enumerate(grid):
        rb, ro, turns, breaches = _simulate(overlay_name, params, r, base_target, policy, asset_class, asset_tags,
                                            cfg, need_floor_cad, value_cad)
        ex = ro - rb
        excess.append(ex)
        srs.append(V.sharpe_ratio(ex.to_numpy(), periods=1))
        if k == 0:
            first = (ro, turns, breaches, ex.to_numpy())
    ro, turns, breaches, ex0 = first
    finite = [s for s in srs if math.isfinite(s)]
    var_sr = float(np.var(finite, ddof=1)) if len(finite) >= 2 else 0.0
    n_obs, skew, kurt = V.moments(ex0)
    dsr = V.deflated_sharpe(srs[0], n_used, n_obs, skew, kurt, var_sr)
    # PBO : variantes alignées sur leurs mois COMMUNS (jointure interne sur les dates ; les préchauffages diffèrent)
    common = pd.concat(excess, axis=1, join="inner").dropna(how="any")
    pbo, pbo_na = None, None
    if len(grid) < MIN_PBO_TRIALS:
        pbo_na = f"PBO non calculable ({len(grid)} essais < {MIN_PBO_TRIALS})"
    elif not finite:
        pbo_na = "PBO non calculable (aucun Sharpe fini parmi les essais)"
    else:
        p = V.pbo_cscv(common.to_numpy())
        pbo = p if math.isfinite(p) else None
        if pbo is None:
            pbo_na = f"PBO non calculable ({len(common)} mois communs aux essais)"
    sharpe_ann = V.sharpe_ratio(ex0, periods=12)
    g = cfg.gate
    ok_dsr = math.isfinite(dsr) and dsr >= g.min_dsr
    ok_len = n_train >= g.min_train_months
    ok_lim = not (g.require_no_limit_breach and breaches)
    ok_pbo = pbo is not None and pbo <= g.max_pbo           # exigé : non calculable = échec
    passe = ok_dsr and ok_len and ok_lim and ok_pbo
    why = []
    if not ok_dsr:
        why.append(f"DSR {_fmt(dsr)} < {g.min_dsr:.2f}" if math.isfinite(dsr) else "aucun effet mesurable (DSR n/d)")
    if not ok_len:
        why.append(f"{n_train} mois d'entraînement < {g.min_train_months}")
    if not ok_lim:
        why.append(f"limites dépassées : {', '.join(breaches)}")
    if pbo_na is not None:
        why.append(pbo_na)
    elif not ok_pbo:
        why.append(f"PBO {_fmt(pbo)} > {g.max_pbo:.2f} (sur-ajustement probable)")
    trials = f"{n_used} essais" + (f" dont {len(grid)} de cet overlay" if n_used != len(grid) else "")
    detail = (f"DSR {_fmt(dsr)} (seuil {g.min_dsr:.2f}, {trials}), Sharpe annualisé de l'excès sur la base "
              f"{_fmt(sharpe_ann)}, PBO {_fmt(pbo)} (seuil {g.max_pbo:.2f}, {len(grid)} variantes sur "
              f"{len(common)} mois communs), {n_train} mois ≤ {train_end.date()} (min {g.min_train_months}), "
              f"coûts {cfg.trading.cost_bps:g} pb par rotation aller simple")
    if breaches and ok_lim:
        detail += f" ; limites linéaires rétablies par le tick : {', '.join(breaches)}"
    reason = f"retenu : {detail}" if passe else f"testé, non retenu ({' ; '.join(why)}) : {detail}"
    cagr = M.annualized_return(ro.to_numpy())
    mdd = M.max_drawdown(ro.to_numpy())
    return (OverlayState(name=overlay_name, active=passe, gate="passe" if passe else "echoue", gate_reason_fr=reason),
            ComparatorRow(name=overlay_name, applied=passe, n_trials=n_used,
                          sharpe=sharpe_ann if math.isfinite(sharpe_ann) else None,
                          dsr=dsr if math.isfinite(dsr) else None, pbo=pbo,
                          cagr=cagr if math.isfinite(cagr) else None, max_drawdown=mdd if math.isfinite(mdd) else None,
                          turnover_ann=float(turns.mean() * 12) if turns.size else None, verdict_fr=reason))
