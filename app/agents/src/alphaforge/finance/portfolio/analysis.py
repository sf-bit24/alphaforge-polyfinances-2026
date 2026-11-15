"""F3 — Outils d'analyse d'un portefeuille (lentilles Timeline, Risque, Diversité, Contraintes).

Fonctions déterministes ; chaque chiffre est recalculable et devient un ``Fact`` sourcé.
Les mesures reprennent celles du moteur (``finance/backtest/metrics.py``) pour que
l'analyse et le Judge (F4) mesurent exactement la même chose.
Les rendements historiques décrivent le passé : ce ne sont pas des prévisions.
SIMULATION SEULEMENT.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from functools import lru_cache
from typing import NamedTuple

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from ..backtest import data as bt_data
from ..backtest import metrics as bt_metrics
from ..contracts import PolicySpec
from ..observability.telemetry import traced_tool
from .compile import exposure_overrides_for, unknown_exposures
from .market import ReturnWindow

MONTHS_PER_YEAR = 12
MIN_HELD_WEIGHT = 1e-9  # poids en dessous duquel un actif n'est pas détenu
MIN_CLUSTERED_WEIGHT = 1e-6  # poids en dessous duquel un actif n'entre dans aucune grappe

# Épisodes historiques (fenêtres mensuelles inclusives). Un épisode n'est calculé que si
# tous les actifs ont des données sur toute la fenêtre ; sinon il est déclaré « non couvert ».
STRESS_EPISODES: dict[str, tuple[str, str, str]] = {
    "2022_taux": ("2022-01", "2022-12", "Hausse des taux 2022 : actions et obligations en baisse"),
    "2020_covid": ("2020-02", "2020-03", "Choc COVID-19"),
    "2008_crise": ("2007-11", "2009-02", "Crise financière mondiale"),
    "2000_bulle": ("2000-09", "2002-09", "Éclatement de la bulle technologique"),
    "1973_choc": ("1973-01", "1974-09", "Choc pétrolier et stagflation"),
}


def _weight_vector(weights: dict[str, float], assets: list[str]) -> np.ndarray:
    extra = set(weights) - set(assets)
    if extra:
        raise KeyError(f"poids sur des actifs hors fenêtre : {sorted(extra)}")
    return np.array([float(weights.get(asset, 0.0)) for asset in assets])


class _Held(NamedTuple):
    assets: list[str]
    weights: np.ndarray


def _held(weights: dict[str, float]) -> _Held:
    """Actifs réellement détenus et leurs poids, dans l'ordre fourni."""
    assets = [asset for asset, x in weights.items() if x > MIN_HELD_WEIGHT]
    return _Held(assets, np.array([weights[asset] for asset in assets]))


def portfolio_returns(weights: dict[str, float], returns: pd.DataFrame) -> pd.Series:
    """Rendements mensuels d'un portefeuille rééquilibré chaque mois vers ``weights``."""
    return returns @ _weight_vector(weights, list(returns.columns))


# --------------------------------------------------------------------------- Risque


@dataclass
class RiskReport:
    vol_ann: float
    hist_return_ann: float  # passé, pas une prévision
    var_m: float  # VaR mensuelle historique (perte positive)
    cvar_m: float  # CVaR mensuelle historique (perte positive)
    cdar: float  # CDaR sur le drawdown composé
    max_drawdown: float  # drawdown composé (engine)
    worst_12m: float
    recovery_months: float
    beta: float
    contrib_vol: dict[str, float]  # somme = vol_ann
    contrib_cvar: dict[str, float]  # somme = cvar_m
    n_obs: int
    window: tuple[str, str]


def cdar_compounded(r: np.ndarray, beta: float) -> float:
    drawdowns = bt_metrics.drawdown_series(r)
    threshold = np.quantile(drawdowns, beta, method="higher")
    return float(drawdowns[drawdowns >= threshold].mean())


