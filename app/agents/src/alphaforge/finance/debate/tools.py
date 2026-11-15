"""Preuves chiffrées des lentilles : enveloppes des analyses F3 qui écrivent des Facts.

Deux usages :
- ``lens_evidence`` : la preuve de base de chaque lentille, calculée par le code avant l'appel LLM ;
- ``strands_tools`` : outils ``@tool`` que la lentille peut appeler elle-même quand elle veut
  creuser (c'est là que se trouve le choix d'outils, donc l'agentivité réelle).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from alphaforge.finance.contracts.policy import PolicySpec
from alphaforge.finance.contracts.profile import InvestorProfile
from alphaforge.finance.portfolio import analysis
from alphaforge.finance.portfolio.judge import check
from alphaforge.finance.portfolio.market import returns_window

from .facts import FactBook

ENGINE = "alphaforge.finance.backtest (rendements mensuels, data/long)"


@dataclass
class LensContext:
    profile: InvestorProfile
    policy: PolicySpec
    weights: dict[str, float]
    as_of: date
    book: FactBook
    label: str = "candidat"  # préfixe des fact_id (ex. r1, r2, demande)
    evidence_fn: Callable | None = None  # OkfMarketStore.evidence(ticker, topic, as_of) : esg, fundamentals, news
    _win: object | None = field(default=None, repr=False)

    def win(self):
        if self._win is None:
            held = [a for a, w in self.weights.items() if w > 1e-9]
            self._win = returns_window(self.policy, self.as_of, held)
        return self._win


def _held(w: dict[str, float]) -> dict[str, float]:
    return {a: x for a, x in w.items() if x > 1e-6}


def shortest_horizon(profile: InvestorProfile) -> float:
    hs = []
    for g in profile.goals:
        if g.horizon_years is not None:
            hs.append(g.horizon_years)
        elif g.target_date is not None:
            hs.append(max((g.target_date - profile.created_utc.date()).days / 365.25, 0.0))
    return min(hs) if hs else 1.0


def wealth(profile: InvestorProfile) -> float | None:
    return profile.investable_wealth


# ------------------------------------------------------------------------- preuves de base
def timeline_evidence(c: LensContext) -> list[str]:
    b, p, w = c.book, c.label, _held(c.weights)
    h = shortest_horizon(c.profile)
    ids = [b.add(f"{p}.horizon", "Horizon le plus court des objectifs", h, "années", dataset="profile")]
    hr = analysis.horizon_report(w, max(h, 1.0), c.as_of)
    if hr.worst is not None:
        ids += [
            b.add(
                f"{p}.horizon_worst",
                f"Pire rendement composé sur {max(h, 1.0):.0f} an(s), historique",
                hr.worst,
                "%",
                dataset=ENGINE,
                processing=hr.note,
                status="FAIT",
            ),
            b.add(
                f"{p}.horizon_share_neg",
                "Part des fenêtres historiques en perte sur l'horizon",
                hr.share_negative,
                "%",
                dataset=ENGINE,
                processing=hr.note,
            ),
        ]
    rr = analysis.risk_report(w, c.win())
    ids.append(
        b.add(
            f"{p}.recovery",
            "Temps de récupération de la pire baisse (historique)",
            rr.recovery_months,
            "mois",
            dataset=ENGINE,
            processing=f"fenêtre {rr.window[0]}..{rr.window[1]}",
        )
    )
    return ids


def risk_evidence(c: LensContext) -> list[str]:
    b, p, w = c.book, c.label, _held(c.weights)
    rr = analysis.risk_report(w, c.win())
    proc = f"rendements mensuels CAD {rr.window[0]}..{rr.window[1]} ({rr.n_obs} mois)"
    ids = [
        b.add(f"{p}.cvar_m", "CVaR 95 % mensuelle (historique)", rr.cvar_m, "%", dataset=ENGINE, processing=proc),
        b.add(
            f"{p}.mdd", "Baisse maximale historique (fenêtre)", rr.max_drawdown, "%", dataset=ENGINE, processing=proc
        ),
        b.add(f"{p}.vol", "Volatilité annualisée (historique)", rr.vol_ann, "%", dataset=ENGINE, processing=proc),
        b.add(
            f"{p}.worst12",
            "Pire rendement sur 12 mois (historique)",
            rr.worst_12m,
            "%",
            dataset=ENGINE,
            processing=proc,
        ),
    ]
    top = sorted(rr.contrib_cvar.items(), key=lambda kv: -kv[1])[:3]
    for a, v in top:
        share = v / rr.cvar_m if rr.cvar_m else None
        ids.append(
            b.add(
                f"{p}.rc.{a}",
                f"Part de la CVaR portée par {a}",
                share,
                "%",
                dataset=ENGINE,
                processing="contribution d'Euler à la CVaR mensuelle",
            )
        )
    investable_cad = wealth(c.profile)
    for s in analysis.stress_report(w):
        if s.covered and s.period_return is not None:
            ids.append(
                b.add(
                    f"{p}.stress.{s.episode}",
                    f"Rendement pendant {s.label_fr}",
                    s.period_return,
                    "%",
                    dataset=ENGINE,
                    processing=f"{s.start}..{s.end}, tickers réels",
                )
            )
            if investable_cad:
                ids.append(
                    b.add(
                        f"{p}.stress_cad.{s.episode}",
                        f"Perte en dollars pendant {s.label_fr}",
                        max(-s.period_return, 0.0) * investable_cad,
                        "CAD",
                        dataset=ENGINE,
                        processing=f"perte × patrimoine investissable déclaré ({investable_cad:,.0f} $)",
                    )
                )
    if c.profile.max_acceptable_loss_cad is not None:
        ids.append(
            b.add(
                f"{p}.loss_declared",
                "Perte que l'investisseur déclare pouvoir absorber",
                c.profile.max_acceptable_loss_cad,
                "CAD",
                dataset="profile",
            )
        )
    return ids


def diversity_evidence(c: LensContext, tags=("tech", "energy", "financials")) -> list[str]:
    b, p, w = c.book, c.label, _held(c.weights)
    dr = analysis.diversification_report(w, c.win())
    ids = [
        b.add(f"{p}.n_eff_risk", "Nombre effectif de sources de risque", dr.effective_n_risk, "ratio", dataset=ENGINE),
        b.add(f"{p}.div_ratio", "Ratio de diversification", dr.diversification_ratio, "ratio", dataset=ENGINE),
    ]
    for i, cl in enumerate(dr.clusters[:3]):
        ids.append(
            b.add(
                f"{p}.cluster{i}",
                f"Poids d'un groupe très corrélé ({', '.join(cl['assets'][:5])})",
                cl["weight"],
                "%",
                dataset=ENGINE,
                processing=f"corrélation moyenne {cl['avg_corr']:.2f}",
            )
        )
    lt = analysis.lookthrough_report(w, c.policy, list(tags), c.as_of)
    for t, v in lt.exposures.items():
        st = "HYPOTHESE" if lt.hypotheses.get(t) else "FAIT"
        ids.append(
            b.add(
                f"{p}.lt.{t}",
                f"Exposition consolidée « {t} » (look-through)",
                v,
                "%",
                dataset=ENGINE,
                processing="look-through engine + exposure_overrides",
                status=st,
            )
        )
    if c.evidence_fn is not None:
        for a in w:
            for f in c.evidence_fn(a, "esg", c.as_of) or []:
                ids += c.book.absorb([f.model_copy(update={"trace_id": c.book.current})])
    return ids


def constraints_evidence(c: LensContext) -> list[str]:
    rep = check(_held(c.weights) or c.weights, c.policy, c.as_of, trace_id=f"{c.book.current}:judge")
    ids = c.book.absorb_report(rep)
    b, p = c.book, c.label
    ids.append(
        b.add(
            f"{p}.n_blocking",
            "Limites bloquantes dépassées",
            len(rep.blocking_violations),
            "ratio",
            dataset="judge:F4",
            processing=", ".join(rep.blocking_violations) or "aucune",
        )
    )
    return ids


EVIDENCE = {
    "timeline": timeline_evidence,
    "risk": risk_evidence,
    "diversity": diversity_evidence,
    "constraints": constraints_evidence,
}


def lens_evidence(lens: str, c: LensContext) -> list[str]:
    with c.book.step(f"lens.{lens}", tool="evidence", inputs={"label": c.label}):
        return EVIDENCE[lens](c)


# ------------------------------------------------------------------------- outils Strands
LENS_TOOLS = {
    "timeline": ("horizon_distribution", "stress_episodes"),
    "risk": ("stress_episodes", "horizon_distribution"),
    "diversity": ("exposure", "esg_evidence"),
    "constraints": ("exposure", "esg_evidence"),
}
# Outils de la base générale (magasin OKF), ajoutés à ces lentilles seulement si ``evidence_fn`` est fourni : sans
# lui, les listes d'outils, donc les clés de rejeu LLM, ne changent pas.
OKF_TOOLS = ("fundamentals_evidence", "filings_evidence")
OKF_TOOL_LENSES = ("diversity", "constraints")


def strands_tools(lens: str, c: LensContext) -> list:
    """Outils à la demande d'une lentille. Chaque appel est tracé et renvoie des fact_ids."""
    from strands import tool

    def run(name, fn, **kw):
        with c.book.step(f"lens.{lens}", tool=name, inputs=kw):
            return c.book.show(fn(**kw))

    names = LENS_TOOLS[lens]
    if c.evidence_fn is not None and lens in OKF_TOOL_LENSES:
        names = (*names, *OKF_TOOLS)
    return [_TOOL_MAKERS[name](tool, c, run) for name in names]


