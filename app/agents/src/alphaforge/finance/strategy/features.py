"""Indicateurs par titre calculés sur le jeu de départ (bibliothèque standard, point-in-time, sûr en CI).

Définitions alignées sur FTSE Russell Global Factor Index Series Ground Rules v8.8 (strategy.yaml#features) :
- volatilité : écart type des rendements hebdomadaires (clôture ajustée du mercredi) sur 5 ans, annualisé (§5.7) ;
- bêta : covariance / variance des rendements quotidiens sur 2 ans contre l'indice local, XIU.TO ou SPY (§5.9) ;
- corrélation au cœur : rendements hebdomadaires en CAD contre 50 % XIU.TO + 50 % SPY ;
- rendement du dividende sur 12 mois (§5.8), liquidité (valeur médiane échangée sur 63 séances, CAD) ;
- momentum sur douze mois hors dernier mois (§5.3) : AFFICHÉ en sensibilité, jamais dans le score ;
- baisse maximale sur la fenêtre du starter (repli quand l'historique long du moteur n'est pas disponible).

Aucune donnée postérieure à ``as_of`` n'est lue. Les jours fériés TSX et NYSE diffèrent : les rendements
hebdomadaires (même mercredi pour tous) évitent d'aligner des séances ; le bêta quotidien n'utilise que les
dates communes au titre et à son indice. Simulation seulement.
"""

from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

from alphaforge import starter

from .config import StrategyConfig, load_strategy


def _wednesdays(as_of: str, weeks: int) -> list[str]:
    d = date.fromisoformat(as_of)
    d -= timedelta(days=(d.weekday() - 2) % 7)  # dernier mercredi <= as_of
    return [(d - timedelta(weeks=i)).isoformat() for i in range(weeks, -1, -1)]


def _price_on_or_before(rows, iso: str):
    lo, hi, best = 0, len(rows) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if rows[mid].date <= iso:
            best, lo = rows[mid], mid + 1
        else:
            hi = mid - 1
    return best


def weekly_returns(ticker: str, as_of: str, weeks: int, cad: bool = False) -> list[tuple[str, float]]:
    rows = starter.daily(ticker, as_of)
    asset = starter.universe().get(ticker)
    if not rows or asset is None:
        return []
    ccy = asset.currency
    pts = []
    for w in _wednesdays(as_of, weeks):
        r = _price_on_or_before(rows, w)
        if r is None or r.date < rows[0].date:
            continue
        px = r.adj_close
        if cad and ccy != "CAD":
            fx = starter.usdcad_on_or_before(r.date)
            if fx is None:
                continue
            px *= fx
        pts.append((w, r.date, px))
    out = []
    for (_, d0, p0), (w1, d1, p1) in zip(pts, pts[1:], strict=False):
        if d1 != d0 and p0 > 0:  # pas de rendement si aucune séance entre deux mercredis
            out.append((w1, p1 / p0 - 1.0))
    return out


def volatility(ticker: str, as_of: str, cfg: StrategyConfig) -> float | None:
    r = [x for _, x in weekly_returns(ticker, as_of, cfg.features.vol_weeks)]
    if len(r) < cfg.features.vol_min_obs:
        return None
    return statistics.stdev(r) * math.sqrt(52)


def _daily_returns(ticker: str, as_of: str) -> dict[str, float]:
    rows = starter.daily(ticker, as_of)
    return {b.date: b.adj_close / a.adj_close - 1.0 for a, b in zip(rows, rows[1:], strict=False) if a.adj_close > 0}


def beta(ticker: str, as_of: str, cfg: StrategyConfig) -> tuple[float | None, str]:
    asset = starter.universe().get(ticker)
    if asset is None:  # titre hors du jeu de départ (ex. ajouté par le data lake) : indicateur absent, pas d'erreur
        return None, "?"
    ccy = asset.currency
    bench = cfg.features.local_index.get(ccy, "SPY")
    a, b = _daily_returns(ticker, as_of), _daily_returns(bench, as_of)
    common = sorted(set(a) & set(b))[-cfg.features.beta_days :]
    if len(common) < cfg.features.beta_min_obs:
        return None, bench
    x, y = [b[d] for d in common], [a[d] for d in common]
    var = statistics.variance(x)
    return (statistics.covariance(x, y) / var if var > 0 else None), bench


def corr_core(ticker: str, as_of: str, cfg: StrategyConfig) -> float | None:
    weeks = cfg.features.corr_weeks
    own = dict(weekly_returns(ticker, as_of, weeks, cad=True))
    comps = {t: dict(weekly_returns(t, as_of, weeks, cad=True)) for t in cfg.features.core}
    dates = sorted(set(own).intersection(*[set(v) for v in comps.values()]))
    if len(dates) < cfg.features.vol_min_obs:
        return None
    core = [sum(w * comps[t][d] for t, w in cfg.features.core.items()) for d in dates]
    return statistics.correlation([own[d] for d in dates], core)


def max_drawdown(ticker: str, as_of: str, start: str | None = None) -> float | None:
    rows = starter.daily(ticker, as_of, start)
    if len(rows) < 2:
        return None
    peak, mdd = rows[0].adj_close, 0.0
    for r in rows:
        peak = max(peak, r.adj_close)
        if peak > 0:
            mdd = max(mdd, 1.0 - r.adj_close / peak)
    return mdd


def momentum(ticker: str, as_of: str, cfg: StrategyConfig) -> float | None:
    long_m, skip_m = cfg.features.momentum_months
    rows = starter.daily(ticker, as_of)
    d = date.fromisoformat(as_of)
    start_iso = (d - timedelta(days=round(30.44 * long_m))).isoformat()
    if not rows or rows[0].date > start_iso:  # historique trop court : pas de momentum
        return None
    p_end = _price_on_or_before(rows, (d - timedelta(days=round(30.44 * skip_m))).isoformat())
    p_start = _price_on_or_before(rows, start_iso)
    if p_end is None or p_start is None or p_start.adj_close <= 0:
        return None
    return p_end.adj_close / p_start.adj_close - 1.0


def stock_features(ticker: str, as_of: str, cfg: StrategyConfig | None = None) -> tuple[dict, dict, dict]:
    """(valeurs, statuts, détails) pour un titre. Statut FAIT : calcul direct sur le jeu de départ daté."""
    cfg = cfg or load_strategy()
    b, bench = beta(ticker, as_of, cfg)
    vals = {
        "vol": volatility(ticker, as_of, cfg),
        "beta": b,
        "corr_core": corr_core(ticker, as_of, cfg),
        "dividend_yield": starter.dividend_yield_ttm(ticker, as_of),
        "liquidity_cad": starter.median_dollar_volume_cad(ticker, as_of, cfg.features.liquidity_days),
        "mdd_short": max_drawdown(ticker, as_of),
        "momentum": momentum(ticker, as_of, cfg),
    }
    status = {k: "FAIT" for k, v in vals.items() if v is not None}
    first = starter.daily(ticker, as_of)
    details = {"beta_index": bench, "window_start": first[0].date if first else None, "as_of": as_of}
    return vals, status, details
