"""Explication fidèle par construction, puis vérification affirmation par affirmation.

1. ``skeleton`` construit les 4 sections (atelier BNCD) à partir de l'enregistrement de décision :
   chaque phrase est un gabarit rempli par des Facts, donc ses chiffres sont exacts par construction.
2. ``rephrase`` (facultatif, LLM) adapte le langage au niveau de connaissances, phrase par phrase.
3. ``verify`` rejette toute phrase reformulée dont un nombre n'est pas la valeur formatée d'un des
   Facts qu'elle cite, ou qui cite un fact_id inconnu ; on retombe alors sur le gabarit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from alphaforge.finance.contracts.decision import Explanation, Statement
from alphaforge.finance.policy.compiler import (
    DollarRuleProtection,
    GoalRef,
    NoMandateCause,
    ProfileChange,
    ProtectionLevers,
)
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
            Statement(text_fr="Le débat a abaissé ou retiré un choix du style : la prudence l'emporte.",
                      fact_ids=[fid], label="HYPOTHESE")
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


def grounding_check(
    book: FactBook,
    expl: Explanation,
    guardrail_id: str | None,
    guardrail_version: str | None,
    region: str = "us-east-1",
) -> dict | None:
    """Filet final : ancrage contextuel Bedrock Guardrails (si un guardrail est configuré)."""
    if not guardrail_id:
        return None
    if not guardrail_version or str(guardrail_version).upper() == "DRAFT":
        raise ValueError("guardrail : version numérotée requise (jamais DRAFT)")
    import boto3

    src = json.dumps(
        [{"id": k, "label": x.label_fr, "value": fmt(x.value, x.unit)} for k, x in book.facts.items()],
        ensure_ascii=False,
    )[:100_000]
    text = " ".join(s.text_fr for sec in (expl.data_used, expl.why, expl.limits, expl.what_would_change) for s in sec)
    r = boto3.client("bedrock-runtime", region_name=region).apply_guardrail(
        guardrailIdentifier=guardrail_id,
        guardrailVersion=guardrail_version,
        source="OUTPUT",
        content=[
            {"text": {"text": src, "qualifiers": ["grounding_source"]}},
            {"text": {"text": "Expliquer la proposition de portefeuille", "qualifiers": ["query"]}},
            {"text": {"text": text[:5000], "qualifiers": ["guard_content"]}},
        ],
    )
    return {"action": r.get("action"), "assessments": r.get("assessments")}


# --------------------------------------------------------------------------- décision sans allocation

MUST_HAVE_FR = {"investable_wealth": "le montant à investir", "goals.horizon": "l'horizon de placement"}
PLANNING_LOSS_FR = "la plus petite perte de planification des portefeuilles possibles"
SAME_VALUE = 1e-12
NECESSARY_FR = " serait nécessaire pour qu'une allocation soit possible"
# Libellé de l'objectif principal du questionnaire (from_profile_view) : « objectif : <code de l'option> », code
# anglais brut (« retirement ») ; l'explication le nomme « votre objectif principal ».
MAIN_GOAL_PREFIX = "objectif : "
# Entrées de missing_info qui ne sont pas des champs du questionnaire : champs obligatoires du mandat (status.must_have)
# et dimensions que l'adaptateur (from_profile_view) ajoute quand le profil n'en dit rien.
MISSING_ALIASES = {
    "investable_wealth": "context.amount_cad",
    "goals.horizon": "horizon.horizon_band",
    "horizon": "horizon.horizon_band",
}
DIMENSION_FR = {"risk_tolerance": "tolérance au risque", "risk_capacity": "capacité à prendre des risques"}
# Mots de liaison retirés en fin de libellé quand on coupe ses nombres (« Réaction à une baisse de 20 % »).
LINK_WORDS_FR = {"de", "des", "du", "dans", "les", "la", "le", "sous", "sur", "en", "à", "au", "aux", "par"}
# Entrée de missing_info que from_profile_view ajoute quand le profil ne dit rien de l'horizon : il retient alors un
# horizon prudent d'un an pour l'objectif principal. Ce n'est pas une réponse de l'investisseur.
DEFAULT_HORIZON_MARK = "horizon"


def _without_numbers(label: str) -> str:
    """Libellé coupé avant son premier nombre : « Réaction à une baisse de 20 % » → « Réaction à une baisse ». Une
    phrase sans Fact n'écrit aucun chiffre (règle des nombres du volet)."""
    match = re.search(r"\d", label)
    if match is None:
        return label
    head = label[: match.start()]
    if "," in head or "(" in head:  # « …, en hausse de 60 % », « … (3 dernières années) »
        head = head[: max(head.rfind(","), head.rfind("("))]
    words = head.split()
    while words and words[-1].lower() in LINK_WORDS_FR:
        words.pop()
    return " ".join(words)