@traced_tool("portfolio.risk_report")
def risk_report(weights: dict[str, float], win: ReturnWindow, beta: float = 0.95) -> RiskReport:
    returns = win.returns
    assets = list(returns.columns)
    vector = _weight_vector(weights, assets)
    portfolio = (returns @ vector).to_numpy()
    var_m, cvar_m = bt_metrics.var_cvar(portfolio, alpha=1 - beta)

    cov = np.atleast_2d(np.cov(returns.to_numpy(), rowvar=False, ddof=1))
    monthly_vol = float(np.sqrt(vector @ cov @ vector))
    marginal = cov @ vector / monthly_vol if monthly_vol > 0 else np.zeros_like(vector)
    contrib_vol = {asset: float(vector[i] * marginal[i] * np.sqrt(MONTHS_PER_YEAR)) for i, asset in enumerate(assets)}

    threshold = np.quantile(portfolio, 1 - beta, method="lower")  # même définition que bt_metrics.var_cvar
    in_tail = portfolio <= threshold
    tail_returns = returns.to_numpy()[in_tail] * vector
    contrib_cvar = {asset: float(-tail_returns[:, i].mean()) for i, asset in enumerate(assets)}

    return RiskReport(
        vol_ann=bt_metrics.volatility(portfolio),
        hist_return_ann=bt_metrics.annualized_return(portfolio),
        var_m=var_m,
        cvar_m=cvar_m,
        cdar=cdar_compounded(portfolio, beta),
        max_drawdown=bt_metrics.max_drawdown(portfolio),
        worst_12m=bt_metrics.worst_window_return(portfolio, 12),
        recovery_months=bt_metrics.recovery_months(portfolio),
        beta=beta,
        contrib_vol=contrib_vol,
        contrib_cvar=contrib_cvar,
        n_obs=win.n_obs,
        window=(str(win.start.date()), str(win.end.date())),
    )


# --------------------------------------------------------------------------- Diversité


@dataclass
class DiversificationReport:
    effective_n_weights: float  # 1 / Σ w²
    effective_n_risk: float  # 1 / Σ (part de risque)² sur les parts positives
    diversification_ratio: float  # Σ w σ_i / σ_p
    clusters: list[dict]  # {"assets": [...], "weight": x, "avg_corr": ρ}
    corr_threshold: float


def _correlation_clusters(
    weights: dict[str, float], returns: pd.DataFrame, held: list[str], corr_threshold: float
) -> list[dict]:
    """Grappes d'actifs corrélés (classification hiérarchique, lien moyen)."""
    correlation = returns[held].corr().to_numpy()
    distance = np.sqrt(np.clip(0.5 * (1 - correlation), 0, None))  # distance de López de Prado
    np.fill_diagonal(distance, 0)
    labels = fcluster(
        linkage(squareform(distance, checks=False), "average"),
        t=np.sqrt(0.5 * (1 - corr_threshold)),
        criterion="distance",
    )
    clusters = []
    for label in sorted(set(labels)):
        members = [asset for asset, member_label in zip(held, labels, strict=True) if member_label == label]
        indices = [held.index(asset) for asset in members]
        within = correlation[np.ix_(indices, indices)]
        mean_correlation = float(within[np.triu_indices(len(indices), 1)].mean()) if len(indices) > 1 else 1.0
        weight = float(sum(weights[asset] for asset in members))
        clusters.append({"assets": members, "weight": weight, "avg_corr": mean_correlation})
    return clusters


@traced_tool("portfolio.diversification_report")
def diversification_report(
    weights: dict[str, float], win: ReturnWindow, corr_threshold: float = 0.7
) -> DiversificationReport:
    returns = win.returns
    assets = list(returns.columns)
    vector = _weight_vector(weights, assets)
    cov = np.atleast_2d(np.cov(returns.to_numpy(), rowvar=False, ddof=1))
    asset_vols = np.sqrt(np.diag(cov))
    portfolio_vol = float(np.sqrt(vector @ cov @ vector))
    risk_share = (vector * (cov @ vector)) / (portfolio_vol**2) if portfolio_vol > 0 else np.zeros_like(vector)
    positive = risk_share[risk_share > 0]

    held = [asset for asset, x in zip(assets, vector, strict=True) if x > MIN_CLUSTERED_WEIGHT]
    if len(held) >= 2:
        clusters = _correlation_clusters(weights, returns, held, corr_threshold)
    else:
        clusters = [{"assets": held, "weight": float(weights[held[0]]), "avg_corr": 1.0}] if held else []
    clusters.sort(key=lambda cluster: -cluster["weight"])

    return DiversificationReport(
        effective_n_weights=float(1 / np.sum(vector**2)),
        effective_n_risk=float(1 / np.sum((positive / positive.sum()) ** 2)) if positive.size else 0.0,
        diversification_ratio=float(vector @ asset_vols / portfolio_vol) if portfolio_vol > 0 else 0.0,
        clusters=clusters,
        corr_threshold=corr_threshold,
    )


# --------------------------------------------------------------------------- Look-through


@dataclass
class LookthroughReport:
    exposures: dict[str, float]  # tag -> part du portefeuille
    by_asset: dict[str, dict[str, float]]
    unknown: dict[str, list[str]]  # tag -> actifs larges sans donnée (comptés 0)
    hypotheses: dict[str, list[str]]  # tag -> actifs dont l'exposition est une HYPOTHESE


