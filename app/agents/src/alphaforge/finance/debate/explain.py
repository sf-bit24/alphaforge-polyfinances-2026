"""Explication fidèle par construction, puis vérification affirmation par affirmation.

1. ``skeleton`` construit les 4 sections (atelier BNCD) à partir de l'enregistrement de décision :
   chaque phrase est un gabarit rempli par des Facts, donc ses chiffres sont exacts par construction.
2. ``rephrase`` (facultatif, LLM) adapte le langage au niveau de connaissances, phrase par phrase.
3. ``verify`` rejette toute phrase reformulée dont un nombre n'est pas la valeur formatée d'un des
   Facts qu'elle cite, ou qui cite un fact_id inconnu ; on retombe alors sur le gabarit.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from alphaforge.finance.contracts.decision import Explanation, Statement
from alphaforge.finance.strategy.labels import STYLE_FR, flag_fr, sector_fr

from .facts import FactBook, fmt
from .schemas import LENS_FR

_NUM = re.compile(
    r"(?<![A-Za-z_.])-?\d[\d\s]*(?:[.,]\d+)?(?![A-Za-z_])"
)  # pas les chiffres d'un identifiant (N0, cvar_m)


def _norm(s: str) -> str:
    return s.replace(" ", " ").replace("\xa0", " ").replace(" ", "").replace(",", ".").lstrip("-")


def numbers(text: str) -> set[str]:
    return {_norm(m.group()) for m in _NUM.finditer(text) if any(ch.isdigit() for ch in m.group())}


def allowed_numbers(book: FactBook, fact_ids: list[str]) -> set[str]:
    out = set()
    for fid in fact_ids:
        f = book.facts.get(fid)
        if f is not None:
            out |= numbers(fmt(f.value, f.unit))
    return out


def _unsourced(book: FactBook, st: Statement) -> tuple[list[str], list[str]]:
    """fact_id cités absents du registre, et nombres du texte qu'aucun Fact cité ne porte (triés)."""
    unknown = [fid for fid in st.fact_ids if fid not in book.facts]
    extra = numbers(st.text_fr) - allowed_numbers(book, st.fact_ids) - {"1", "2", "3", "4", "12", "95", "2022"}
    return unknown, sorted(extra)


def verify(book: FactBook, st: Statement) -> list[str]:
    """Liste des problèmes (vide = phrase acceptée), avec les identifiants : pour le code et ses erreurs."""
    unknown, extra = _unsourced(book, st)
    problems = [f"fact_id inconnu : {fid}" for fid in unknown]
    if extra:
        problems.append(f"nombres non sourcés : {extra}")
    return problems


def verify_fr(book: FactBook, st: Statement) -> list[str]:
    """Les mêmes problèmes que ``verify`` (vide dans les mêmes cas), rédigés pour l'investisseur : sans identifiant
    ni liste Python. Les nombres sont écrits à la française (« 12,5 »)."""
    unknown, extra = _unsourced(book, st)
    out = []
    if unknown:
        n = len(unknown)
        out.append("fait cité introuvable dans la décision" if n == 1 else f"{n} faits cités introuvables")
    if extra:
        nums = ", ".join(x.replace(".", ",") for x in extra)
        out.append(f"nombre non sourcé : {nums}" if len(extra) == 1 else f"nombres non sourcés : {nums}")
    return out


# Les quatre questions de l'atelier, comme l'interface les titre (app/web/src/lib/i18n/portfolio.ts).
SECTION_FR = {
    "data_used": "Quelles données ?",
    "why": "Pourquoi ce choix ?",
    "limits": "Quelles limites ?",
    "what_would_change": "Qu'est-ce qui changerait la réponse ?",
}


