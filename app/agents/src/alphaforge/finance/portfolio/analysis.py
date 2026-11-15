"""F3 — Outils d'analyse d'un portefeuille (lentilles Timeline, Risque, Diversité, Contraintes).

Fonctions déterministes ; chaque chiffre est recalculable et devient un ``Fact`` sourcé.
Les mesures reprennent celles de l'engine (research/backtest/engine/metrics.py) pour que
l'analyse et le Judge (F4) mesurent exactement la même chose.
Les rendements historiques décrivent le passé : ce ne sont pas des prévisions.
SIMULATION SEULEMENT.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from ..contracts import PolicySpec
from ..observability.telemetry import traced_tool
from ._engine import bt_data, bt_metrics
from .market import ReturnWindow

P = 12

# Épisodes historiques (fenêtres mensuelles inclusives). Un épisode n'est calculé que si
# tous les actifs ont des données sur toute la fenêtre ; sinon il est déclaré « non couvert ».
STRESS_EPISODES: dict[str, tuple[str, str, str]] = {
    "2022_taux": ("2022-01", "2022-12", "Hausse des taux 2022 : actions et obligations en baisse"),
    "2020_covid": ("2020-02", "2020-03", "Choc COVID-19"),
    "2008_crise": ("2007-11", "2009-02", "Crise financière mondiale"),
    "2000_bulle": ("2000-09", "2002-09", "Éclatement de la bulle technologique"),
    "1973_choc": ("1973-01", "1974-09", "Choc pétrolier et stagflation"),
}


def _w(weights: dict[str, float], assets: list[str]) -> np.ndarray:
    extra = set(weights) - set(assets)
    if extra:
        raise KeyError(f"poids sur des actifs hors fenêtre : {sorted(extra)}")
    return np.array([float(weights.get(a, 0.0)) for a in assets])


def portfolio_returns(weights: dict[str, float], returns: pd.DataFrame) -> pd.Series:
    """Rendements mensuels d'un portefeuille rééquilibré chaque mois vers ``weights``."""
    return returns @ _w(weights, list(returns.columns))


# --------------------------------------------------------------------------- Risque

@dataclass
class RiskReport:
    vol_ann: float
    hist_return_ann: float              # passé, pas une prévision
    var_m: float                        # VaR mensuelle historique (perte positive)
    cvar_m: float                       # CVaR mensuelle historique (perte positive)
    cdar: float                         # CDaR sur le drawdown composé
    max_drawdown: float                 # drawdown composé (engine)
    worst_12m: float
    recovery_months: float
    beta: float
    contrib_vol: dict[str, float]       # somme = vol_ann
    contrib_cvar: dict[str, float]      # somme = cvar_m
    n_obs: int
    window: tuple[str, str]


def cdar_compounded(r: np.ndarray, beta: float) -> float:
    dd = bt_metrics.drawdown_series(r)
    q = np.quantile(dd, beta, method="higher")
    return float(dd[dd >= q].mean())


@traced_tool("portfolio.risk_report")
def risk_report(weights: dict[str, float], win: ReturnWindow, beta: float = 0.95) -> RiskReport:
    R = win.returns
    assets = list(R.columns)
    w = _w(weights, assets)
    r = (R @ w).to_numpy()
    var_m, cvar_m = bt_metrics.var_cvar(r, alpha=1 - beta)

    cov = np.cov(R.to_numpy(), rowvar=False, ddof=1)
    sigma_m = float(np.sqrt(w @ cov @ w))
    mrc = cov @ w / sigma_m if sigma_m > 0 else np.zeros_like(w)
    contrib_vol = {a: float(w[i] * mrc[i] * np.sqrt(P)) for i, a in enumerate(assets)}

    q = np.quantile(r, 1 - beta, method="lower")      # même définition que bt_metrics.var_cvar
    tail = r <= q
    tail_ret = R.to_numpy()[tail] * w
    contrib_cvar = {a: float(-tail_ret[:, i].mean()) for i, a in enumerate(assets)}

    return RiskReport(
        vol_ann=bt_metrics.volatility(r), hist_return_ann=bt_metrics.annualized_return(r),
        var_m=var_m, cvar_m=cvar_m, cdar=cdar_compounded(r, beta),
        max_drawdown=bt_metrics.max_drawdown(r), worst_12m=bt_metrics.worst_window_return(r, 12),
        recovery_months=bt_metrics.recovery_months(r), beta=beta, contrib_vol=contrib_vol,
        contrib_cvar=contrib_cvar, n_obs=win.n_obs,
        window=(str(win.start.date()), str(win.end.date())))


