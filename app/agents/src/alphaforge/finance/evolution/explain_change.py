"""Explication d'un événement d'évolution (les 4 questions : données, pourquoi, limites, ce qui changerait).

Gabarits déterministes : chaque nombre écrit est la valeur formatée (``debate.facts.fmt``) d'un ``Fact`` cité, et
chaque phrase passe le vérificateur existant ``debate.explain.verify`` (importé, non modifié). Aucun LLM ici ;
une reformulation éventuelle passerait par le même vérificateur. SIMULATION SEULEMENT.
"""
from __future__ import annotations

from ..contracts.decision import Explanation, Fact, Source, Statement
from ..contracts.evolution import PortfolioVersion
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
        return Fact(fact_id=f"cfg.{key}", label_fr=label, value=value, unit=unit, status="HYPOTHESE",
                    sources=[Source(dataset=cfg.src(path), sha256=cfg.sha256)], trace_id=f"evolution:cfg:{month_key}")
    return [
        f("band_abs", "Largeur absolue de la bande", cfg.bands.abs, "%", "bands.abs"),
        f("band_rel", "Largeur relative de la bande", cfg.bands.rel, "%", "bands.rel"),
        f("max_turnover", "Rotation maximale par mois lors d'un changement de cible", cfg.trading.max_turnover_tick,
          "%", "trading.max_turnover_tick"),
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
        Fact(fact_id=f"{key}.mois", label_fr="Mois simulé", value=f"{version.as_of:%Y-%m}", unit="texte",
             status="FICTION", sources=[Source(dataset="evolution:replay")], trace_id=f"evolution:{key}"),
    ]
    book = _book(facts, extra)
    has = book.facts.__contains__
    mois, r, dd, drift, rot, cost, lvl = (f"{key}.{k}" for k in
                                          ("mois", "r_portefeuille", "baisse", "derive", "rotation", "cout", "niveau"))
    proxies = [fid for fid in book.facts if fid.startswith(f"{key}.proxy.")]

    data_used = [_s(book, f"Mois simulé {fmt(book.facts[mois].value, 'texte')} : seuls les rendements mensuels en CAD "
                    "connus à cette date sont lus.", [mois], "FICTION")]
    if has(r):
        data_used.append(_s(book, f"Rendement du portefeuille sur le mois : {fmt(book.facts[r].value, '%')}.", [r]))
    if proxies:
        data_used.append(_s(book, "Certaines lignes n'avaient pas encore d'historique : leur indice long de "
                            "remplacement est utilisé.", proxies, "HYPOTHESE"))

    why: list[Statement] = []
    a = ev.action
    if a == "HOLD":
        why.append(_s(book, f"Toutes les lignes restent dans leurs bandes (dérive {fmt(book.facts[drift].value, '%')}) "
                      "et aucune limite n'est franchie : aucun mouvement.", [drift]))
    elif a == "REBALANCE_TO_BANDS" and ev.breaches:
        ids = [f"{key}.bande.{x}" for x in ev.breaches if has(f"{key}.bande.{x}")]
        why.append(_s(book, f"{', '.join(ev.breaches)} sort de sa bande (au plus {fmt(cfg.bands.abs, '%')} ou "
                      f"{fmt(cfg.bands.rel, '%')} de la cible) : retour à mi-chemin vers la cible.",
                      ["cfg.band_abs", "cfg.band_rel", *ids]))
    elif a == "REBALANCE_TO_BANDS":
        rules = ", ".join(sorted({t.code for t in ev.triggers if t.code == "JUDGE_VIOLATION_DRIFT"})) or "une limite"
        why.append(_s(book, f"La dérive du marché fait franchir {rules} du profil : correction minimale des seules "
                      "lignes concernées, sans rééquilibrage complet.", []))
    elif a == "REOPTIMIZE":
        why.append(_s(book, f"Le niveau de risque devient {fmt(book.facts[lvl].value, 'niveau')} à cette date "
                      "(l'horizon raccourcit) : la cible est recalculée par le moteur, puis contrôlée par le Judge.",
                      [lvl]))
    elif a == "OVERLAY_SHIFT":
        names = ", ".join(o.name for o in ev.overlays if o.active and o.delta)
        why.append(_s(book, f"Le signal d'une stratégie systématique validée a changé ({names}) : la cible se déplace "
                      "à l'intérieur des limites du profil.", [fid for o in ev.overlays for fid in o.fact_ids]))
    elif a == "REPROFILE_REQUIRED":
        codes = ", ".join(t.code for t in ev.triggers if t.blocking)
        if ev.trades:
            why.append(_s(book, f"Déclencheur bloquant ({codes}) : aucune décision stratégique ; seules des "
                          "corrections de conformité aux limites du profil ont été simulées. Une mise à jour du "
                          "profil est demandée avant toute nouvelle proposition.", []))
        else:
            why.append(_s(book, f"Déclencheur bloquant ({codes}) : aucun mouvement ; une mise à jour du profil est "
                          "demandée avant toute nouvelle proposition.", []))
    for t in ev.triggers:
        fid = f"{key}.declencheur.{t.code}"
        if has(fid) and t.code != "JUDGE_VIOLATION_DRIFT":
            why.append(_s(book, f"Déclencheur {t.code} (son seuil et la source de ce seuil sont dans le fait cité).",
                          [fid]))

    limits = [
        _s(book, "Événement de rééquilibrage illustratif : simulation éducative, aucun ordre réel.", [], "FICTION"),
        _s(book, "Les rendements décrivent le passé et ne prédisent pas l'avenir.", [], "HYPOTHESE"),
    ]
    if ev.trades and has(cost) and has(rot):
        limits.append(_s(book, f"Coût estimé des mouvements : {fmt(book.facts[cost].value, 'CAD')} pour une rotation "
                         f"de {fmt(book.facts[rot].value, '%')} ; paramètres de coût en HYPOTHESE.", [cost, rot],
                         "HYPOTHESE"))
    if has(dd):
        limits.append(_s(book, f"Baisse depuis le plus haut à cette date : {fmt(book.facts[dd].value, '%')}.", [dd]))

    wwc = [_s(book, f"Une bande plus large que {fmt(cfg.bands.abs, '%')} réduirait le nombre de mouvements, au prix "
              "d'un écart plus long à la cible.", ["cfg.band_abs"], "HYPOTHESE")]
    if a == "REOPTIMIZE":
        wwc.append(_s(book, f"Une rotation maximale de {fmt(cfg.trading.max_turnover_tick, '%')} par mois étale un "
                      "changement de niveau à la hausse sur plusieurs mois.", ["cfg.max_turnover"], "HYPOTHESE"))
    return Explanation(data_used=data_used, why=why, limits=limits, what_would_change=wwc), extra