def kept_template_fr(section: str, index: int, problems: list[str]) -> str:
    """Ligne du rapport de reformulation : « 4e énoncé de « Pourquoi ce choix ? » : reformulation écartée
    (nombre non sourcé : 50), gabarit conservé. » ; ``index`` part de 0."""
    n = index + 1
    where = f"{n}{'er' if n == 1 else 'e'} énoncé de « {SECTION_FR.get(section, section)} »"
    return f"{where} : reformulation écartée ({' ; '.join(problems)}), gabarit conservé."


# Fenêtre des rendements mensuels que le moteur écrit avec ses mesures historiques (tools.risk_evidence) :
# « rendements mensuels CAD AAAA-MM-JJ..AAAA-MM-JJ (n mois) ».
_WINDOW = re.compile(r"(\d{4})-\d{2}-\d{2}\.\.(\d{4})-\d{2}-\d{2}")


def _past_limit(book: FactBook, cand: str) -> Statement:
    """Première limite : les chiffres décrivent le passé, sur la période réellement mesurée, jamais écrite à la main."""
    ids = _window_years(book, cand)
    period = "-".join(fmt(book.facts[i].value, book.facts[i].unit) for i in ids)
    covered = f"{period} pour les titres réels" if ids else "titres réels"
    return Statement(
        text_fr=f"Les chiffres décrivent le passé ({covered}, proxys longs étiquetés HYPOTHESE) : ils ne prédisent "
        "pas les rendements futurs.",
        fact_ids=ids,
        label="HYPOTHESE",
    )


def _window_years(book: FactBook, cand: str) -> list[str]:
    """fact_ids de la première et de la dernière année des rendements mensuels qui mesurent ``cand``.

    Les bornes sont celles de la fenêtre que le moteur a enregistrée avec ces mesures (source de ``<cand>.cvar_m``,
    ``.mdd`` ou ``.vol``) : deux Facts, rattachés à l'étape qui a fait la mesure, ajoutés une seule fois. Sans
    fenêtre enregistrée, aucun Fact, donc aucune année écrite."""
    ids = [f"{cand}.window.first_year", f"{cand}.window.last_year"]
    if all(i in book.facts for i in ids):
        return ids
    for fid in (f"{cand}.cvar_m", f"{cand}.mdd", f"{cand}.vol"):
        fact = book.facts.get(fid)
        source = fact.sources[0] if fact is not None else None
        found = _WINDOW.search(source.processing or "") if source is not None else None
        if found:
            window = found.group(0)
            return [
                book.add(
                    key,
                    label,
                    int(found.group(n)),
                    "année",
                    dataset=source.dataset,
                    processing=f"{edge} de la fenêtre {window} des mesures historiques ({fid})",
                    trace_id=fact.trace_id,
                )
                for n, key, label, edge in (
                    (1, ids[0], "Première année des rendements mensuels mesurés (titres réels)", "début"),
                    (2, ids[1], "Dernière année des rendements mensuels mesurés (titres réels)", "fin"),
                )
            ]
    return []


def _s(book: FactBook, text: str, ids: list[str], label="FAIT") -> Statement:
    ids = [i for i in ids if i in book.facts]
    vals = {i: fmt(book.facts[i].value, book.facts[i].unit) for i in ids}
    return Statement(
        text_fr=text.format(**{k.replace(".", "_").replace("#", "_"): v for k, v in vals.items()}),
        fact_ids=ids,
        label=label,
    )


def _shown(facts: dict[str, Any], fid: str) -> str:
    """Valeur affichée d'un Fact (celle que ``verify`` admet), ou « n.d. » s'il manque."""
    return fmt(facts[fid].value, facts[fid].unit) if fid in facts else "n.d."