def _absorb_evidence(c: LensContext, ticker: str, topic: str) -> list[str]:
    """Facts de la base générale pour ``ticker`` et ``topic``, rattachés à l'étape courante de la trace."""
    return c.book.absorb(
        [x.model_copy(update={"trace_id": c.book.current}) for x in c.evidence_fn(ticker, topic, c.as_of) or []]
    )


# Une fabrique par outil : elle reçoit le décorateur ``tool`` de Strands, le contexte et le traceur ``run``. Le nom,
# la signature et la docstring de chaque fonction décorée sont ce que lit le modèle : ne pas les changer.
def _stress_episodes(tool, c: LensContext, run: Callable):
    @tool
    def stress_episodes() -> list[dict]:
        """Rendement et perte en dollars du candidat pendant les crises historiques couvertes
        (2022, 2020, etc.). Renvoie des fact_id à citer."""
        return run("stress_episodes", lambda: [i for i in risk_evidence(c) if ".stress" in i])

    return stress_episodes


def _horizon_distribution(tool, c: LensContext, run: Callable):
    @tool
    def horizon_distribution(years: float) -> list[dict]:
        """Distribution historique des rendements composés du candidat sur `years` années
        (pire cas, part des fenêtres en perte). Renvoie des fact_id à citer."""

        def f(years):
            hr = analysis.horizon_report(_held(c.weights), max(float(years), 1.0), c.as_of)
            return [
                c.book.add(
                    f"{c.label}.h{years}.worst",
                    f"Pire rendement sur {years} ans",
                    hr.worst,
                    "%",
                    dataset=ENGINE,
                    processing=hr.note,
                ),
                c.book.add(
                    f"{c.label}.h{years}.neg",
                    f"Part des fenêtres de {years} ans en perte",
                    hr.share_negative,
                    "%",
                    dataset=ENGINE,
                    processing=hr.note,
                ),
            ]

        return run("horizon_distribution", f, years=years)

    return horizon_distribution


