"""Mesures de performance d'une trajectoire de portefeuille simulée (mois par mois).

Conventions (toutes en décimal, mois de 12 périodes par an) :

- **TWR** (rendement pondéré par le temps) : produit chaîné des rendements mensuels du portefeuille.
  Les flux ayant lieu aux bornes de mois, le TWR ne dépend pas des flux : il mesure la gestion.
- **MWR** (rendement pondéré par les capitaux, TRI) : mesure l'expérience de l'investisseur, flux compris.
- **Flux** : en fin de mois, après le rendement du mois (même convention que
  ``backtest.metrics.wealth_path`` : ``V_t = V_{t-1}(1 + r_t) + flux_t``) ; positif = apport.
- **Drawdown** : calculé sur l'**indice TWR** (produit cumulé de ``1 + r``), jamais sur la valeur en CAD,
  car un apport masquerait une perte et un retrait en créerait une fausse. Perte positive (0,25 = -25 %).
- **Annualisation** : jamais sous 12 mois (on renvoie ``None``).

Le passé décrit le passé : aucune de ces mesures n'est une prévision. SIMULATION SEULEMENT.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

import numpy as np

from ..backtest import metrics as bt_metrics
from ..contracts.evolution import PerfSnapshot

P = 12
_EPS = 1e-12


# --------------------------------------------------------------------------- rendements

def twr_from_returns(r: Sequence[float]) -> float:
    """TWR cumulé : ``Π(1 + r_t) - 1`` (0 si aucune période)."""
    a = np.asarray(r, dtype=float)
    return float(np.prod(1.0 + a) - 1.0) if a.size else 0.0


def annualize(cum: float, months: int) -> float | None:
    """Annualise un rendement cumulé sur ``months`` mois ; ``None`` sous 12 mois (jamais d'extrapolation)."""
    if months < P:
        return None
    g = 1.0 + float(cum)
    return float(g ** (P / months) - 1.0) if g > 0 else -1.0


def cagr(value_start: float, value_end: float, months: int) -> float | None:
    """Taux de croissance annuel composé entre deux valeurs, sans flux intermédiaire ; ``None`` sous 12 mois."""
    if months < P or value_start <= 0:
        return None
    return annualize(value_end / value_start - 1.0, months)


def _npv(i: float, cf: np.ndarray, t: np.ndarray) -> float:
    return float(np.sum(cf / (1.0 + i) ** t))


def mwr(cashflows_by_month: Sequence[float], final_value: float, lo: float = -0.99, hi: float = 10.0,
        tol: float = 1e-12, max_iter: int = 500) -> float | None:
    """TRI mensuel annualisé (rendement pondéré par les capitaux).

    Convention : ``cashflows_by_month[k]`` est l'**apport net dans le portefeuille** au temps ``k``
    (début du mois ``k`` = fin du mois ``k-1``), positif = apport, négatif = retrait ; l'élément 0 contient
    la valeur initiale. ``final_value`` est la valeur au temps ``T = len(cashflows_by_month)``, nette d'un
    éventuel flux de ce même instant. Du point de vue de l'investisseur, les apports sont des sorties :
    on résout ``-Σ c_k (1+i)^-k + V_T (1+i)^-T = 0`` par bissection sur ``i ∈ [lo, hi]`` (mensuel).

    ``None`` si moins de 12 mois (pas d'annualisation) ou si la fonction ne change pas de signe sur
    l'intervalle (TRI indéfini ou non unique dans la plage).
    """
    c = np.asarray(cashflows_by_month, dtype=float)
    T = c.size
    if T < P:
        return None
    cf = np.concatenate([-c, [float(final_value)]])
    t = np.arange(T + 1, dtype=float)
    f_lo, f_hi = _npv(lo, cf, t), _npv(hi, cf, t)
    if f_lo == 0:
        return float((1 + lo) ** P - 1)
    if f_hi == 0:
        return float((1 + hi) ** P - 1)
    if np.sign(f_lo) == np.sign(f_hi):
        return None
    a, b = lo, hi
    for _ in range(max_iter):
        m = 0.5 * (a + b)
        f_m = _npv(m, cf, t)
        if f_m == 0 or (b - a) < tol:
            break
        if np.sign(f_m) == np.sign(f_lo):
            a, f_lo = m, f_m
        else:
            b = m
    i = 0.5 * (a + b)
    return float((1.0 + i) ** P - 1.0)


# --------------------------------------------------------------------------- drawdowns

def twr_index(r: Sequence[float], base: float = 1.0) -> np.ndarray:
    """Indice TWR ``[base, base(1+r_1), ...]`` (longueur ``len(r) + 1``, la base comprise)."""
    a = np.asarray(r, dtype=float)
    return base * np.concatenate([[1.0], np.cumprod(1.0 + a)])


def high_water_mark(values: Sequence[float]) -> np.ndarray:
    """Plus haut historique courant (sommet atteint jusqu'à chaque date, celle-ci comprise)."""
    v = np.asarray(values, dtype=float)
    return np.maximum.accumulate(v) if v.size else v


def drawdowns(values: Sequence[float]) -> np.ndarray:
    """``1 - v / HWM`` (perte positive). À appliquer à un **indice TWR**, pas à une valeur avec flux :
    ``drawdowns(twr_index(r))[1:]`` est identique à ``backtest.metrics.drawdown_series(r)``."""
    v = np.asarray(values, dtype=float)
    if not v.size:
        return v
    hwm = high_water_mark(v)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(hwm > 0, 1.0 - v / hwm, 0.0)
    return np.clip(dd, 0.0, None)


def drawdown_vs_invested(values: Sequence[float], invested: Sequence[float]) -> np.ndarray:
    """Perte par rapport aux apports nets cumulés : ``max(0, 1 - V / investi)`` (0 si rien d'investi).

    Lecture « investisseur » (combien sous ma mise ?), complémentaire du drawdown TWR (gestion)."""
    v = np.asarray(values, dtype=float)
    inv = np.asarray(invested, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(inv > 0, 1.0 - v / inv, 0.0)
    return np.clip(dd, 0.0, None)


def months_underwater(index: Sequence[float]) -> tuple[int, int]:
    """(série en cours, plus longue série) de mois consécutifs sous le plus haut de l'indice."""
    dd = drawdowns(index)
    best = cur = 0
    for x in dd:
        cur = cur + 1 if x > _EPS else 0
        best = max(best, cur)
    return int(cur), int(best)


# --------------------------------------------------------------------------- frictions

def cash_drag(weights_path: Sequence[Mapping[str, float]], cash_assets: Sequence[str],
              r_portfolio: Sequence[float], r_cash: Sequence[float]) -> float | None:
    """Coût annualisé approximatif de la liquidité : ``poids moyen en liquidités × (moyenne r_portefeuille -
    moyenne r_liquidités) × 12``.

    Approximation de premier ordre (pas d'attribution exacte : le rendement du portefeuille inclut déjà la
    poche de liquidités, et l'effet de composition est ignoré). Positif = la liquidité a pesé sur le
    rendement. ``None`` si les séries sont vides ou de longueurs différentes.
    """
    rp, rc = np.asarray(r_portfolio, dtype=float), np.asarray(r_cash, dtype=float)
    n = len(weights_path)
    if n == 0 or rp.size != n or rc.size != n:
        return None
    cash = set(cash_assets)
    w_cash = np.array([sum(float(v) for k, v in w.items() if k in cash) for w in weights_path])
    return float(w_cash.mean() * (rp.mean() - rc.mean()) * P)


# --------------------------------------------------------------------------- risque

def risk_contributions(weights: Mapping[str, float], returns_window, beta: float = 0.95) -> dict[str, dict[str, float]]:
    """Contributions au risque (vol d'Euler et CVaR) via ``portfolio.analysis.risk_report``.

    ``returns_window`` : une ``ReturnWindow`` ou un ``DataFrame`` mois × actifs (rendements mensuels CAD) ;
    dans ce dernier cas une fenêtre est construite sans ``data_version`` (``"inconnue"``).
    """
    import pandas as pd

    from ..portfolio.analysis import risk_report
    from ..portfolio.market import ReturnWindow

    if isinstance(returns_window, pd.DataFrame):
        returns_window = ReturnWindow(returns=returns_window, as_of=pd.Timestamp(returns_window.index[-1]),
                                      currency="CAD", data_version="inconnue")
    rep = risk_report(dict(weights), returns_window, beta=beta)
    return {"vol": dict(rep.contrib_vol), "cvar": dict(rep.contrib_cvar)}


# --------------------------------------------------------------------------- suivi incrémental

class PerfTracker:
    """Accumule mois par mois les mesures d'une trajectoire et produit un ``PerfSnapshot``.

    ``initial_value_cad`` est la valeur au début de la trajectoire (temps 0). À chaque ``update`` :
    ``r_portfolio`` est le rendement du mois (hors flux), ``value_end`` la valeur en fin de mois **après**
    le flux ``flow_cad`` (positif = apport). ``invested_cad`` = valeur initiale + Σ flux.
    """

    def __init__(self, initial_value_cad: float, cash_assets: Sequence[str] = ()):
        if initial_value_cad < 0:
            raise ValueError("valeur initiale négative")
        self.initial_value_cad = float(initial_value_cad)
        self.cash_assets = tuple(cash_assets)
        self.months_seen: list[date] = []
        self.returns: list[float] = []
        self.values: list[float] = []
        self.flows: list[float] = []
        self.weights: list[dict[str, float]] = []
        self.cash_returns: list[float] = []
        self.turnover_oneway_cum = 0.0
        self.costs_cad_cum = 0.0

    def update(self, month: date, r_portfolio: float, value_end: float, flow_cad: float = 0.0,
               turnover_oneway: float = 0.0, cost_cad: float = 0.0, weights: Mapping[str, float] | None = None,
               r_cash: float | None = None) -> None:
        if self.months_seen and month <= self.months_seen[-1]:
            raise ValueError(f"mois non croissant : {month} après {self.months_seen[-1]}")
        self.months_seen.append(month)
        self.returns.append(float(r_portfolio))
        self.values.append(float(value_end))
        self.flows.append(float(flow_cad))
        self.weights.append(dict(weights or {}))
        if r_cash is not None:
            self.cash_returns.append(float(r_cash))
        self.turnover_oneway_cum += float(turnover_oneway)
        self.costs_cad_cum += float(cost_cad)

    @property
    def months(self) -> int:
        return len(self.returns)

    def mwr(self) -> float | None:
        """TRI annualisé : flux de fin de mois ``k`` placés au temps ``k+1`` ; le flux du dernier mois est
        retranché de la valeur finale (il a lieu au même instant)."""
        if not self.returns:
            return None
        cf = [self.initial_value_cad, *self.flows[:-1]]
        return mwr(cf, self.values[-1] - self.flows[-1])

    def snapshot(self) -> PerfSnapshot:
        n = self.months
        idx = twr_index(self.returns)
        dd = drawdowns(idx)
        cur_uw, _ = months_underwater(idx)
        twr_cum = float(idx[-1] - 1.0)
        value = self.values[-1] if self.values else self.initial_value_cad
        drag = None
        if self.cash_assets and len(self.cash_returns) == n:
            drag = cash_drag(self.weights, self.cash_assets, self.returns, self.cash_returns)
        return PerfSnapshot(
            months=n,
            value_cad=value,
            invested_cad=self.initial_value_cad + float(sum(self.flows)),
            twr_cum=twr_cum,
            twr_ann=annualize(twr_cum, n),
            mwr_ann=self.mwr(),
            # CAGR d'un dollar placé au départ (indice TWR) : la valeur en CAD mêle les apports.
            cagr=cagr(1.0, float(idx[-1]), n),
            max_drawdown=float(dd.max()) if dd.size else 0.0,
            current_drawdown=float(dd[-1]) if dd.size else 0.0,
            # Plus haut de la valeur en CAD (flux compris), y compris la valeur initiale : information
            # d'affichage seulement ; les drawdowns ci-dessus sont calculés sur l'indice TWR.
            high_water_mark_cad=float(max([self.initial_value_cad, *self.values])),
            months_underwater=cur_uw,
            cash_drag=drag,
            turnover_oneway_cum=self.turnover_oneway_cum,
            costs_cad_cum=self.costs_cad_cum,
        )


def max_drawdown_twr(r: Sequence[float]) -> float:
    """Raccourci : drawdown maximal de l'indice TWR (identique à ``backtest.metrics.max_drawdown``)."""
    a = np.asarray(r, dtype=float)
    return float(bt_metrics.max_drawdown(a)) if a.size else 0.0
