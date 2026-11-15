"""Flux (apports, retraits), plan de mouvements illustratifs, rotation et coûts.

SIMULATION SEULEMENT : un ``Trade`` est un mouvement illustratif, jamais un ordre.
Conventions : poids = fractions (somme 1) ; montants en CAD ; rotation aller simple = 0,5·Σ|dw|
(convention du backtest), aller-retour = Σ|dw| (convention de l'optimiseur).
"""
from __future__ import annotations

from collections.abc import Mapping

from alphaforge.finance.contracts.evolution import Trade, TradeReason

_EPS = 1e-12


def _keys(*ms: Mapping[str, float]) -> list[str]:
    return sorted(set().union(*ms))


def turnover(w_from: Mapping[str, float], w_to: Mapping[str, float]) -> tuple[float, float]:
    """(aller simple 0,5·Σ|dw|, aller-retour Σ|dw|) sur l'union des clés."""
    two = sum(abs(float(w_to.get(a, 0.0)) - float(w_from.get(a, 0.0))) for a in _keys(w_from, w_to))
    return 0.5 * two, two


def cost_cad(turnover_oneway: float, value_cad: float, cost_bps: float) -> float:
    """Coût d'une opération = rotation aller simple × valeur × cost_bps / 10 000."""
    return float(turnover_oneway) * float(value_cad) * float(cost_bps) / 1e4


def _split(amount: float, weights: dict[str, float]) -> dict[str, float]:
    tot = sum(weights.values())
    if tot <= _EPS:
        return {a: 0.0 for a in weights}
    return {a: amount * v / tot for a, v in weights.items()}


def apply_flow(w: Mapping[str, float], value_cad: float, flow_cad: float, target: Mapping[str, float],
               contribution_first: bool = True) -> tuple[dict[str, float], float]:
    """Applique un flux (positif = apport, négatif = retrait) et renvoie (poids de somme 1, nouvelle valeur).

    La nouvelle valeur est value + flux, ramenée à 0 au minimum (un retrait ne peut dépasser l'actif).
    - ``contribution_first`` et apport : l'argent va d'abord aux lignes sous-pondérées
      (manque = w*·V_nouveau − w·V > 0) au prorata du manque, plafonné au manque ; le reste au prorata
      de la cible.
    - ``contribution_first`` et retrait : pris d'abord sur les lignes sur-pondérées
      (excès = w·V − w*·V_nouveau > 0, plafonné à la ligne) au prorata de l'excès ; le reste au prorata
      des avoirs restants.
    - sinon : apport au prorata de la cible, retrait au prorata des poids actuels.
    Si la nouvelle valeur est nulle, renvoie (poids actuels, 0.0).
    """
    keys = _keys(w, target)
    V = float(value_cad)
    hold = {a: float(w.get(a, 0.0)) * V for a in keys}
    tg = {a: float(target.get(a, 0.0)) for a in keys}
    flow = max(float(flow_cad), -V)
    V_new = V + flow
    if V_new <= _EPS:
        return {a: float(w.get(a, 0.0)) for a in keys}, 0.0
    if flow > 0:
        if contribution_first:
            short = {a: max(0.0, tg[a] * V_new - hold[a]) for a in keys}
            first = min(flow, sum(short.values()))
            add = _split(first, short)
            rest = _split(flow - first, tg)
            delta = {a: add[a] + rest[a] for a in keys}
        else:
            delta = _split(flow, tg)
    elif flow < 0:
        need = -flow
        if contribution_first:
            excess = {a: min(hold[a], max(0.0, hold[a] - tg[a] * V_new)) for a in keys}
            first = min(need, sum(excess.values()))
            take = _split(first, excess)
            left = {a: hold[a] - take[a] for a in keys}
            more = _split(need - first, left)
            delta = {a: -(take[a] + min(left[a], more[a])) for a in keys}
        else:
            delta = {a: -v for a, v in _split(need, hold).items()}
    else:
        delta = {a: 0.0 for a in keys}
    new = {a: max(0.0, hold[a] + delta[a]) for a in keys}
    s = sum(new.values())
    return {a: v / s for a, v in new.items()}, V_new


def plan_trades(w_from: Mapping[str, float], w_to: Mapping[str, float], value_cad: float, reason: TradeReason,
                min_trade_cad: float = 0.0) -> tuple[list[Trade], dict[str, float]]:
    """Mouvements illustratifs pour passer de ``w_from`` à ``w_to`` sur une valeur ``value_cad``.

    Une ligne dont |dw|·valeur < ``min_trade_cad`` n'est pas déplacée (elle reste à w_from). Le résidu de
    somme ainsi créé est absorbé par la ligne au plus gros mouvement conservé, pour que les poids
    effectifs somment à 1. Si aucune ligne n'est conservée, renvoie ([], w_from).
    Renvoie (mouvements triés par asset_id, poids effectifs sur l'union des clés).
    """
    keys = _keys(w_from, w_to)
    wf = {a: float(w_from.get(a, 0.0)) for a in keys}
    wt = {a: float(w_to.get(a, 0.0)) for a in keys}
    V = float(value_cad)
    kept = [a for a in keys if abs(wt[a] - wf[a]) > _EPS and abs(wt[a] - wf[a]) * V >= float(min_trade_cad)]
    if not kept:
        return [], wf
    eff = {a: (wt[a] if a in kept else wf[a]) for a in keys}
    resid = 1.0 - sum(eff.values())
    if abs(resid) > _EPS:
        big = max(kept, key=lambda a: (abs(wt[a] - wf[a]), a))
        eff[big] = max(0.0, eff[big] + resid)
    trades = []
    for a in kept:
        dw = eff[a] - wf[a]
        trades.append(Trade(asset_id=a, w_from=wf[a], w_to=eff[a], dw=dw, amount_cad=round(dw * V, 2),
                            reason=reason))
    return trades, eff