def _lower_first(label: str) -> str:
    """Minuscule initiale dans une liste (« Montant à investir » → « montant à investir »), sauf pour un sigle."""
    if len(label) > 1 and label[1].isupper():
        return label
    return label[:1].lower() + label[1:]


def missing_fields_fr(missing: list[str]) -> list[str]:
    """Champs manquants nommés en français, sans doublon, dans l'ordre du questionnaire.

    Une entrée de ``missing_info`` est un identifiant complet (``context.amount_cad``), le nom court d'un champ de
    ``completeness.missing`` (``approach``), un champ obligatoire du mandat (``investable_wealth``) ou une dimension
    (``risk_tolerance``). Elle prend le libellé français de profile/questionnaire.yaml, sans ses nombres. Une entrée
    inconnue reste lisible : « foo_bar » devient « foo bar ». ``missing_info`` lui-même garde les identifiants.
    """
    from alphaforge.profile.questionnaire import default_questionnaire  # import local : l'en-tête reste inchangé

    fields = default_questionnaire().fields
    rank = {field_id: index for index, field_id in enumerate(fields)}
    by_name = {spec.name: field_id for field_id, spec in fields.items()}
    first_of_dimension: dict[str, int] = {}
    for field_id, index in rank.items():
        first_of_dimension.setdefault(field_id.split(".", 1)[0], index)
    named: dict[str, int] = {}
    for entry in missing:
        alias = MISSING_ALIASES.get(entry, entry)
        field_id = alias if alias in fields else by_name.get(alias)
        if field_id is not None:
            label, index = fields[field_id].label_text("fr"), rank[field_id]
        else:
            label = DIMENSION_FR.get(entry) or entry.rsplit(".", 1)[-1].replace("_", " ")
            index = first_of_dimension.get(entry, len(rank))
        text = _lower_first(_without_numbers(label)) or "un champ du profil"
        named[text] = min(index, named.get(text, index))
    return sorted(named, key=lambda text: named[text])


def no_allocation_explanation(
    book: FactBook, kind: str, cause: NoMandateCause, missing_info: list[str], level_fid: str
) -> Explanation:
    """Explication d'une décision sans allocation (``protection``, ``incomplet`` ou ``position_attente``).

    Elle nomme la cause que la compilation a inscrite dans sa trace (règle des dollars, statut du profil, champ
    obligatoire absent, confiance) et le levier qui changerait la réponse. Chaque nombre écrit est la valeur formatée
    d'un Fact cité, rattaché à l'étape de compilation (celle du Fact ``level``). « Compléter : … » n'apparaît que
    pour un profil à qui il manque vraiment des informations.
    """
    data_used = [Statement(text_fr="Profil analysé selon les règles déterministes du mandat.", fact_ids=[level_fid])]
    if kind == "protection":
        return _protection_explanation(book, cause, missing_info, level_fid, data_used)
    why, change = _incomplete_statements(book, kind, cause, missing_info, level_fid)
    limits = [
        Statement(text_fr="Aucune allocation n'est calculée tant que le profil n'est pas complété.", label="HYPOTHESE")
    ]
    return Explanation(data_used=data_used, why=why, limits=limits, what_would_change=change)