def skeleton(  # noqa: PLR0913 - signature gardée : pipeline.py passe ces entrées de l'enregistrement par mot-clé
    book: FactBook,
    *,
    kind: str,
    level_fid: str,
    cand: str,
    active_fids: list[str],
    applied: list,
    counterfactual_stmts: list[Statement],
    request_fids: list[str] | None = None,
    limits_extra: list[str] | None = None,
    strategy: dict | None = None,
) -> Explanation:
    data_used = _data_used_statements(book.facts, level_fid, cand)
    why = _why_statements(book.facts, active_fids, applied, kind, request_fids)
    limits = [
        _past_limit(book, cand),
    ]
    limits += [Statement(text_fr=t, fact_ids=[], label="HYPOTHESE") for t in limits_extra or []]
    if strategy is not None:
        extra = strategy_statements(book, strategy)
        data_used += extra["data_used"]
        why += extra["why"]
        limits += extra["limits"]
    return Explanation(data_used=data_used, why=why, limits=limits, what_would_change=counterfactual_stmts)


def _data_used_statements(facts: dict[str, Any], level_fid: str, cand: str) -> list[Statement]:
    """Niveau de risque effectif, puis les mesures historiques du portefeuille candidat ``cand`` qui existent."""
    out = [
        Statement(
            text_fr=f"Profil de risque effectif : niveau {_shown(facts, level_fid)}, dérivé de la tolérance et "
            f"de la capacité (la plus prudente l'emporte).",
            fact_ids=[level_fid],
        )
    ]
    risk_ids = [i for i in (f"{cand}.cvar_m", f"{cand}.mdd", f"{cand}.vol") if i in facts]
    if risk_ids:
        out.append(
            Statement(
                text_fr="Mesures historiques du portefeuille proposé : CVaR mensuelle "
                f"{_shown(facts, risk_ids[0])}"
                + (f", baisse maximale {_shown(facts, risk_ids[1])}" if len(risk_ids) > 1 else "")
                + " (rendements mensuels en CAD, prix ajustés).",
                fact_ids=risk_ids,
            )
        )
    return out


def _why_statements(
    facts: dict[str, Any], active_fids: list[str], applied: list, kind: str, request_fids: list[str] | None
) -> list[Statement]:
    """Les trois premières contraintes déterminantes, les resserrements appliqués par les lentilles, puis le refus
    encadré d'une demande hors profil."""
    out = [
        Statement(text_fr=f"Contrainte déterminante. {facts[fid].label_fr} ({_shown(facts, fid)}).", fact_ids=[fid])
        for fid in active_fids[:3]
    ]
    out += [
        Statement(
            text_fr=f"La lentille « {LENS_FR.get(a.lens, a.lens)} » a resserré le mandat : {a.amendment.reason_fr}.",
            fact_ids=[i for i in a.amendment.evidence_fact_ids if i in facts],
        )
        for a in applied
        if a.status == "applique" and a.amendment.kind != "flag_only"
    ]
    if kind == "refus_encadre" and request_fids:
        out.append(
            Statement(
                text_fr="La demande telle quelle dépasse les limites du profil ; une version encadrée "
                "est proposée à la place.",
                fact_ids=[i for i in request_fids if i in facts],
            )
        )
    return out


def strategy_statements(book: FactBook, final: dict | None = None) -> dict[str, list[Statement]]:
    """Gabarits de l'étape 0 (style et sélection). Tout nombre écrit est la valeur formatée d'un Fact cité ;
    les règles citées (ACVM, FTSE…) restent dans les Facts, pas dans le texte, pour le vérificateur."""
    facts = book.facts
    if "strat.style" not in facts:
        return {"data_used": [], "why": [], "limits": []}
    final = final or {}
    return {
        "data_used": _style_data_used(facts),
        "why": _style_why(facts, final),
        "limits": _style_limits(facts, final),
    }


def _with_prefix(facts: dict[str, Any], prefix: str) -> list[str]:
    return [k for k in facts if k.startswith(prefix)]


