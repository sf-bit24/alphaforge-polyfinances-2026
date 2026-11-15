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
from alphaforge.finance.policy.compiler import DollarRuleProtection, NoMandateCause, ceil_step, floor_step

from .facts import FactBook, fmt

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


def verify(book: FactBook, st: Statement) -> list[str]:
    """Liste des problèmes (vide = phrase acceptée)."""
    problems = [f"fact_id inconnu : {fid}" for fid in st.fact_ids if fid not in book.facts]
    extra = numbers(st.text_fr) - allowed_numbers(book, st.fact_ids) - {"1", "2", "3", "4", "12", "95", "2022"}
    if extra:
        problems.append(f"nombres non sourcés : {sorted(extra)}")
    return problems


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
                    text_fr=f"La lentille « {a.lens} » a resserré le mandat : {a.amendment.reason_fr}.",
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


STYLE_FR = {"defensive": "défensif", "dynamique": "dynamique", "offensive": "offensif"}  # accordé à « style »


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
                text_fr=f"Plafond d'exposition {tag} (look-through) : {v(fid)}.", fact_ids=[fid], label="HYPOTHESE"
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
                text_fr=f"Signal de comportement « {fid[len('strat.flag.') :]} » : il règle des garde-fous, jamais "
                "l'allocation.",
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
                probs = verify(book, alt)
                if not probs:
                    kept.append(alt)
                    continue
                report.append(f"{sec}[{i}] gabarit conservé : {probs}")
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
        return _protection_explanation(book, cause, level_fid, data_used)
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
                text_fr=f"La confiance du profil ({fmt(cause.confidence, '%')}) est sous le minimum requis pour une "
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
    missing = list(missing_info) or must
    if missing or not change:  # sans cause connue, le statut INCOMPLETE vient du profil lui-même
        change.insert(
            0, Statement(text_fr="Compléter : " + ", ".join(missing or ["le profil"]) + ".", label="HYPOTHESE")
        )
    return why, change


def _protection_explanation(
    book: FactBook, cause: NoMandateCause, level_fid: str, data_used: list[Statement]
) -> Explanation:
    """Mode protection : le profil le signale (statut PROTECTION), ou la règle des dollars ne laisse aucune part
    d'actions dont la perte de planification tienne dans l*. Les deux causes peuvent s'additionner."""
    tid = book.facts[level_fid].trace_id
    why: list[Statement] = []
    change: list[Statement] = []
    levers: list[tuple[str, list[str]]] = []
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
        facts = _ProtectionFacts(book, cause.dollar_rule, tid)
        data_used.append(facts.rule_statement())
        rule_why, levers = facts.causes()
        why += rule_why
        limits.append(
            Statement(
                text_fr="Les pertes de planification viennent de l'historique (pire baisse observée, plus une marge) : "
                "elles ne prédisent pas les pertes futures.",
                label="HYPOTHESE",
            )
        )
    if not why:  # cause non inscrite dans la trace (compilation externe) : le mode protection, sans chiffre
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
    # Un seul levier suffit à rendre une allocation possible ; avec plusieurs causes, chacun est nécessaire.
    alone = len(levers) + len(change) == 1
    tail = " rendrait une allocation possible." if alone else " serait nécessaire pour qu'une allocation soit possible."
    change += [Statement(text_fr=subject + tail, fact_ids=ids) for subject, ids in levers]
    return Explanation(data_used=data_used, why=why, limits=limits, what_would_change=change)