def _incomplete_statements(
    book: FactBook, kind: str, cause: NoMandateCause, missing_info: list[str], level_fid: str
) -> tuple[list[Statement], list[Statement]]:
    """Profil incomplet (``incomplet``) ou en attente (``position_attente``) : champs manquants, confiance."""
    tid = book.facts[level_fid].trace_id
    must = [MUST_HAVE_FR.get(name, name) for name in cause.must_have_missing]
    if kind != "incomplet":
        text = (
            "Le profil n'est pas encore complet : une position d'attente prudente s'applique, sans allocation calculée."
        )
    elif must:
        what = "une information indispensable" if len(must) == 1 else "des informations indispensables"
        text = (
            f"Le profil ne permet pas encore une proposition : il manque {what} au calcul ({', '.join(must)}) ; "
            "aucune allocation n'est calculée."
        )
    else:
        text = (
            "Le profil ne permet pas encore une proposition : des informations manquent ; aucune allocation n'est "
            "calculée."
        )
    why = [Statement(text_fr=text, fact_ids=[level_fid])]
    change: list[Statement] = []
    if cause.low_confidence:
        src = cause.status_yaml_path or "risk_levels.yaml#status"
        conf = book.add(
            "attente.confidence",
            "Confiance du profil",
            cause.confidence,
            "%",
            dataset="profil : confidence",
            trace_id=tid,
        )
        need = book.add(
            "attente.completeness_min",
            "Confiance minimale pour une proposition",
            cause.completeness_min,
            "%",
            dataset=f"{src}.completeness_min",
            trace_id=tid,
        )
        why.append(
            Statement(
                text_fr=f"La confiance du profil ({fmt(cause.confidence, '%')}) est "
                f"{_under(fmt(cause.confidence, '%'), fmt(cause.completeness_min, '%'))} le minimum requis pour une "
                f"proposition ({fmt(cause.completeness_min, '%')}).",
                fact_ids=[conf, need],
            )
        )
        change.append(
            Statement(
                text_fr="Confirmer ou préciser les réponses du profil, pour que sa confiance atteigne au moins "
                f"{fmt(cause.completeness_min, '%')}.",
                fact_ids=[need],
                label="HYPOTHESE",
            )
        )
    missing = missing_fields_fr(list(missing_info) or cause.must_have_missing)
    if missing or not change:  # sans cause connue, le statut INCOMPLETE vient du profil lui-même
        change.insert(
            0, Statement(text_fr="Compléter : " + ", ".join(missing or ["le profil"]) + ".", label="HYPOTHESE")
        )
    return why, change


def _protection_explanation(
    book: FactBook, cause: NoMandateCause, missing_info: list[str], level_fid: str, data_used: list[Statement]
) -> Explanation:
    """Mode protection : le profil le signale (statut PROTECTION), ou la règle des dollars ne laisse aucune part
    d'actions dont la perte de planification tienne dans l*. Les deux causes peuvent s'additionner, et un profil en
    protection peut aussi manquer d'informations : « Compléter : … » reste alors un levier."""
    tid = book.facts[level_fid].trace_id
    why: list[Statement] = []
    change: list[Statement] = []
    must = [MUST_HAVE_FR.get(name, name) for name in cause.must_have_missing]
    missing = missing_fields_fr(list(missing_info) or cause.must_have_missing)
    if DEFAULT_HORIZON_MARK in missing_info and cause.dollar_rule is not None:  # l'horizon par défaut fixe T : en tête
        first = missing_fields_fr([DEFAULT_HORIZON_MARK])
        missing = first + [name for name in missing if name not in first]
    if missing:
        change.append(Statement(text_fr="Compléter : " + ", ".join(missing) + ".", label="HYPOTHESE"))
    limits = [
        Statement(
            text_fr=f"En mode protection, le niveau reste {fmt(book.facts[level_fid].value, 'niveau')} et aucune "
            "allocation n'est calculée ; le mandat prévoit d'en parler avec une personne qualifiée.",
            fact_ids=[level_fid],
            label="HYPOTHESE",
        )
    ]
    if cause.profile_protection:
        fid = book.add(
            "protection.profile_status",
            "Statut transmis par le profil",
            "PROTECTION",
            "texte",
            dataset=cause.status_yaml_path or "profil : status",
            processing="statut du profil (signaux de vulnérabilité) ; status.PROTECTION : niveau N0, renvoi humain",
            trace_id=tid,
        )
        why.append(
            Statement(
                text_fr="Votre profil signale une situation de vulnérabilité (statut PROTECTION) : par prudence, "
                "aucune allocation n'est calculée.",
                fact_ids=[fid],
            )
        )
        change.append(
            Statement(
                text_fr="Revoir votre situation avec une personne qualifiée : tant que le profil signale une "
                "vulnérabilité, aucune allocation n'est calculée.",
                fact_ids=[fid],
                label="HYPOTHESE",
            )
        )
    if cause.dollar_rule is not None:
        facts = _ProtectionFacts(
            book, cause.dollar_rule, cause.levers, tid, horizon_defaulted=DEFAULT_HORIZON_MARK in missing_info
        )
        data_used.append(facts.rule_statement())
        why += facts.why()
        change += facts.lever_statements(others=len(change))
        limits.append(
            Statement(
                text_fr="Les pertes de planification viennent de l'historique (pire baisse observée, plus une marge) : "
                "elles ne prédisent pas les pertes futures.",
                label="HYPOTHESE",
            )
        )
    if not cause.profile_protection and cause.dollar_rule is None:  # cause non inscrite (compilation externe)
        why.append(
            Statement(
                text_fr="Le mode protection s'applique : le profil présente des signaux de vulnérabilité ; par "
                "prudence, aucune allocation n'est calculée.",
                fact_ids=[level_fid],
            )
        )
        change.append(
            Statement(
                text_fr="Revoir votre situation avec une personne qualifiée avant toute proposition.", label="HYPOTHESE"
            )
        )
    if must:
        what = "une information indispensable" if len(must) == 1 else "des informations indispensables"
        why.append(Statement(text_fr=f"Il manque aussi {what} au calcul ({', '.join(must)}).", fact_ids=[level_fid]))
    return Explanation(data_used=data_used, why=why, limits=limits, what_would_change=change)


