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

from alphaforge.finance.contracts.decision import Explanation, Statement

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
        text = f"Titre retenu {t} : rang {v(rank)} sur {v('strat.n_candidates')}, plancher de satellite {v(fid)}"
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