@traced_tool("portfolio.lookthrough_report")
def lookthrough_report(weights: dict[str, float], policy: PolicySpec, tags: list[str], as_of=None) -> LookthroughReport:
    assets = list(policy.investable)
    vector = _weight_vector(weights, assets)
    catalog = bt_data.load_assets()
    exposures, by_asset, unknown, hypotheses = {}, {}, {}, {}
    for tag in tags:
        overrides = exposure_overrides_for(policy, tag, assets)
        exposure = bt_data.exposure_vector(assets, tag, date=as_of, overrides=overrides)
        exposures[tag] = float(exposure @ vector)
        by_asset[tag] = {asset: float(x) for asset, x in zip(assets, exposure, strict=True) if x > 0}
        unknown[tag] = unknown_exposures(assets, exposure, overrides, catalog)
        hypotheses[tag] = [
            asset
            for asset, declared in policy.exposure_overrides.items()
            if tag in declared and declared[tag].status == "HYPOTHESE" and asset in assets
        ]
    return LookthroughReport(exposures, by_asset, unknown, hypotheses)


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


def _stress_episode(key: str, episode: tuple[str, str, str], held: _Held, currency: str) -> StressResult:
    first, last, label = episode
    start, end = bt_data.to_month_end(first), bt_data.to_month_end(last)
    try:
        with warnings.catch_warnings():  # la couverture est rapportée explicitement ci-dessous
            warnings.simplefilter("ignore", UserWarning)
            returns = bt_data.load_returns(held.assets, start=start, end=end, currency=currency)
    except Exception as exc:  # pragma: no cover - dépend des données
        return StressResult(key, label, first, last, covered=False, reason=str(exc))
    months = pd.date_range(start, end, freq="ME")
    if len(returns) < len(months) or returns.index[0] > start:
        info = returns.attrs.get("info") or {}
        reason = f"historique insuffisant ({len(returns)}/{len(months)} mois) ; {info}"
        return StressResult(key, label, first, last, covered=False, reason=reason)
    portfolio = (returns[held.assets] @ held.weights).to_numpy()
    growth = float(np.prod(1 + portfolio) - 1)
    loss_per_100k = round(-100_000 * min(growth, 0.0), 2)
    return StressResult(key, label, first, last, True, growth, bt_metrics.max_drawdown(portfolio), loss_per_100k)


@traced_tool("portfolio.stress_report")
def stress_report(
    weights: dict[str, float], currency: str = "CAD", episodes: dict[str, tuple[str, str, str]] | None = None
) -> list[StressResult]:
    held = _held(weights)
    return [_stress_episode(key, episode, held, currency) for key, episode in (episodes or STRESS_EPISODES).items()]


# --------------------------------------------------------------------------- Timeline


@dataclass
class HorizonReport:
    horizon_years: float
    n_windows: int  # fenêtres glissantes mensuelles (chevauchantes)
    worst: float | None
    p05: float | None
    median: float | None
    share_negative: float | None
    history: tuple[str, str] | None
    note: str


def _rolling_growth(log_returns: np.ndarray, months: int) -> np.ndarray:
    """Rendements composés sur ``months`` mois glissants (fenêtres chevauchantes)."""
    cumulative = np.concatenate([[0.0], np.cumsum(log_returns)])
    return np.expm1(cumulative[months:] - cumulative[:-months])


@traced_tool("portfolio.horizon_report")
def horizon_report(weights: dict[str, float], horizon_years: float, as_of, currency: str = "CAD") -> HorizonReport:
    """Distribution historique des rendements composés sur l'horizon (fenêtres glissantes ≤ as_of)."""
    held = _held(weights)
    returns = bt_data.load_returns(held.assets, end=bt_data.to_month_end(as_of), currency=currency)
    months = int(round(horizon_years * MONTHS_PER_YEAR))
    note = "fenêtres chevauchantes : observations non indépendantes ; le passé n'est pas une prévision"
    if len(returns) < months + 1:
        short = f"historique commun trop court ({len(returns)} mois pour {months}) ; {note}"
        return HorizonReport(horizon_years, 0, None, None, None, None, None, short)
    growth = _rolling_growth(np.log1p((returns[held.assets] @ held.weights).to_numpy()), months)
    return HorizonReport(
        horizon_years,
        len(growth),
        float(growth.min()),
        float(np.quantile(growth, 0.05)),
        float(np.median(growth)),
        float((growth < 0).mean()),
        (str(returns.index[0].date()), str(returns.index[-1].date())),
        note,
    )


# --------------------------------------------------------------------------- Historique long (CVAR12M)