def _style_data_used(facts: dict[str, Any]) -> list[Statement]:
    """Style retenu (ce qu'il règle et ce qu'il ne règle pas), puis le classement des titres individuels."""
    out = [
        Statement(
            text_fr="Style de composition retenu : "
            f"{STYLE_FR.get(facts['strat.style'].value, _shown(facts, 'strat.style'))}. "
            "Il ne relève ni le niveau de risque, ni la "
            "part d'actions visée, ni les budgets de perte : il règle la composition (titres retenus, planchers "
            "des satellites, plafonds sectoriels). Il peut donc ajouter du risque, toujours sous ces budgets.",
            fact_ids=["strat.style"],
            label="HYPOTHESE",
        )
    ]
    if "strat.n_candidates" in facts:
        out.append(
            Statement(
                text_fr=f"Classement des {_shown(facts, 'strat.n_candidates')} titres individuels par rangs "
                "(volatilité, bêta, baisse maximale longue, dividende, corrélation au cœur), sur le jeu de départ "
                "et l'historique long.",
                fact_ids=["strat.n_candidates"],
                label="HYPOTHESE",
            )
        )
    return out


def _style_why(facts: dict[str, Any], final: dict) -> list[Statement]:
    """Part actions visée, effet du style sur le risque minimisé, planchers des titres retenus, plafonds sectoriels
    et préférences refusées."""
    out = []
    band = final.get("band_target", "strat.band_target" if "strat.band_target" in facts else None)
    if band and band in facts:
        out.append(
            Statement(
                text_fr=f"Part actions visée : {_shown(facts, band)}, entre {_shown(facts, 'strat.e_min')} et "
                f"{_shown(facts, 'strat.e_cap')}. La tolérance place le portefeuille dans sa bande, la capacité la "
                "plafonne.",
                fact_ids=[band, "strat.e_min", "strat.e_cap"],
                label="HYPOTHESE",
            )
        )
    if "strat.risk_cost" in facts and "strat.base_risk" in facts:
        out.append(_risk_cost_statement(facts))
    out += _floor_statements(facts, final.get("floors"))
    out += [
        Statement(
            text_fr=f"Plafond d'exposition au {sector_fr(fid[len('strat.sector_cap.') :])} (look-through) : "
            f"{_shown(facts, fid)}.",
            fact_ids=[fid],
            label="HYPOTHESE",
        )
        for fid in _with_prefix(facts, "strat.sector_cap.")
    ]
    out += [
        Statement(
            text_fr=f"Pourquoi votre profil dit autrement : {facts[fid].value}.", fact_ids=[fid], label="HYPOTHESE"
        )
        for fid in _with_prefix(facts, "strat.preference_refused.")
    ]
    return out


def _risk_cost_statement(facts: dict[str, Any]) -> Statement:
    cost = facts["strat.risk_cost"].value
    return Statement(
        text_fr="Effet du style et de la sélection sur le risque minimisé (CVaR mensuelle) : "
        f"{'hausse' if cost >= 0 else 'baisse'} de {fmt(abs(cost), '%')} par rapport au mandat de base "
        f"({_shown(facts, 'strat.base_risk')}), dans les budgets du niveau.",
        fact_ids=["strat.risk_cost", "strat.base_risk"],
        label="HYPOTHESE",
    )


def _floor_statements(facts: dict[str, Any], floors: dict[str, str] | None) -> list[Statement]:
    """Un énoncé par plancher de satellite : ceux du débat (``floors``), sinon tous ceux de l'étape 0."""
    if floors is None:
        floors = {k[len("strat.floor.") :]: k for k in _with_prefix(facts, "strat.floor.")}
    return [_floor_statement(facts, ticker, fid) for ticker, fid in floors.items()]


def _floor_statement(facts: dict[str, Any], ticker: str, fid: str) -> Statement:
    rank, cad = f"strat.rank.{ticker}", f"strat.floor_cad.{ticker}"
    if rank in facts:
        ids = [fid, rank, "strat.n_candidates"]
        text = (
            f"Titre retenu {ticker} : rang {_shown(facts, rank)} sur {_shown(facts, 'strat.n_candidates')}, "
            f"plancher de satellite {_shown(facts, fid)}"
        )
    else:  # FNB d'un intérêt de l'investisseur (or → GLD) : pas de classement
        ids = [fid]
        text = (
            f"{ticker}, demandé par un intérêt de l'investisseur : plancher de {_shown(facts, fid)}, "
            "dans le plafond du niveau"
        )
    if cad in facts:
        text += f", soit {_shown(facts, cad)}"
        ids.append(cad)
    return Statement(text_fr=text + ".", fact_ids=[i for i in ids if i in facts], label="HYPOTHESE")