# --------------------------------------------------------------------------- Diversité

@dataclass
class DiversificationReport:
    effective_n_weights: float          # 1 / Σ w²
    effective_n_risk: float             # 1 / Σ (part de risque)² sur les parts positives
    diversification_ratio: float        # Σ w σ_i / σ_p
    clusters: list[dict]                # {"assets": [...], "weight": x, "avg_corr": ρ}
    corr_threshold: float


@traced_tool("portfolio.diversification_report")
def diversification_report(weights: dict[str, float], win: ReturnWindow,
                           corr_threshold: float = 0.7) -> DiversificationReport:
    R = win.returns
    assets = list(R.columns)
    w = _w(weights, assets)
    cov = np.cov(R.to_numpy(), rowvar=False, ddof=1)
    sig = np.sqrt(np.diag(cov))
    sp = float(np.sqrt(w @ cov @ w))
    share = (w * (cov @ w)) / (sp ** 2) if sp > 0 else np.zeros_like(w)
    pos = share[share > 0]

    held = [a for a, x in zip(assets, w, strict=True) if x > 1e-6]
    clusters = []
    if len(held) >= 2:
        corr = R[held].corr().to_numpy()
        dist = np.sqrt(np.clip(0.5 * (1 - corr), 0, None))    # distance de López de Prado
        np.fill_diagonal(dist, 0)
        labels = fcluster(linkage(squareform(dist, checks=False), "average"),
                          t=np.sqrt(0.5 * (1 - corr_threshold)), criterion="distance")
        for lab in sorted(set(labels)):
            members = [a for a, lbl in zip(held, labels, strict=True) if lbl == lab]
            idx = [held.index(a) for a in members]
            sub = corr[np.ix_(idx, idx)]
            avg = float(sub[np.triu_indices(len(idx), 1)].mean()) if len(idx) > 1 else 1.0
            clusters.append({"assets": members, "weight": float(sum(weights[a] for a in members)),
                             "avg_corr": avg})
    elif held:
        clusters = [{"assets": held, "weight": float(weights[held[0]]), "avg_corr": 1.0}]
    clusters.sort(key=lambda c: -c["weight"])

    return DiversificationReport(
        effective_n_weights=float(1 / np.sum(w ** 2)),
        effective_n_risk=float(1 / np.sum((pos / pos.sum()) ** 2)) if pos.size else 0.0,
        diversification_ratio=float(w @ sig / sp) if sp > 0 else 0.0,
        clusters=clusters, corr_threshold=corr_threshold)


# --------------------------------------------------------------------------- Look-through

@dataclass
class LookthroughReport:
    exposures: dict[str, float]         # tag -> part du portefeuille
    by_asset: dict[str, dict[str, float]]
    unknown: dict[str, list[str]]       # tag -> actifs larges sans donnée (comptés 0)
    hypotheses: dict[str, list[str]]    # tag -> actifs dont l'exposition est une HYPOTHESE


