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


def _s(book: FactBook, text: str, ids: list[str], label="FAIT") -> Statement:
    ids = [i for i in ids if i in book.facts]
    vals = {i: fmt(book.facts[i].value, book.facts[i].unit) for i in ids}
    return Statement(
        text_fr=text.format(**{k.replace(".", "_").replace("#", "_"): v for k, v in vals.items()}),
        fact_ids=ids,
        label=label,
    )


def skeleton(
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
    f = book.facts

    def v(fid):
        return fmt(f[fid].value, f[fid].unit) if fid in f else "n.d."

    data_used = [
        Statement(
            text_fr=f"Profil de risque effectif : niveau {v(level_fid)}, dérivé de la tolérance et "
            f"de la capacité (la plus prudente l'emporte).",
            fact_ids=[level_fid],
        )
    ]
    risk_ids = [i for i in (f"{cand}.cvar_m", f"{cand}.mdd", f"{cand}.vol") if i in f]
    if risk_ids:
        data_used.append(
            Statement(
                text_fr="Mesures historiques du portefeuille proposé : CVaR mensuelle "
                f"{v(risk_ids[0])}"
                + (f", baisse maximale {v(risk_ids[1])}" if len(risk_ids) > 1 else "")
                + " (rendements mensuels en CAD, prix ajustés).",
                fact_ids=risk_ids,
            )
        )
    why = []
    for fid in active_fids[:3]:
        why.append(Statement(text_fr=f"Contrainte déterminante. {f[fid].label_fr} ({v(fid)}).", fact_ids=[fid]))
    for a in applied:
        if a.status == "applique" and a.amendment.kind != "flag_only":
            why.append(
                Statement(
                    text_fr=f"La lentille « {LENS_FR.get(a.lens, a.lens)} » a resserré le mandat : "
                    f"{a.amendment.reason_fr}.",
                    fact_ids=[i for i in a.amendment.evidence_fact_ids if i in f],
                )
            )
    if kind == "refus_encadre" and request_fids:
        why.append(
            Statement(
                text_fr="La demande telle quelle dépasse les limites du profil ; une version encadrée "
                "est proposée à la place.",
                fact_ids=[i for i in request_fids if i in f],
            )
        )
    limits = [
        Statement(
            text_fr="Les chiffres décrivent le passé (2018-2026 pour les titres réels, proxys longs "
            "étiquetés HYPOTHESE) : ils ne prédisent pas les rendements futurs.",
            fact_ids=[],
            label="HYPOTHESE",
        )
    ]
    for t in limits_extra or []:
        limits.append(Statement(text_fr=t, fact_ids=[], label="HYPOTHESE"))
    if strategy is not None:
        extra = strategy_statements(book, strategy)
        data_used += extra["data_used"]
        why += extra["why"]
        limits += extra["limits"]
    return Explanation(data_used=data_used, why=why, limits=limits, what_would_change=counterfactual_stmts)


def strategy_statements(book: FactBook, final: dict | None = None) -> dict[str, list[Statement]]:
    """Gabarits de l'étape 0 (style et sélection). Tout nombre écrit est la valeur formatée d'un Fact cité ;
    les règles citées (ACVM, FTSE…) restent dans les Facts, pas dans le texte, pour le vérificateur."""
    f = book.facts
    out: dict[str, list[Statement]] = {"data_used": [], "why": [], "limits": []}
    if "strat.style" not in f:
        return out

    def v(fid):
        return fmt(f[fid].value, f[fid].unit) if fid in f else "n.d."

    out["data_used"].append(
        Statement(
            text_fr=f"Style de composition retenu : {STYLE_FR.get(f['strat.style'].value, v('strat.style'))}. "
            "Il ne relève ni le niveau de risque, ni la "
            "part d'actions visée, ni les budgets de perte : il règle la composition (titres retenus, planchers "
            "des satellites, plafonds sectoriels). Il peut donc ajouter du risque, toujours sous ces budgets.",
            fact_ids=["strat.style"],
            label="HYPOTHESE",
        )
    )
    if "strat.n_candidates" in f:
        out["data_used"].append(
            Statement(
                text_fr=f"Classement des {v('strat.n_candidates')} titres individuels par rangs (volatilité, bêta, "
                "baisse maximale longue, dividende, corrélation au cœur), sur le jeu de départ et l'historique long.",
                fact_ids=["strat.n_candidates"],
                label="HYPOTHESE",
            )
        )
    final = final or {}
    band = final.get("band_target", "strat.band_target" if "strat.band_target" in f else None)
    if band and band in f:
        out["why"].append(
            Statement(
                text_fr=f"Part actions visée : {v(band)}, entre {v('strat.e_min')} et "
                f"{v('strat.e_cap')}. La tolérance place le portefeuille dans sa bande, la capacité la plafonne.",
                fact_ids=[band, "strat.e_min", "strat.e_cap"],
                label="HYPOTHESE",
            )
        )
    if "strat.risk_cost" in f and "strat.base_risk" in f:
        rc = f["strat.risk_cost"].value
        out["why"].append(
            Statement(
                text_fr="Effet du style et de la sélection sur le risque minimisé (CVaR mensuelle) : "
                f"{'hausse' if rc >= 0 else 'baisse'} de {fmt(abs(rc), '%')} par rapport au mandat de base "
                f"({v('strat.base_risk')}), dans les budgets du niveau.",
                fact_ids=["strat.risk_cost", "strat.base_risk"],
                label="HYPOTHESE",
            )
        )
    floors = final.get("floors") if final else None
    if floors is None:
        floors = {k[len("strat.floor.") :]: k for k in f if k.startswith("strat.floor.")}
    for t, fid in floors.items():
        rank = f"strat.rank.{t}"
        ids = [fid, rank, "strat.n_candidates"]
        cad = f"strat.floor_cad.{t}"
        if rank in f:
            text = f"Titre retenu {t} : rang {v(rank)} sur {v('strat.n_candidates')}, plancher de satellite {v(fid)}"
        else:  # FNB d'un intérêt de l'investisseur (or → GLD) : pas de classement
            ids = [fid]
            text = f"{t}, demandé par un intérêt de l'investisseur : plancher de {v(fid)}, dans le plafond du niveau"
        if cad in f:
            text += f", soit {v(cad)}"
            ids.append(cad)
        out["why"].append(Statement(text_fr=text + ".", fact_ids=[i for i in ids if i in f], label="HYPOTHESE"))
    for fid in [k for k in f if k.startswith("strat.sector_cap.")]:
        tag = fid[len("strat.sector_cap.") :]
        out["why"].append(
            Statement(
                text_fr=f"Plafond d'exposition au {sector_fr(tag)} (look-through) : {v(fid)}.",
                fact_ids=[fid],
                label="HYPOTHESE",
            )
        )
    for fid in [k for k in f if k.startswith("strat.preference_refused.")]:
        out["why"].append(
            Statement(
                text_fr=f"Pourquoi votre profil dit autrement : {f[fid].value}.", fact_ids=[fid], label="HYPOTHESE"
            )
        )
    for fid in [k for k in f if k.startswith("strat.contradiction.")]:
        out["limits"].append(
            Statement(
                text_fr=f"Réponses contradictoires, la plus prudente l'emporte : {f[fid].value}.",
                fact_ids=[fid],
                label="HYPOTHESE",
            )
        )
    for fid in [k for k in f if k.startswith("strat.flag.")]:
        out["limits"].append(
            Statement(
                text_fr=f"Signal de comportement « {flag_fr(fid[len('strat.flag.') :])} » : il règle des garde-fous, "
                "jamais l'allocation.",
                fact_ids=[fid],
                label="HYPOTHESE",
            )
        )
    for fid in final.get("clamped", []) if final else []:
        out["limits"].append(
            Statement(
                text_fr="Le débat a abaissé ou retiré un choix du style : la prudence l'emporte.",
                fact_ids=[fid],
                label="HYPOTHESE",
            )
        )
    for fid in [k for k in f if k.startswith("strat.fallback.")]:
        out["limits"].append(
            Statement(text_fr="Le style a été allégé pour rester faisable.", fact_ids=[fid], label="HYPOTHESE")
        )
    out["limits"].append(
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


def grounding_check(
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
    if client is None:
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "bedrock-runtime", region_name=region, config=Config(retries={"mode": "standard", "max_attempts": 6})
        )
    pacer = _TextUnitPacer(units_per_second) if units_per_second else None

    def call(statements: list[Statement]) -> dict[str, Any]:
        src = grounding_source(book, statements, context, docs)
        text = "\n".join(x.text_fr for x in statements)[:GROUNDING_CONTENT_MAX]
        if pacer is not None:
            pacer.wait(len(src) + len(GROUNDING_QUERY) + len(text))
        try:
            r = client.apply_guardrail(
                guardrailIdentifier=guardrail_id,
                guardrailVersion=guardrail_version,
                source="OUTPUT",
                content=[
                    {"text": {"text": src, "qualifiers": ["grounding_source"]}},
                    {"text": {"text": GROUNDING_QUERY, "qualifiers": ["query"]}},
                    {"text": {"text": text, "qualifiers": ["guard_content"]}},
                ],
            )
        except Exception as exc:  # réseau, droits, quota : rapporté, la décision continue
            return {"action": "ERROR", "error": type(exc).__name__}
        filters = {
            x.get("type"): x
            for a in r.get("assessments") or []
            for x in (a.get("contextualGroundingPolicy") or {}).get("filters", [])
        }
        g, rel = filters.get("GROUNDING", {}), filters.get("RELEVANCE", {})
        return {
            "action": r.get("action"),
            "score": g.get("score"),
            "threshold": g.get("threshold"),
            "relevance": rel.get("score"),
            "retries": (r.get("ResponseMetadata") or {}).get("RetryAttempts", 0),
        }

    sections = {
        sec: [(i, st) for i, st in enumerate(getattr(expl, sec)) if only is None or (sec, i) in only]
        for sec in SECTIONS
    }
    sections = {sec: items for sec, items in sections.items() if items}
    rows: dict[tuple[str, int], dict[str, Any]] = {}
    redo: list[tuple[str, int, Statement]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        if only is None:
            names = list(sections)
            for sec, res in zip(names, pool.map(lambda sec: call([st for _, st in sections[sec]]), names), strict=True):
                items = sections[sec]
                if res["action"] == "NONE" or len(items) == 1:
                    scope = "section" if len(items) > 1 else "statement"
                    rows.update({(sec, i): {"section": sec, "index": i, **res, "scope": scope} for i, _ in items})
                else:
                    redo += [(sec, i, st) for i, st in items]
        else:
            redo = [(sec, i, st) for sec, items in sections.items() for i, st in items]
        for (sec, i, _), res in zip(redo, pool.map(lambda item: call([item[2]]), redo), strict=True):
            rows[(sec, i)] = {"section": sec, "index": i, **res, "scope": "statement"}
    ordered = [rows[(sec, i)] for sec in SECTIONS for i, _ in sections.get(sec, []) if (sec, i) in rows]
    return summarize_grounding(ordered, [key for key, _ in docs])


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