@dataclass
class LongHistory:
    returns: pd.Series  # Σ_{i avec historique} w_i r_i (poids NON renormalisés), mensuel
    start: str
    end: str
    proxies_used: dict[str, str]  # actif -> proxy raccordé avant son lancement
    excluded_bound: float  # Σ_j w_j δ_j des actifs exclus (loss_bounds)
    excluded: list[str]
    status: str  # FAIT si aucun proxy ni borne, sinon HYPOTHESE


def _spliced_history(asset: str, policy: PolicySpec, end: pd.Timestamp) -> tuple[pd.Series, str | None]:
    """Rendements de ``asset`` jusqu'à ``end``, précédés de ceux de son proxy déclaré avant son lancement ;
    rend aussi le proxy effectivement raccordé. La série vient du cache de ``_spliced``."""
    declared = policy.history_proxies.get(asset)
    proxy = declared.proxy if declared is not None else None
    series, proxied = _spliced(asset, proxy, end, policy.currency, bt_data.data_version().get("data_sha256"))
    return series, proxy if proxied else None


@lru_cache(maxsize=4096)
def _spliced(
    asset: str, proxy: str | None, end: pd.Timestamp, currency: str, data_sha: str | None
) -> tuple[pd.Series, bool]:
    """Série mensuelle d'un actif ≤ ``end``, raccordée à son proxy avant son lancement (mémoïsée).

    ``data_sha`` fait partie de la clé : de nouvelles données invalident le cache. La série rendue est partagée :
    les appelants ne la modifient pas (``pd.DataFrame(series)`` copie).
    """
    own = bt_data.load_returns([asset], end=end, currency=currency)[asset]
    if proxy is not None:
        proxy_returns = bt_data.load_returns([proxy], end=end, currency=currency)[proxy]
        before = proxy_returns.loc[: own.index[0] - pd.offsets.MonthEnd(1)]
        if len(before):
            return pd.concat([before, own]), True
    return own, False


@traced_tool("portfolio.long_history_returns")
def long_history_returns(weights: dict[str, float], policy: PolicySpec, as_of) -> LongHistory:
    """Historique le plus long possible ≤ as_of : chaque actif détenu, raccordé à son proxy déclaré
    (``policy.history_proxies``) avant son lancement. Les actifs de ``policy.loss_bounds`` (sans
    historique long, ex. crypto) sont exclus de la série et rendus sous forme de borne Σ w_j δ_j,
    pour ne pas tronquer l'échantillon (1973-74, 2000-02, 2008). Raccord et borne = HYPOTHESE."""
    end = bt_data.to_month_end(as_of)
    held = _held(weights).assets
    excluded = [asset for asset in held if asset in policy.loss_bounds]
    kept = [asset for asset in held if asset not in policy.loss_bounds]
    bound = float(sum(weights[asset] * policy.loss_bounds[asset] for asset in excluded))
    series, used = {}, {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        for asset in kept:
            series[asset], proxy = _spliced_history(asset, policy, end)
            if proxy is not None:
                used[asset] = proxy
    if not kept:
        return LongHistory(pd.Series(dtype=float), "", "", used, bound, excluded, "HYPOTHESE")
    frame = pd.DataFrame(series).dropna()
    returns = frame[kept] @ np.array([weights[asset] for asset in kept])
    status = "HYPOTHESE" if (used or excluded) else "FAIT"
    return LongHistory(returns, str(frame.index[0].date()), str(frame.index[-1].date()), used, bound, excluded, status)


@traced_tool("portfolio.loss_2022")
def loss_2022(weights: dict[str, float], currency: str = "CAD") -> tuple[float | None, str]:
    """Perte (positive) de l'année civile 2022, tickers réels, rééquilibrage mensuel."""
    held = _held(weights)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        returns = bt_data.load_returns(
            held.assets, start=bt_data.to_month_end("2022-01"), end=bt_data.to_month_end("2022-12"), currency=currency
        )
    if len(returns) < 12:
        return None, f"2022 non couvert pour ce portefeuille ({len(returns)}/12 mois)"
    growth = float(np.prod(1 + returns[held.assets] @ held.weights) - 1)
    return max(-growth, 0.0), "rendement composé 2022-01 → 2022-12, tickers réels"


def cvar_rolling(r, months: int = 12, beta: float = 0.95) -> float:
    """CVaR (perte positive) des rendements composés sur ``months`` mois glissants chevauchants,
    même convention que bt_metrics.var_cvar (quantile « lower », moyenne de la queue)."""
    log_returns = np.log1p(np.asarray(r, float))
    if log_returns.size < months + 1:
        return float("nan")
    return bt_metrics.var_cvar(_rolling_growth(log_returns, months), alpha=1 - beta)[1]