@traced_tool("portfolio.lookthrough_report")
def lookthrough_report(weights: dict[str, float], policy: PolicySpec, tags: list[str],
                       as_of=None) -> LookthroughReport:
    assets = [a for a in policy.investable]
    w = _w(weights, assets)
    catalog = bt_data.load_assets()
    out, by_asset, unknown, hyp = {}, {}, {}, {}
    for tag in tags:
        ov = {a: {tag: o[tag].value} for a, o in policy.exposure_overrides.items()
              if tag in o and a in assets}
        v = bt_data.exposure_vector(assets, tag, date=as_of, overrides=ov)
        out[tag] = float(v @ w)
        by_asset[tag] = {a: float(x) for a, x in zip(assets, v, strict=True) if x > 0}
        unknown[tag] = [a for a, x in zip(assets, v, strict=True)
                        if x == 0 and a not in ov and {"broad_market", "tech_heavy"} & set(catalog.at[a, "tag_list"])
                        and not (a == "US_MKT" or catalog.at[a, "proxy_for_ticker"] == "US_MKT")]
        hyp[tag] = [a for a, o in policy.exposure_overrides.items()
                    if tag in o and o[tag].status == "HYPOTHESE" and a in assets]
    return LookthroughReport(out, by_asset, unknown, hyp)


# --------------------------------------------------------------------------- Stress

@dataclass
class StressResult:
    episode: str
    label_fr: str
    start: str
    end: str
    covered: bool
    period_return: float | None = None  # rendement composé sur l'épisode
    max_drawdown: float | None = None
    loss_cad_per_100k: float | None = None
    reason: str | None = None


@traced_tool("portfolio.stress_report")
def stress_report(weights: dict[str, float], currency: str = "CAD",
                  episodes: dict[str, tuple[str, str, str]] | None = None) -> list[StressResult]:
    held = [a for a, x in weights.items() if x > 1e-9]
    w = np.array([weights[a] for a in held])
    out = []
    for key, (s, e, label) in (episodes or STRESS_EPISODES).items():
        start, end = bt_data.to_month_end(s), bt_data.to_month_end(e)
        try:
            with warnings.catch_warnings():   # la couverture est rapportée explicitement ci-dessous
                warnings.simplefilter("ignore", UserWarning)
                df = bt_data.load_returns(held, start=start, end=end, currency=currency)
        except Exception as exc:  # pragma: no cover - dépend des données
            out.append(StressResult(key, label, s, e, False, reason=str(exc)))
            continue
        months = pd.date_range(start, end, freq="ME")
        if len(df) < len(months) or df.index[0] > start:
            info = df.attrs.get("info") or {}
            out.append(StressResult(key, label, s, e, False,
                                    reason=f"historique insuffisant ({len(df)}/{len(months)} mois) ; {info}"))
            continue
        r = (df[held] @ w).to_numpy()
        g = float(np.prod(1 + r) - 1)
        out.append(StressResult(key, label, s, e, True, g, bt_metrics.max_drawdown(r),
                                round(-100_000 * min(g, 0.0), 2)))
    return out


# --------------------------------------------------------------------------- Timeline

@dataclass
class HorizonReport:
    horizon_years: float
    n_windows: int                      # fenêtres glissantes mensuelles (chevauchantes)
    worst: float | None
    p05: float | None
    median: float | None
    share_negative: float | None
    history: tuple[str, str] | None
    note: str


@traced_tool("portfolio.horizon_report")
def horizon_report(weights: dict[str, float], horizon_years: float, as_of,
                   currency: str = "CAD") -> HorizonReport:
    """Distribution historique des rendements composés sur l'horizon (fenêtres glissantes ≤ as_of)."""
    held = [a for a, x in weights.items() if x > 1e-9]
    w = np.array([weights[a] for a in held])
    df = bt_data.load_returns(held, end=bt_data.to_month_end(as_of), currency=currency)
    m = int(round(horizon_years * P))
    note = "fenêtres chevauchantes : observations non indépendantes ; le passé n'est pas une prévision"
    if len(df) < m + 1:
        return HorizonReport(horizon_years, 0, None, None, None, None, None,
                             f"historique commun trop court ({len(df)} mois pour {m}) ; {note}")
    lg = np.log1p((df[held] @ w).to_numpy())
    c = np.concatenate([[0.0], np.cumsum(lg)])
    g = np.expm1(c[m:] - c[:-m])
    return HorizonReport(horizon_years, len(g), float(g.min()), float(np.quantile(g, 0.05)),
                         float(np.median(g)), float((g < 0).mean()),
                         (str(df.index[0].date()), str(df.index[-1].date())), note)


