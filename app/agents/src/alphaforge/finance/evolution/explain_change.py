"""Explication d'un événement d'évolution (les 4 questions : données, pourquoi, limites, ce qui changerait).

Gabarits déterministes : chaque nombre écrit est la valeur formatée (``debate.facts.fmt``) d'un ``Fact`` cité, et
chaque phrase passe le vérificateur existant ``debate.explain.verify`` (importé, non modifié). Aucun LLM ici ;
une reformulation éventuelle passerait par le même vérificateur. SIMULATION SEULEMENT.
"""

from __future__ import annotations

from ..contracts.decision import Explanation, Fact, Source, Statement
from ..contracts.evolution import PortfolioVersion, RebalanceEvent
from ..debate.explain import verify
from ..debate.facts import FactBook, fmt
from .config import EvolutionConfig

FORBIDDEN = ("achète", "achetez", "vends", "vendez", "recommand", "conseil personnalisé", "garanti")


def _book(facts: list[Fact], extra: list[Fact]) -> FactBook:
    book = FactBook("evolution")
    for f in [*facts, *extra]:
        book.facts[f.fact_id] = f
    return book


def _cfg_facts(cfg: EvolutionConfig, month_key: str) -> list[Fact]:
    def f(key, label, value, unit, path):
        return Fact(
            fact_id=f"cfg.{key}",
            label_fr=label,
            value=value,
            unit=unit,
            status="HYPOTHESE",
            sources=[Source(dataset=cfg.src(path), sha256=cfg.sha256)],
            trace_id=f"evolution:cfg:{month_key}",
        )

    return [
        f("band_abs", "Largeur absolue de la bande", cfg.bands.abs, "%", "bands.abs"),
        f("band_rel", "Largeur relative de la bande", cfg.bands.rel, "%", "bands.rel"),
        f(
            "max_turnover",
            "Rotation maximale par mois lors d'un changement de cible",
            cfg.trading.max_turnover_tick,
            "%",
            "trading.max_turnover_tick",
        ),
    ]


def _s(book: FactBook, text: str, ids: list[str], label: str = "FAIT") -> Statement:
    ids = [i for i in ids if i in book.facts]
    st = Statement(text_fr=text, fact_ids=ids, label=label)
    problems = verify(book, st)
    if problems:
        raise ValueError(f"phrase non vérifiable ({problems}) : {text}")
    low = text.lower()
    if any(w in low for w in FORBIDDEN):
        raise ValueError(f"vocabulaire interdit : {text}")
    return st


def explain_event(version: PortfolioVersion, facts: list[Fact], cfg: EvolutionConfig) -> tuple[Explanation, list[Fact]]:
    """Explication de l'événement d'une version. Rend aussi les faits de configuration ajoutés."""
    ev = version.event
    key = f"ev.{version.as_of:%Y%m}"
    extra = _cfg_facts(cfg, key) + [
        Fact(
            fact_id=f"{key}.mois",
            label_fr="Mois simulé",
            value=f"{version.as_of:%Y-%m}",
            unit="texte",
            status="FICTION",
            sources=[Source(dataset="evolution:replay")],
            trace_id=f"evolution:{key}",
        ),
    ]
    book = _book(facts, extra)
    explanation = Explanation(
        data_used=_data_used(book, key),
        why=_why(book, ev, key, cfg),
        limits=_limits(book, ev, key),
        what_would_change=_what_would_change(book, ev, cfg),
    )
    return explanation, extra


def _data_used(book: FactBook, key: str) -> list[Statement]:
    """Question 1 : les données lues à la date simulée."""
    mois, r = f"{key}.mois", f"{key}.r_portefeuille"
    proxies = [fid for fid in book.facts if fid.startswith(f"{key}.proxy.")]
    data_used = [
        _s(
            book,
            f"Mois simulé {fmt(book.facts[mois].value, 'texte')} : seuls les rendements mensuels en CAD "
            "connus à cette date sont lus.",
            [mois],
            "FICTION",
        )
    ]
    if r in book.facts:
        data_used.append(_s(book, f"Rendement du portefeuille sur le mois : {fmt(book.facts[r].value, '%')}.", [r]))
    if proxies:
        data_used.append(
            _s(
                book,
                "Certaines lignes n'avaient pas encore d'historique : leur indice long de remplacement est utilisé.",
                proxies,
                "HYPOTHESE",
            )
        )
    return data_used


def _why(book: FactBook, ev: RebalanceEvent, key: str, cfg: EvolutionConfig) -> list[Statement]:
    """Question 2 : la raison de l'action, puis une phrase par déclencheur dont le fait est connu."""
    reason = _action_reason(book, ev, key, cfg)
    why = [] if reason is None else [reason]
    for t in ev.triggers:
        fid = f"{key}.declencheur.{t.code}"
        if fid in book.facts and t.code != "JUDGE_VIOLATION_DRIFT":
            why.append(
                _s(book, f"Déclencheur {t.code} (son seuil et la source de ce seuil sont dans le fait cité).", [fid])
            )
    return why