# fmt et son port web (app/web/src/lib/portfolio/format.ts) écrivent toujours une décimale en « mois » et en « ans ».
# Une durée entière prend donc une unité que les deux écrivent sans décimale (« 12 ») ; la phrase ajoute le mot.
WHOLE_UNITS = {"mois": "nombre de mois", "ans": "nombre d'années"}
WHOLE_UNIT_WORDS = {whole: word for word, whole in WHOLE_UNITS.items()}


def _duration(years: float) -> tuple[float | int, str]:
    """Horizon affiché : en mois sous deux ans, en années au-delà ; sans décimale s'il est entier (« 12 mois »,
    « 5 ans », mais « 5,1 ans »)."""
    value, unit = (round(years * 12, 4), "mois") if years < 2 else (years, "ans")
    if abs(value - round(value)) < 1e-9:
        return int(round(value)), WHOLE_UNITS[unit]
    return value, unit


def _under(shown: str, limit: str) -> str:
    """« sous », ou « juste sous » quand les deux valeurs s'écrivent pareil une fois arrondies (12,98 % et 12,99 %
    s'écrivent tous deux 13,0 %) : l'écart reste lisible sans écrire de chiffre non sourcé."""
    return "juste sous" if shown == limit else "sous"


def _covered(book: FactBook, text: str, fact_ids: list[str]) -> bool:
    """Vrai si chaque nombre du texte est la valeur d'un Fact cité : le libellé d'un objectif (« retraits prévus sous
    12 mois ») peut alors être cité tel quel sans enfreindre la règle des nombres."""
    values = {float(book.facts[fid].value) for fid in fact_ids if isinstance(book.facts[fid].value, int | float)}
    values |= {float(n) for n in allowed_numbers(book, fact_ids)}
    return all(float(n) in values for n in numbers(text))


