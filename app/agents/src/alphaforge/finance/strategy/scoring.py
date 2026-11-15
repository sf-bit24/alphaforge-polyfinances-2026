"""Étape 0, partie moteur : candidats (titres individuels de l'univers) avec leurs indicateurs.

Les indicateurs courts viennent du jeu de départ (``features``, FAIT). La baisse maximale longue vient de
l'historique raccordé du moteur (``portfolio.analysis.long_history_returns``, proxy industriel Ken French avant
le lancement du titre, donc HYPOTHESE). Si les données longues manquent (runtime sans parquets), la baisse
maximale sur la fenêtre du starter la remplace, en HYPOTHESE « fenêtre courte ». Simulation seulement.
"""

from __future__ import annotations

from datetime import date

from alphaforge import starter
from alphaforge.finance.backtest import data as bt_data
from alphaforge.finance.backtest import metrics as bt_metrics
from alphaforge.finance.contracts import PolicySpec
from alphaforge.finance.observability.telemetry import traced_tool
from alphaforge.finance.portfolio.analysis import long_history_returns

from .config import StrategyConfig, load_strategy
from .features import stock_features
from .rules import Candidate

SINGLE = "equity_single"


def _iso(as_of) -> str:
    return as_of.isoformat() if isinstance(as_of, date) else str(as_of)[:10]


def single_stocks(policy: PolicySpec) -> list[str]:
    catalog = bt_data.load_assets()
    return [a for a in policy.universe if a in catalog.index and catalog.at[a, "asset_class"] == SINGLE]


def _mdd_long(ticker: str, policy: PolicySpec, as_of) -> tuple[float | None, str, dict]:
    try:
        lh = long_history_returns({ticker: 1.0}, policy, as_of)
    except Exception as exc:  # données longues absentes ou titre inconnu du moteur
        return None, "HYPOTHESE", {"mdd_long_source": f"indisponible ({type(exc).__name__})"}
    if lh.returns.empty:
        return None, "HYPOTHESE", {"mdd_long_source": "série longue vide"}
    proxy = lh.proxies_used.get(ticker)
    det = {
        "mdd_long_source": f"historique raccordé {lh.start} → {lh.end}" + (f", proxy {proxy}" if proxy else ""),
        "mdd_long_proxy": proxy,
    }
    return float(bt_metrics.max_drawdown(lh.returns)), lh.status, det


@traced_tool("strategy.score_stocks", lambda r: {"n_candidates": len(r)})
def compute_candidates(policy: PolicySpec, as_of, cfg: StrategyConfig | None = None) -> list[Candidate]:
    cfg = cfg or load_strategy()
    iso = _iso(as_of)
    catalog = bt_data.load_assets()
    uni = starter.universe()
    out: list[Candidate] = []
    for t in single_stocks(policy):
        vals, status, details = stock_features(t, iso, cfg)
        mdd, st, det = _mdd_long(t, policy, as_of)
        if mdd is None:
            mdd, st = vals.get("mdd_short"), "HYPOTHESE"
            det["mdd_long_source"] = det.get("mdd_long_source", "") + " ; repli : fenêtre courte du starter"
        vals = {**vals, "mdd_long": mdd}
        status = {**status, "mdd_long": st} if mdd is not None else status
        tags = tuple(catalog.at[t, "tag_list"]) if t in catalog.index else ()
        asset = uni.get(t)
        out.append(
            Candidate(
                t,
                asset.sector if asset else "?",
                tags,
                asset.currency if asset else "CAD",
                vals,
                status,
                {**details, **det},
            )
        )
    return out