@dataclass
class _ProtectionFacts:
    """Facts de la règle des dollars en PROTECTION (``dollar_rule.protection`` et ses entrées), rattachés à l'étape
    de compilation, et les phrases qui les citent."""

    book: FactBook
    rule: DollarRuleProtection
    trace_id: str
    star: str = field(init=False)  # Fact de l*
    floor: str = field(init=False)  # Fact de min_L_plan

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

    def add(self, key: str, label: str, value, unit: str, processing: str, dataset: str | None = None) -> str:
        return self.book.add(
            f"protection.{key}",
            label,
            value,
            unit,
            dataset=dataset or self.rule.yaml_path,
            processing=processing,
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
        return fmt(fact.value, fact.unit)

    def below(self, said: str, ids: list[str]) -> Statement:
        return Statement(
            text_fr=f"{said} est sous {PLANNING_LOSS_FR} ({self.v(self.floor)}) : aucune allocation ne respecte cette "
            "limite.",
            fact_ids=[*ids, self.floor],
        )

    def rule_statement(self) -> Statement:
        return Statement(
            text_fr=f"Règle des dollars : la perte admissible retenue ({self.v(self.star)}) doit couvrir la perte de "
            "planification d'un portefeuille, soit sa pire baisse historique plus une marge quotidienne. La plus "
            f"petite, parmi les portefeuilles possibles, est de {self.v(self.floor)}.",
            fact_ids=[self.star, self.floor],
        )

    def causes(self) -> tuple[list[Statement], list[tuple[str, list[str]]]]:
        """Phrases « pourquoi » et leviers (sujet, Facts) : chaque entrée de l* sous min_L_plan."""
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
        if not found:  # l* sous min_L_plan sans entrée identifiée : la règle elle-même
            need = self.add(
                "min_loss_pct",
                "Perte admissible minimale pour une allocation, en part du montant",
                ceil_step(rule.min_planning_loss, 0.001),
                "%",
                "min_L_plan arrondi au dixième de point supérieur",
            )
            found = [
                (
                    self.below(f"La perte admissible retenue ({self.v(self.star)})", [self.star]),
                    (f"Une perte admissible d'au moins {self.v(need)} du montant", [need]),
                )
            ]
        return [why for why, _ in found], [lever for _, lever in found]

    def _declared(self) -> tuple[Statement, tuple[str, list[str]]]:
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
            need = self.add(
                "min_loss_cad",
                "Perte admissible minimale pour une allocation",
                ceil_step(rule.min_planning_loss * rule.wealth, 1),
                "CAD",
                "min_L_plan × W, arrondi au dollar supérieur",
            )
            said = f"La perte que vous dites pouvoir absorber ({self.v(cad)}, soit {self.v(pct)} du montant)"
            lever = f"Une perte admissible d'au moins {self.v(need)} sur ce montant"
            return self.below(said, [cad, pct]), (lever, [need])
        need = self.add(
            "min_loss_pct",
            "Perte admissible minimale pour une allocation, en part du montant",
            ceil_step(rule.min_planning_loss, 0.001),
            "%",
            "min_L_plan arrondi au dixième de point supérieur",
        )
        said = f"La perte que vous dites pouvoir absorber ({self.v(pct)} du montant)"
        return self.below(said, [pct]), (f"Une perte admissible d'au moins {self.v(need)} du montant", [need])

    def _horizon(self) -> tuple[Statement, tuple[str, list[str]]]:
        rule = self.rule
        loss = self.loss(
            "horizon_loss",
            "Perte que l'horizon permet d'absorber",
            rule.horizon_loss,
            "1 - (1 + mu_recovery)^-T, terme de l_cap",
        )
        years = self.add(
            "horizon_years",
            "Horizon de l'objectif le plus proche (T)",
            rule.horizon_years,
            "ans",
            "trace dollar_rule.l_cap",
        )
        need = self.add(
            "required_horizon_years",
            "Horizon minimal pour une allocation",
            ceil_step(rule.required_horizon_years(), 0.1),
            "ans",
            "T tel que 1 - (1 + mu_recovery)^-T atteigne min_L_plan, arrondi au dixième supérieur",
        )
        said = (
            f"La perte que l'horizon de votre objectif le plus proche permet d'absorber ({self.v(loss)}, "
            f"à {self.v(years)})"
        )
        return self.below(said, [loss, years]), (
            f"Un horizon d'au moins {self.v(need)} pour l'objectif le plus proche",
            [need],
        )

    def _withdrawals(self) -> tuple[Statement, tuple[str, list[str]]]:
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
        need = self.add(
            "allowed_withdrawal_rate",
            "Retraits maximaux par an pour une allocation",
            floor_step(rule.allowed_withdrawal_rate(), 0.001),
            "%",
            "q_max × (1 - min_L_plan), arrondi au dixième de point inférieur",
        )
        said = (
            f"La perte que vos retraits prévus permettent d'absorber ({self.v(loss)}, pour des retraits de "
            f"{self.v(rate)} du montant par an)"
        )
        lever = f"Un taux de retrait d'au plus {self.v(need)} du montant par an"
        return self.below(said, [loss, rate]), (lever, [need])