def _style_limits(facts: dict[str, Any], final: dict) -> list[Statement]:
    """Réponses contradictoires, signaux de comportement, choix abaissés par le débat, style allégé, puis les
    hypothèses de conception du style et de la sélection."""
    out = [
        Statement(
            text_fr=f"Réponses contradictoires, la plus prudente l'emporte : {facts[fid].value}.",
            fact_ids=[fid],
            label="HYPOTHESE",
        )
        for fid in _with_prefix(facts, "strat.contradiction.")
    ]
    out += [
        Statement(
            text_fr=f"Signal de comportement « {flag_fr(fid[len('strat.flag.') :])} » : il règle des garde-fous, "
            "jamais l'allocation.",
            fact_ids=[fid],
            label="HYPOTHESE",
        )
        for fid in _with_prefix(facts, "strat.flag.")
    ]
    out += [
        Statement(
            text_fr="Le débat a abaissé ou retiré un choix du style : la prudence l'emporte.",
            fact_ids=[fid],
            label="HYPOTHESE",
        )
        for fid in final.get("clamped", [])
    ]
    out += [
        Statement(text_fr="Le style a été allégé pour rester faisable.", fact_ids=[fid], label="HYPOTHESE")
        for fid in _with_prefix(facts, "strat.fallback.")
    ]
    out.append(
        Statement(
            text_fr="Les règles du style et de la sélection sont des hypothèses de conception à valider par "
            "l'équipe. L'univers a "
            "été choisi aujourd'hui (biais du survivant) : un bon rang passé ne prédit pas les rendements, et le "
            "momentum sur douze mois hors dernier mois n'est montré qu'en sensibilité.",
            fact_ids=[],
            label="HYPOTHESE",
        )
    )
    return out


def rephrase(
    book: FactBook, expl: Explanation, knowledge_level: str | None, model_factory=None
) -> tuple[Explanation, list[str]]:
    """Reformulation LLM phrase par phrase ; toute phrase qui échoue à ``verify`` garde son gabarit."""
    from strands import Agent

    from .roles import SONNET, model

    sections = expl.model_dump()
    agent = Agent(
        model=(model_factory or model)(SONNET, "explainer"),
        name="explainer",
        callback_handler=None,
        system_prompt="Tu reformules des phrases d'explication financière pour un investisseur de niveau "
        f"« {knowledge_level or 'debutant'} ». Garde EXACTEMENT les mêmes nombres, écrits "
        "pareil, n'en ajoute aucun, n'ajoute aucun conseil. Réponds en JSON : la même "
        "structure, seuls les champs text_fr changent.",
    )
    with book.step("explainer", tool="llm", model_id=SONNET):
        res = agent(json.dumps(sections, ensure_ascii=False), structured_output_model=Explanation)
    new = res.structured_output
    report, out = [], {}
    for sec in ("data_used", "why", "limits", "what_would_change"):
        orig, cand = getattr(expl, sec), getattr(new, sec)
        kept = []
        for i, st in enumerate(orig):
            alt = cand[i] if i < len(cand) else None
            if alt is not None:
                alt = alt.model_copy(update={"fact_ids": st.fact_ids, "label": st.label})
                probs = verify_fr(book, alt)
                if not probs:
                    kept.append(alt)
                    continue
                report.append(kept_template_fr(sec, i, probs))
            kept.append(st)
        out[sec] = kept
    return Explanation(**out), report