def _action_reason(book: FactBook, ev: RebalanceEvent, key: str, cfg: EvolutionConfig) -> Statement | None:
    """Phrase « pourquoi » propre à l'action de l'événement ; None pour une action sans gabarit."""
    a = ev.action
    if a == "HOLD":
        drift = f"{key}.derive"
        return _s(
            book,
            f"Toutes les lignes restent dans leurs bandes (dérive {fmt(book.facts[drift].value, '%')}) "
            "et aucune limite n'est franchie : aucun mouvement.",
            [drift],
        )
    if a == "REBALANCE_TO_BANDS" and ev.breaches:
        ids = [f"{key}.bande.{x}" for x in ev.breaches if f"{key}.bande.{x}" in book.facts]
        return _s(
            book,
            f"{', '.join(ev.breaches)} sort de sa bande (au plus {fmt(cfg.bands.abs, '%')} ou "
            f"{fmt(cfg.bands.rel, '%')} de la cible) : retour à mi-chemin vers la cible.",
            ["cfg.band_abs", "cfg.band_rel", *ids],
        )
    if a == "REBALANCE_TO_BANDS":
        rules = ", ".join(sorted({t.code for t in ev.triggers if t.code == "JUDGE_VIOLATION_DRIFT"})) or "une limite"
        return _s(
            book,
            f"La dérive du marché fait franchir {rules} du profil : correction minimale des seules "
            "lignes concernées, sans rééquilibrage complet.",
            [],
        )
    if a == "REOPTIMIZE":
        lvl = f"{key}.niveau"
        return _s(
            book,
            f"Le niveau de risque devient {fmt(book.facts[lvl].value, 'niveau')} à cette date "
            "(l'horizon raccourcit) : la cible est recalculée par le moteur, puis contrôlée par le Judge.",
            [lvl],
        )
    if a == "OVERLAY_SHIFT":
        names = ", ".join(o.name for o in ev.overlays if o.active and o.delta)
        return _s(
            book,
            f"Le signal d'une stratégie systématique validée a changé ({names}) : la cible se déplace "
            "à l'intérieur des limites du profil.",
            [fid for o in ev.overlays for fid in o.fact_ids],
        )
    if a == "REPROFILE_REQUIRED":
        return _reprofile_reason(book, ev)
    return None


def _reprofile_reason(book: FactBook, ev: RebalanceEvent) -> Statement:
    codes = ", ".join(t.code for t in ev.triggers if t.blocking)
    if ev.trades:
        return _s(
            book,
            f"Déclencheur bloquant ({codes}) : aucune décision stratégique ; seules des "
            "corrections de conformité aux limites du profil ont été simulées. Une mise à jour du "
            "profil est demandée avant toute nouvelle proposition.",
            [],
        )
    return _s(
        book,
        f"Déclencheur bloquant ({codes}) : aucun mouvement ; une mise à jour du profil est "
        "demandée avant toute nouvelle proposition.",
        [],
    )


def _limits(book: FactBook, ev: RebalanceEvent, key: str) -> list[Statement]:
    """Question 3 : les limites de la simulation (coût des mouvements, baisse depuis le plus haut)."""
    rot, cost, dd = f"{key}.rotation", f"{key}.cout", f"{key}.baisse"
    limits = [
        _s(book, "Événement de rééquilibrage illustratif : simulation éducative, aucun ordre réel.", [], "FICTION"),
        _s(book, "Les rendements décrivent le passé et ne prédisent pas l'avenir.", [], "HYPOTHESE"),
    ]
    if ev.trades and cost in book.facts and rot in book.facts:
        limits.append(
            _s(
                book,
                f"Coût estimé des mouvements : {fmt(book.facts[cost].value, 'CAD')} pour une rotation "
                f"de {fmt(book.facts[rot].value, '%')} ; paramètres de coût en HYPOTHESE.",
                [cost, rot],
                "HYPOTHESE",
            )
        )
    if dd in book.facts:
        limits.append(_s(book, f"Baisse depuis le plus haut à cette date : {fmt(book.facts[dd].value, '%')}.", [dd]))
    return limits


def _what_would_change(book: FactBook, ev: RebalanceEvent, cfg: EvolutionConfig) -> list[Statement]:
    """Question 4 : ce qui changerait le résultat (largeur de bande, rotation maximale)."""
    wwc = [
        _s(
            book,
            f"Une bande plus large que {fmt(cfg.bands.abs, '%')} réduirait le nombre de mouvements, au prix "
            "d'un écart plus long à la cible.",
            ["cfg.band_abs"],
            "HYPOTHESE",
        )
    ]
    if ev.action == "REOPTIMIZE":
        wwc.append(
            _s(
                book,
                f"Une rotation maximale de {fmt(cfg.trading.max_turnover_tick, '%')} par mois étale un "
                "changement de niveau à la hausse sur plusieurs mois.",
                ["cfg.max_turnover"],
                "HYPOTHESE",
            )
        )
    return wwc