def _exposure(tool, c: LensContext, run: Callable):
    @tool
    def exposure(tag: str) -> list[dict]:
        """Exposition consolidée (look-through des FNB) du candidat à un thème : tech, energy,
        financials, healthcare... Renvoie des fact_id à citer."""

        def f(tag):
            lt = analysis.lookthrough_report(_held(c.weights), c.policy, [tag], c.as_of)
            return [
                c.book.add(
                    f"{c.label}.lt.{tag}",
                    f"Exposition consolidée « {tag} »",
                    lt.exposures.get(tag),
                    "%",
                    dataset=ENGINE,
                    status="HYPOTHESE" if lt.hypotheses.get(tag) else "FAIT",
                )
            ]

        return run("exposure", f, tag=tag)

    return exposure


def _esg_evidence(tool, c: LensContext, run: Callable):
    @tool
    def esg_evidence(ticker: str) -> list[dict]:
        """Preuves ESG datées (exclusions d'indices, incidents, émissions) pour un titre de la base
        générale. Liste vide si aucune preuve : ne jamais inventer de controverse."""

        def f(ticker):
            if c.evidence_fn is None:
                return []
            return _absorb_evidence(c, ticker, "esg")

        return run("esg_evidence", f, ticker=ticker)

    return esg_evidence


def _fundamentals_evidence(tool, c: LensContext, run: Callable):
    @tool
    def fundamentals_evidence(ticker: str) -> list[dict]:
        """Chiffres financiers publiés par une société de la base générale (produits, bénéfice, BPA dilué,
        levier, dividende), connus à la date de la simulation, avec leur période. Contexte seulement : ils
        n'entrent pas dans le classement des titres. Liste vide si la société n'est pas couverte."""

        def f(ticker):
            return _absorb_evidence(c, ticker, "fundamentals")

        return run("fundamentals_evidence", f, ticker=ticker)

    return fundamentals_evidence


def _filings_evidence(tool, c: LensContext, run: Callable):
    @tool
    def filings_evidence(ticker: str) -> list[dict]:
        """Dépôts réglementaires récents d'une société (formulaire, numéro, date de dépôt), connus à la date de la
        simulation. Contexte à signaler seulement (flag_only) : leur contenu n'est pas lu, ils ne justifient jamais
        un changement du mandat. Liste vide si aucun dépôt n'est connu."""

        def f(ticker):
            return _absorb_evidence(c, ticker, "filings")

        return run("filings_evidence", f, ticker=ticker)

    return filings_evidence


_TOOL_MAKERS = {
    "stress_episodes": _stress_episodes,
    "horizon_distribution": _horizon_distribution,
    "exposure": _exposure,
    "esg_evidence": _esg_evidence,
    "fundamentals_evidence": _fundamentals_evidence,
    "filings_evidence": _filings_evidence,
}