SECTIONS = ("data_used", "why", "limits", "what_would_change")
GROUNDING_QUERY = "Expliquer la proposition de portefeuille"
GROUNDING_SOURCE_MAX = 100_000  # limites d'ApplyGuardrail : source d'ancrage, puis contenu vérifié
GROUNDING_CONTENT_MAX = 5_000
# Quota du compte pour l'ancrage contextuel : 106 unités de texte par seconde, rafale comprise (1 unité = 1 000
# caractères de source, de question et de contenu). Un appel isolé prend moins d'une seconde ; au-delà du quota, les
# reprises font attendre bien plus. On étale donc les appels avec de la marge, et les reprises restent un filet.
GROUNDING_TEXT_UNITS_PER_SECOND = 80.0
GROUNDING_WORKERS = 2


class _TextUnitPacer:
    """Réserve à chaque appel un créneau proportionnel à sa taille, partagé entre les fils."""

    def __init__(self, units_per_second: float):
        self.rate, self.lock, self.next_start = units_per_second, threading.Lock(), 0.0

    def wait(self, chars: int) -> None:
        units = max(1, math.ceil(chars / 1000))
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next_start)
            self.next_start = start + units / self.rate
        if start > now:
            time.sleep(start - now)


def grounding_context(book: FactBook, checks: Iterable[Any], verdicts: dict[str, str]) -> str:
    """Ce que la décision enregistre elle-même : limites vérifiées par le Judge (description, dérivation),
    étapes tracées qui ont un message, verdicts des lentilles au second tour. Jamais un texte écrit pour l'ancrage."""
    lines = [f"Limite {c.rule_id} : {c.description_fr} ; dérivée de : {c.derived_from}" for c in checks]
    for ev in book.trace:
        text = " ".join(x for x in (ev.message, ev.output_summary) if x)
        if text:
            lines.append(f"Étape {ev.tool or ev.agent} : {text}")
    lines += [f"Verdict de la lentille « {lens} » au second tour : {v}" for lens, v in sorted(verdicts.items())]
    return "\n".join(lines)


def grounding_source(
    book: FactBook, st: Statement | Sequence[Statement], context: str, docs: Sequence[tuple[str, str]]
) -> str:
    """Source d'un énoncé (ou d'une section) : faits cités, puis la décision, puis les fiches de méthode (coupées en
    dernier, à la limite d'ApplyGuardrail)."""
    statements = [st] if isinstance(st, Statement) else list(st)
    fids = list(dict.fromkeys(fid for x in statements for fid in x.fact_ids))
    cited = "\n".join(
        f"{f.label_fr} : {fmt(f.value, f.unit)} ({f.status})" for fid in fids if (f := book.facts.get(fid))
    )
    parts = [
        f"Faits cités :\n{cited}" if cited else "",
        f"Décision :\n{context}" if context else "",
        "Méthodologie :\n" + "\n\n".join(f"# {key}\n{text}" for key, text in docs) if docs else "",
    ]
    return "\n\n".join(x for x in parts if x)[:GROUNDING_SOURCE_MAX] or "(aucune source)"