# --------------------------------------------------------------------------- Historique long (CVAR12M)

@dataclass
class LongHistory:
    returns: pd.Series                  # Σ_{i avec historique} w_i r_i (poids NON renormalisés), mensuel
    start: str
    end: str
    proxies_used: dict[str, str]        # actif -> proxy raccordé avant son lancement
    excluded_bound: float               # Σ_j w_j δ_j des actifs exclus (loss_bounds)
    excluded: list[str]
    status: str                         # FAIT si aucun proxy ni borne, sinon HYPOTHESE


@traced_tool("portfolio.long_history_returns")
def long_history_returns(weights: dict[str, float], policy: PolicySpec, as_of) -> LongHistory:
    """Historique le plus long possible ≤ as_of : chaque actif détenu, raccordé à son proxy déclaré
    (``policy.history_proxies``) avant son lancement. Les actifs de ``policy.loss_bounds`` (sans
    historique long, ex. crypto) sont exclus de la série et rendus sous forme de borne Σ w_j δ_j,
    pour ne pas tronquer l'échantillon (1973-74, 2000-02, 2008). Raccord et borne = HYPOTHESE."""
    end = bt_data.to_month_end(as_of)
    held = [a for a, x in weights.items() if x > 1e-9]
    excluded = [a for a in held if a in policy.loss_bounds]
    kept = [a for a in held if a not in policy.loss_bounds]
    bound = float(sum(weights[a] * policy.loss_bounds[a] for a in excluded))
    series, used = {}, {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        for a in kept:
            own = bt_data.load_returns([a], end=end, currency=policy.currency)[a]
            hp = policy.history_proxies.get(a)
            if hp is not None:
                prox = bt_data.load_returns([hp.proxy], end=end, currency=policy.currency)[hp.proxy]
                before = prox.loc[:own.index[0] - pd.offsets.MonthEnd(1)]
                if len(before):
                    own = pd.concat([before, own])
                    used[a] = hp.proxy
            series[a] = own
    if not kept:
        return LongHistory(pd.Series(dtype=float), "", "", used, bound, excluded, "HYPOTHESE")
    df = pd.DataFrame(series).dropna()
    r = df[kept] @ np.array([weights[a] for a in kept])
    return LongHistory(r, str(df.index[0].date()), str(df.index[-1].date()), used, bound, excluded,
                       "HYPOTHESE" if (used or excluded) else "FAIT")


@traced_tool("portfolio.loss_2022")
def loss_2022(weights: dict[str, float], currency: str = "CAD") -> tuple[float | None, str]:
    """Perte (positive) de l'année civile 2022, tickers réels, rééquilibrage mensuel."""
    held = [a for a, x in weights.items() if x > 1e-9]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        df = bt_data.load_returns(held, start=bt_data.to_month_end("2022-01"),
                                  end=bt_data.to_month_end("2022-12"), currency=currency)
    if len(df) < 12:
        return None, f"2022 non couvert pour ce portefeuille ({len(df)}/12 mois)"
    g = float(np.prod(1 + df[held] @ np.array([weights[a] for a in held])) - 1)
    return max(-g, 0.0), "rendement composé 2022-01 → 2022-12, tickers réels"


def cvar_rolling(r, months: int = 12, beta: float = 0.95) -> float:
    """CVaR (perte positive) des rendements composés sur ``months`` mois glissants chevauchants,
    même convention que bt_metrics.var_cvar (quantile « lower », moyenne de la queue)."""
    lg = np.log1p(np.asarray(r, float))
    if lg.size < months + 1:
        return float("nan")
    c = np.concatenate([[0.0], np.cumsum(lg)])
    g = np.expm1(c[months:] - c[:-months])
    return bt_metrics.var_cvar(g, alpha=1 - beta)[1]