@dataclass
class _ProtectionFacts:
    """Facts de la règle des dollars en PROTECTION (``dollar_rule.protection``, ses entrées et ses leviers vérifiés),
    rattachés à l'étape de compilation, et les phrases qui les citent."""

    book: FactBook
    rule: DollarRuleProtection
    levers: ProtectionLevers | None
    trace_id: str
    star: str = field(init=False)  # Fact de l*
    floor: str = field(init=False)  # Fact de min_L_plan
    goal_facts: dict[str, str] = field(default_factory=dict)  # objectif -> Fact de son horizon
    horizon_defaulted: bool = False  # horizon absent du profil : l'adaptateur retient son défaut prudent

    def __post_init__(self) -> None:
        self.star = self.add(
            "l_star",
            "Perte maximale admissible retenue (l*)",
            self.rule.l_star,
            "%",
            "l* = min(L_plan(e_max), l_declared, l_cap)",
        )
        self.floor = self.add(
            "min_L_plan",
            "Plus petite perte de planification des portefeuilles possibles (min L_plan)",
            self.rule.min_planning_loss,
            "%",
            "minimum sur la grille des parts d'actions de L_plan(e) = ENV(e, mdd) + daily_buffer",
        )

    def add(  # noqa: PLR0913 (libellé, valeur, unité et provenance d'un Fact)
        self, key: str, label: str, value, unit: str, processing: str, dataset: str | None = None, status: str = "FAIT"
    ) -> str:
        return self.book.add(
            f"protection.{key}",
            label,
            value,
            unit,
            dataset=dataset or self.rule.yaml_path,
            processing=processing,
            status=status,
            currency="CAD" if unit == "CAD" else None,
            trace_id=self.trace_id,
        )

    def loss(self, key: str, label: str, value: float, processing: str) -> str:
        """Fact d'une perte entrée de l* ; celui de l* quand elle en est la valeur (l* est alors cité)."""
        if abs(value - self.rule.l_star) <= SAME_VALUE:
            return self.star
        return self.add(key, label, value, "%", processing)

    def v(self, fid: str) -> str:
        fact = self.book.facts[fid]
        word = WHOLE_UNIT_WORDS.get(fact.unit)  # durée entière : « 12 » + « mois »
        return f"{fmt(fact.value, fact.unit)} {word}" if word else fmt(fact.value, fact.unit)

    def below(self, said: str, ids: list[str], compared: str) -> Statement:
        """« <said> est sous min_L_plan » ; ``compared`` est le Fact de la perte comparée."""
        under = _under(self.v(compared), self.v(self.floor))
        return Statement(
            text_fr=f"{said} est {under} {PLANNING_LOSS_FR} ({self.v(self.floor)}) : aucune allocation ne respecte "
            "cette limite.",
            fact_ids=[*ids, self.floor],
        )

    def rule_statement(self) -> Statement:
        return Statement(
            text_fr=f"Règle des dollars : la perte admissible retenue ({self.v(self.star)}) doit couvrir la perte de "
            "planification d'un portefeuille, soit sa pire baisse historique plus une marge quotidienne. La plus "
            f"petite, parmi les portefeuilles possibles, est de {self.v(self.floor)}.",
            fact_ids=[self.star, self.floor],
        )

    # ------------------------------------------------------------------ pourquoi : chaque entrée de l* trop basse
    def why(self) -> list[Statement]:
        rule = self.rule
        found = [
            part
            for part in (
                self._declared() if rule.is_below(rule.declared_loss) else None,
                self._horizon() if rule.is_below(rule.horizon_loss) else None,
                self._withdrawals() if rule.is_below(rule.withdrawal_loss) else None,
            )
            if part is not None
        ]
        return found or [self.below(f"La perte admissible retenue ({self.v(self.star)})", [self.star], self.star)]

    def _declared(self) -> Statement:
        rule = self.rule
        pct = self.loss(
            "l_declared",
            "Perte maximale déclarée, en part du montant (l_declared)",
            rule.declared_loss,
            "l_declared = min(max_acceptable_loss_pct, max_acceptable_loss_cad / W)",
        )
        if rule.declared_in_dollars:
            cad = self.add(
                "max_loss_cad",
                "Perte maximale déclarée",
                rule.declared_loss_cad,
                "CAD",
                "trace dollar_rule.l_declared",
                dataset="profil : max_acceptable_loss_cad",
            )
            said = f"La perte que vous dites pouvoir absorber ({self.v(cad)}, soit {self.v(pct)} du montant)"
            return self.below(said, [cad, pct], pct)
        return self.below(f"La perte que vous dites pouvoir absorber ({self.v(pct)} du montant)", [pct], pct)

    def _horizon(self) -> Statement:
        rule = self.rule
        loss = self.loss(
            "horizon_loss",
            "Perte que l'horizon permet d'absorber",
            rule.horizon_loss,
            "1 - (1 + mu_recovery)^-T, terme de l_cap",
        )
        goal = self.levers.horizon_goal if self.levers else None
        # Horizon absent du profil : T vient du défaut prudent de l'adaptateur (objectif principal), pas d'une réponse.
        defaulted = self.horizon_defaulted and (goal is None or goal.label.startswith(MAIN_GOAL_PREFIX))
        value, unit = _duration(rule.horizon_years)
        horizon = self.add(
            "horizon",
            "Horizon de placement retenu (T du seau risque)",
            value,
            unit,
            "défaut prudent de l'adaptateur, horizon absent du profil ; trace horizon.T_risk"
            if defaulted
            else "trace horizon.T_risk et dollar_rule.l_cap",
            status="HYPOTHESE" if defaulted else "FAIT",
        )
        if goal is not None:
            self.goal_facts[goal.goal_id] = horizon
        name = _goal_words(self.book, goal, [horizon]) if goal is not None else None
        if defaulted:
            who = " pour votre objectif principal" if goal is not None else ""
            text = f"Faute d'horizon connu, le calcul retient {self.v(horizon)}{who}, par prudence."
        elif name is not None:
            text = f"{name[0].upper()}{name[1:]} fixe l'horizon de placement à {self.v(horizon)}."
        else:
            text = f"L'horizon de placement retenu est de {self.v(horizon)}."
        return Statement(
            text_fr=f"{text} La perte que cet horizon permet d'absorber ({self.v(loss)}) est "
            f"{_under(self.v(loss), self.v(self.floor))} {PLANNING_LOSS_FR} "
            f"({self.v(self.floor)}) : aucune allocation ne respecte cette limite.",
            fact_ids=[horizon, loss, self.floor],
            label="HYPOTHESE" if defaulted else "FAIT",
        )

    def _withdrawals(self) -> Statement:
        rule = self.rule
        loss = self.loss(
            "withdrawal_loss",
            "Perte que les retraits prévus permettent d'absorber",
            rule.withdrawal_loss,
            "1 - q / q_max, terme de l_cap",
        )
        rate = self.add(
            "withdrawal_rate",
            "Retraits prévus par an, en part du montant (q)",
            rule.withdrawal_rate,
            "%",
            "trace dollar_rule.l_cap",
        )
        said = (
            f"La perte que vos retraits prévus permettent d'absorber ({self.v(loss)}, pour des retraits de "
            f"{self.v(rate)} du montant par an)"
        )
        return self.below(said, [loss, rate], loss)

    # ------------------------------------------------------------------ leviers vérifiés par compilation
    def lever_statements(self, others: int) -> list[Statement]:
        """Un énoncé par levier vérifié. Seul, il « rendrait une allocation possible » (la compilation du profil
        modifié donne un mandat) ; avec d'autres causes, chacun « serait nécessaire »."""
        levers = self.levers
        if levers is None:  # leviers non calculés (profil absent) : la règle, sans chiffre
            return [
                Statement(
                    text_fr="Une perte admissible plus élevée ou un horizon de placement plus long serait nécessaire "
                    "pour qu'une allocation soit possible.",
                    label="HYPOTHESE",
                )
            ]
        parts = [self._required_lever(change) for change in levers.required]
        alone = len(parts) + int(levers.horizon_short) + others == 1 and levers.allocation
        tail = " rendrait une allocation possible" if alone else NECESSARY_FR
        out = [Statement(text_fr=f"{subject}{tail}.", fact_ids=ids) for subject, ids in parts]
        if levers.horizon_short:
            out.append(self._horizon_lever(levers, tail))
        if levers.allocation and not alone and others == 0:
            out.append(
                Statement(
                    text_fr="Ensemble, ces changements rendraient une allocation possible : une nouvelle compilation "
                    "du profil modifié le vérifie.",
                )
            )
        return out

    def _required_lever(self, change: ProfileChange) -> tuple[str, list[str]]:
        verified = "seuil de la règle des dollars, vérifié par une nouvelle compilation du profil modifié"
        if change.kind == "max_loss_cad":
            fid = self.add("min_loss_cad", "Perte admissible minimale pour une allocation", change.value, "CAD",
                           f"min_L_plan × W, arrondi au dollar supérieur ; {verified}")
            return f"Une perte admissible d'au moins {self.v(fid)} sur ce montant", [fid]
        if change.kind == "max_loss_pct":
            fid = self.add("min_loss_pct", "Perte admissible minimale pour une allocation, en part du montant",
                           change.value, "%", f"min_L_plan arrondi au dixième de point supérieur ; {verified}")
            return f"Une perte admissible d'au moins {self.v(fid)} du montant", [fid]
        fid = self.add("allowed_withdrawal_rate", "Retraits maximaux par an pour une allocation", change.value, "%",
                       f"q_max × (1 - min_L_plan), arrondi au dixième de point inférieur ; {verified}")
        return f"Un taux de retrait d'au plus {self.v(fid)} du montant par an", [fid]

    def _horizon_lever(self, levers: ProtectionLevers, tail: str) -> Statement:
        if not levers.horizon:
            return Statement(
                text_fr=f"Un horizon de placement plus long{tail} ; aucun changement d'un seul objectif ne suffit ici.",
                label="HYPOTHESE",
            )
        texts, ids = [], []
        for option in levers.horizon:
            text, option_ids = self._horizon_option(option)
            texts.append(text)
            ids += option_ids
        return Statement(
            text_fr=f"Un horizon de placement plus long{tail}. Par exemple : " + " ; ou ".join(texts) + ".",
            fact_ids=list(dict.fromkeys(ids)),
        )

    def _horizon_option(self, option: ProfileChange) -> tuple[str, list[str]]:
        goal = option.goal
        name, ids = self._goal_name(goal)
        if option.kind == "without_goal":
            after = self._horizon_after(option)
            return f"sans {name}, l'horizon passerait à {self.v(after)}", [*ids, after]
        target = self.add(f"lever.{goal.goal_id}.horizon", f"Horizon testé pour {_goal_title(goal)}",
                          *_duration(option.value), "plus petit horizon testé qui lève la règle des dollars")
        text = f"un horizon d'au moins {self.v(target)} pour {name}"
        if _duration(option.horizon_after) != _duration(option.value):  # réserve de retraits : T ne vaut pas l'horizon
            after = self._horizon_after(option)
            text += f", l'horizon passerait à {self.v(after)}"
            ids.append(after)
        return text, [*ids, target]

    def _horizon_after(self, option: ProfileChange) -> str:
        return self.add(f"lever.{option.goal.goal_id}.horizon_after", "Horizon de placement après ce changement",
                        *_duration(option.horizon_after), "trace horizon.T_risk de la compilation du profil modifié")

    def _goal_name(self, goal: GoalRef) -> tuple[str, list[str]]:
        """Nom de l'objectif (``_goal_words``), ou « votre objectif à 5,0 ans » si son libellé a des nombres non
        sourcés."""
        fid = self.goal_facts.get(goal.goal_id)
        if fid is None:
            fid = self.add(f"goal.{goal.goal_id}.horizon", f"Horizon de {_goal_title(goal)}",
                           *_duration(goal.horizon_years), "trace horizon.T_risk")
            self.goal_facts[goal.goal_id] = fid
        return _goal_words(self.book, goal, [fid]) or f"votre objectif à {self.v(fid)}", [fid]


def _goal_title(goal: GoalRef) -> str:
    """Nom de l'objectif dans le libellé d'un Fact : « l'objectif principal » ou « l'objectif « libellé » »."""
    return "l'objectif principal" if goal.label.startswith(MAIN_GOAL_PREFIX) else f"l'objectif « {goal.label} »"


def _goal_words(book: FactBook, goal: GoalRef, fact_ids: list[str]) -> str | None:
    """Nom de l'objectif dans une phrase : « votre objectif principal » pour celui du questionnaire (son libellé porte
    le code brut de l'option), « votre objectif « libellé » » si chaque nombre du libellé est sourcé, sinon None."""
    if goal.label.startswith(MAIN_GOAL_PREFIX):
        return "votre objectif principal"
    if _covered(book, goal.label, fact_ids):
        return f"votre objectif « {goal.label} »"
    return None