def grounding_check(  # noqa: PLR0913 - signature gardée : pipeline.py et les tests passent ces réglages par mot-clé
    book: FactBook,
    expl: Explanation,
    guardrail_id: str | None,
    guardrail_version: str | None,
    region: str = "us-east-1",
    *,
    context: str = "",
    docs: Sequence[tuple[str, str]] = (),
    only: set[tuple[str, int]] | None = None,
    client: Any = None,
    workers: int = GROUNDING_WORKERS,
    units_per_second: float | None = GROUNDING_TEXT_UNITS_PER_SECOND,
) -> dict | None:
    """Filet final : ancrage contextuel Bedrock Guardrails, avec un résultat par énoncé.

    Une section entière est d'abord vérifiée en un appel (source : les faits cités par ses énoncés, la décision,
    les fiches de méthode) ; si le guardrail l'ancre, chacun de ses énoncés l'est. Sinon ses énoncés sont revérifiés
    un par un, pour savoir lequel ne l'est pas. Avec ``only`` (gabarits remis), on vérifie directement énoncé par
    énoncé. L'action est celle que rend le guardrail (son seuil fait foi) ; une erreur d'appel est rapportée sans
    faire échouer la décision.
    """
    if not guardrail_id:
        return None
    if not guardrail_version or str(guardrail_version).upper() == "DRAFT":
        raise ValueError("guardrail : version numérotée requise (jamais DRAFT)")
    call = _GuardrailCall(
        client=client if client is not None else _bedrock_runtime(region),
        guardrail_id=guardrail_id,
        guardrail_version=guardrail_version,
        book=book,
        context=context,
        docs=docs,
        pacer=_TextUnitPacer(units_per_second) if units_per_second else None,
    )
    sections = _statements_to_check(expl, only)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        if only is None:
            rows, redo = _check_sections(pool, call, sections)
        else:
            rows, redo = {}, [(sec, i, st) for sec, items in sections.items() for i, st in items]
        for (sec, i, _), res in zip(redo, pool.map(lambda item: call([item[2]]), redo), strict=True):
            rows[(sec, i)] = _row(sec, i, res, "statement")
    ordered = [rows[(sec, i)] for sec in SECTIONS for i, _ in sections.get(sec, []) if (sec, i) in rows]
    return summarize_grounding(ordered, [key for key, _ in docs])


def _bedrock_runtime(region: str) -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        "bedrock-runtime", region_name=region, config=Config(retries={"mode": "standard", "max_attempts": 6})
    )


@dataclass(frozen=True)
class _GuardrailCall:
    """Un appel ApplyGuardrail sur des énoncés : leur source d'ancrage, la question, puis leur texte (un par ligne)."""

    client: Any
    guardrail_id: str
    guardrail_version: str
    book: FactBook
    context: str
    docs: Sequence[tuple[str, str]]
    pacer: _TextUnitPacer | None

    def __call__(self, statements: list[Statement]) -> dict[str, Any]:
        src = grounding_source(self.book, statements, self.context, self.docs)
        text = "\n".join(x.text_fr for x in statements)[:GROUNDING_CONTENT_MAX]
        if self.pacer is not None:
            self.pacer.wait(len(src) + len(GROUNDING_QUERY) + len(text))
        try:
            response = self.client.apply_guardrail(
                guardrailIdentifier=self.guardrail_id,
                guardrailVersion=self.guardrail_version,
                source="OUTPUT",
                content=[
                    {"text": {"text": src, "qualifiers": ["grounding_source"]}},
                    {"text": {"text": GROUNDING_QUERY, "qualifiers": ["query"]}},
                    {"text": {"text": text, "qualifiers": ["guard_content"]}},
                ],
            )
        except Exception as exc:  # réseau, droits, quota : rapporté, la décision continue
            return {"action": "ERROR", "error": type(exc).__name__}
        return _grounding_result(response)


def _grounding_result(response: dict[str, Any]) -> dict[str, Any]:
    """Action rendue par le guardrail, score et seuil du filtre d'ancrage, score de pertinence et reprises."""
    filters = {
        x.get("type"): x
        for a in response.get("assessments") or []
        for x in (a.get("contextualGroundingPolicy") or {}).get("filters", [])
    }
    grounding, relevance = filters.get("GROUNDING", {}), filters.get("RELEVANCE", {})
    return {
        "action": response.get("action"),
        "score": grounding.get("score"),
        "threshold": grounding.get("threshold"),
        "relevance": relevance.get("score"),
        "retries": (response.get("ResponseMetadata") or {}).get("RetryAttempts", 0),
    }


