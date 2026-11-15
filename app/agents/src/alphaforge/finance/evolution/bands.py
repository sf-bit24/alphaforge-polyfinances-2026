"""Bandes de tolérance et retour dans les bandes (rééquilibrage par seuils, sans anticipation).

Largeur de bande d'une ligne de cible w* : max(min_abs, min(abs, rel·w*)) — la plus petite des bandes
absolue et relative (Daryanani 2008), avec un plancher pour les très petites cibles.

Pourquoi ne pas utiliser ``portfolio.optimizer.project()`` ici : ``project`` cherche le portefeuille
admissible le plus proche **de la cible** proposée par l'optimiseur ; il ignore les poids dérivés
détenus. Un retour dans les bandes doit au contraire partir **des poids dérivés** et ne déplacer que
le nécessaire (moins de rotation, moins de coûts). La cible w* est déjà admissible (projetée lors de la
décision) ; les modes ci-dessous restent dans l'enveloppe convexe {w dérivé, w*} (half, full) ou ne
déplacent que les lignes en dépassement (edge). Le Judge revérifie les contraintes après l'opération.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

_EPS = 1e-12

TradeMode = Literal["half", "edge", "full"]


def band_width(target_w: float, bands) -> float:
    """Demi-largeur de bande autour de la cible ``target_w`` (en points de poids, fraction)."""
    return max(float(bands.min_abs), min(float(bands.abs), float(bands.rel) * float(target_w)))


def _keys(w: Mapping[str, float], target: Mapping[str, float]) -> list[str]:
    return sorted(set(w) | set(target))


def breaches(w: Mapping[str, float], target: Mapping[str, float], bands) -> list[str]:
    """Actifs (triés) dont |w − w*| dépasse la bande. Une ligne détenue de cible 0 est en dépassement
    dès que w > min_abs (cas particulier de la même règle, la bande valant min_abs)."""
    out = []
    for a in _keys(w, target):
        wa, ta = float(w.get(a, 0.0)), float(target.get(a, 0.0))
        if abs(wa - ta) > band_width(ta, bands) + _EPS:
            out.append(a)
    return out


def _clean(w: dict[str, float]) -> dict[str, float]:
    """Poids >= 0 de somme 1 (corrige l'erreur d'arrondi flottant)."""
    w = {a: (v if v > 0 else 0.0) for a, v in w.items()}
    s = sum(w.values())
    if s <= 0:
        raise ValueError("poids nuls après rééquilibrage")
    return {a: v / s for a, v in w.items()}


def _edge(wd: dict[str, float], tg: dict[str, float], bands, br: list[str]) -> dict[str, float]:
    new = dict(wd)
    for a in br:
        b = band_width(tg[a], bands)
        new[a] = tg[a] + b if wd[a] > tg[a] else max(0.0, tg[a] - b)
    # excédent à redistribuer : > 0 si les lignes en dépassement ont été réduites (on doit acheter ailleurs)
    excess = sum(wd[a] - new[a] for a in br)
    others = [a for a in wd if a not in br]
    if abs(excess) <= _EPS or not others:
        return new
    rest = _absorb_toward_target(new, tg, others, excess)
    if rest > _EPS:
        _absorb_pro_rata(new, others, rest, buying=excess > 0)
    return new


def _absorb_toward_target(new: dict[str, float], tg: dict[str, float], others: list[str], excess: float) -> float:
    """1) Absorbe ``excess`` sur ``others`` (modifie ``new``) au prorata de l'écart à la cible dans le sens utile
    (acheter les sous-pondérées / vendre les sur-pondérées). Renvoie le reliquat non absorbé."""
    if excess > 0:
        room = {a: max(0.0, tg[a] - new[a]) for a in others}
    else:
        room = {a: max(0.0, new[a] - tg[a]) for a in others}
    total_room = sum(room.values())
    take = min(abs(excess), total_room)
    if total_room > _EPS:
        for a in others:
            new[a] += (1 if excess > 0 else -1) * take * room[a] / total_room
    return abs(excess) - take


def _absorb_pro_rata(new: dict[str, float], others: list[str], rest: float, *, buying: bool) -> None:
    """2) Reliquat ``rest`` au prorata des poids (achat) ou des poids restants (vente), jamais en dessous de 0
    (modifie ``new``)."""
    base = {a: new[a] for a in others}
    tot = sum(base.values())
    if tot <= _EPS:
        base, tot = dict.fromkeys(others, 1.0), float(len(others))
    for a in others:
        if buying:
            new[a] += rest * base[a] / tot
        else:
            new[a] -= min(new[a], rest * base[a] / tot)


def rebalance_to_bands(
    w_drift: Mapping[str, float], target: Mapping[str, float], bands, mode: TradeMode | None = None
) -> dict[str, float]:
    """Poids après retour dans les bandes, en partant des poids dérivés ``w_drift``.

    - aucun dépassement : ``w_drift`` inchangé (mêmes valeurs, clés = union avec la cible) ;
    - ``half`` : w + 0,5·(w* − w) pour CHAQUE ligne (combinaison convexe, somme conservée : chaque
      ligne se rapproche de la cible ; une ligne dont l'écart est < 2 × sa bande revient dedans) ;
    - ``full`` : w = w* ;
    - ``edge`` : chaque ligne en dépassement est ramenée exactement au bord de sa bande ; la différence
      nette est absorbée par les autres lignes au prorata de leur écart à la cible dans le sens utile,
      puis, s'il reste un reliquat, au prorata de leur poids.
    Le résultat est toujours >= 0, de somme 1, sur l'union des clés de ``w_drift`` et de ``target``.
    """
    mode = mode or bands.trade_mode
    keys = _keys(w_drift, target)
    wd = {a: float(w_drift.get(a, 0.0)) for a in keys}
    tg = {a: float(target.get(a, 0.0)) for a in keys}
    br = breaches(wd, tg, bands)
    if not br:
        return wd
    if mode == "full":
        return _clean(tg)
    if mode == "half":
        return _clean({a: wd[a] + 0.5 * (tg[a] - wd[a]) for a in keys})
    if mode == "edge":
        return _clean(_edge(wd, tg, bands, br))
    raise ValueError(f"mode de rééquilibrage inconnu : {mode}")