def _statements_to_check(
    expl: Explanation, only: set[tuple[str, int]] | None
) -> dict[str, list[tuple[int, Statement]]]:
    """Énoncés à vérifier (tous, ou ceux de ``only``) par section, sans les sections vides, dans l'ordre de SECTIONS."""
    sections = {
        sec: [(i, st) for i, st in enumerate(getattr(expl, sec)) if only is None or (sec, i) in only]
        for sec in SECTIONS
    }
    return {sec: items for sec, items in sections.items() if items}


def _check_sections(
    pool: ThreadPoolExecutor, call: _GuardrailCall, sections: dict[str, list[tuple[int, Statement]]]
) -> tuple[dict[tuple[str, int], dict[str, Any]], list[tuple[str, int, Statement]]]:
    """Un appel par section. Une section ancrée (ou d'un seul énoncé) donne son résultat à chacun de ses énoncés ;
    les énoncés des autres sont rendus à part, pour être revérifiés un par un."""
    rows: dict[tuple[str, int], dict[str, Any]] = {}
    redo: list[tuple[str, int, Statement]] = []
    names = list(sections)
    for sec, res in zip(names, pool.map(lambda sec: call([st for _, st in sections[sec]]), names), strict=True):
        items = sections[sec]
        if res["action"] == "NONE" or len(items) == 1:
            scope = "section" if len(items) > 1 else "statement"
            rows.update({(sec, i): _row(sec, i, res, scope) for i, _ in items})
        else:
            redo += [(sec, i, st) for i, st in items]
    return rows, redo


def _row(sec: str, index: int, res: dict[str, Any], scope: str) -> dict[str, Any]:
    return {"section": sec, "index": index, **res, "scope": scope}


def summarize_grounding(rows: list[dict[str, Any]], sources: list[str]) -> dict[str, Any]:
    """Résultat d'ensemble : ``GUARDRAIL_INTERVENED`` si un énoncé l'est, ``ERROR`` si aucun n'a pu être vérifié."""
    ok = [r for r in rows if r.get("action") != "ERROR"]
    below = [r for r in ok if r.get("action") == "GUARDRAIL_INTERVENED"]
    scores = [r["score"] for r in ok if r.get("score") is not None]
    thresholds = {r["threshold"] for r in ok if r.get("threshold") is not None}
    return {
        "action": "ERROR" if rows and not ok else ("GUARDRAIL_INTERVENED" if below else "NONE"),
        "method": "per_statement",
        "checked": len(ok),
        "below": len(below),
        "errors": len(rows) - len(ok),
        "retries": sum(r.get("retries") or 0 for r in rows),
        "min_score": min(scores) if scores else None,
        "threshold": thresholds.pop() if len(thresholds) == 1 else None,
        "sources": sources,
        "statements": rows,
    }


def keep_grounded(
    expl: Explanation, template: Explanation, grounding: dict[str, Any] | None
) -> tuple[Explanation, list[tuple[str, int]]]:
    """Un énoncé reformulé que le guardrail n'ancre pas reprend son gabarit (même règle que ``verify``)."""
    if not grounding:
        return expl, []
    out = {sec: list(getattr(expl, sec)) for sec in SECTIONS}
    reverted = []
    for r in grounding.get("statements", []):
        sec, i = r["section"], r["index"]
        if r.get("action") != "GUARDRAIL_INTERVENED" or i >= len(getattr(template, sec)):
            continue
        tpl = getattr(template, sec)[i]
        if out[sec][i].text_fr != tpl.text_fr:
            out[sec][i] = tpl
            reverted.append((sec, i))
    return Explanation(**out), reverted


def merge_grounding(first: dict[str, Any], again: dict[str, Any] | None) -> dict[str, Any]:
    """Remplace les lignes revérifiées (gabarits remis) et recalcule le résultat d'ensemble."""
    if not again:
        return first
    redo = {(r["section"], r["index"]): r for r in again["statements"]}
    rows = [redo.get((r["section"], r["index"]), r) for r in first["statements"]]
    return summarize_grounding(rows, first["sources"])
