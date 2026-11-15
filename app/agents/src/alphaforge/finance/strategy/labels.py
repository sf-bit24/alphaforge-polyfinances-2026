"""Libellés français des codes de l'étape 0 : styles, secteurs, intérêts, exclusions, signaux de comportement.

Les codes (``offensive``, ``tech``, ``technology``, ``low_composure``…) restent les identifiants du moteur : ils
vivent dans les ``fact_id``, les ``rule_id``, la trace et le résumé ``strategy``. Ce qu'un investisseur lit
(``label_fr``, valeur texte d'un Fact, ``description_fr``) passe par ces tables ; un identifiant interne, s'il
doit rester visible, va dans la source ou le traitement du Fact (``processing``). Bibliothèque standard seulement.
"""

from __future__ import annotations

NBSP = "\u00a0"  # espace insécable avant « % » (typographie française)

# Accordé à « style » (masculin) : « style offensif ».
STYLE_FR = {"defensive": "défensif", "dynamique": "dynamique", "offensive": "offensif"}

# Tags d'exposition (strategy.yaml#sectors.tags, data/long/assets.csv) : « secteur de la technologie ».
SECTOR_OF = {
    "tech": "de la technologie",
    "tech_platform": "des plateformes technologiques",
    "energy": "de l'énergie",
    "financials": "de la finance",
    "utilities": "des services publics",
    "healthcare": "de la santé",
    "communication": "des communications",
    "consumer_discretionary": "de la consommation discrétionnaire",
    "consumer_staples": "de la consommation de base",
    "industrials": "de l'industrie",
    "materials": "des matériaux",
    "chemicals": "de la chimie",
    "retail": "du commerce de détail",
}

# risk_capacity.employment_sector (libellés du questionnaire, en minuscules).
EMPLOYMENT_FR = {
    "technology": "technologie",
    "finance": "finance",
    "energy": "énergie",
    "healthcare": "santé",
    "public": "secteur public",
    "industry": "industrie",
    "retail": "commerce",
}

# preferences.interests.
INTEREST_FR = {
    "technology": "technologie et intelligence artificielle",
    "crypto": "cryptoactifs",
    "dividends": "revenus de dividendes",
    "canadian_companies": "entreprises canadiennes",
    "healthcare": "santé",
    "clean_energy": "énergie propre",
    "gold": "or",
}

# preferences.exclusions.
EXCLUSION_FR = {
    "tobacco": "tabac",
    "weapons": "armement",
    "fossil_fuels": "combustibles fossiles",
    "gambling": "jeux de hasard",
    "alcohol": "alcool",
}

# style.BehaviorFlags.active().
FLAG_FR = {
    "overconfidence": "surconfiance",
    "fomo": "peur de manquer une occasion (FOMO)",
    "attention": "attrait des titres médiatisés",
    "low_composure": "faible sang-froid face aux baisses",
    "low_literacy": "faible littératie financière",
}

# Preuves des signaux (style.behavior_flags) : « champ=valeur » ou repère fixe → texte lisible.
_EVIDENCE_FIELD_FR = {
    "knowledge.self_assessment": "connaissances autoévaluées",
    "knowledge.level": "niveau de connaissances",
    "knowledge.news_frequency": "suivi de l'actualité financière",
    "behavior.hype_reaction": "réaction à un titre très médiatisé",
    "behavior.hype_position_share": "part d'un placement dans un titre médiatisé",
    "risk_tolerance.drop_reaction": "réaction à une forte baisse",
    "risk_tolerance.past_drop_behavior": "lors d'une baisse passée",
    "risk_tolerance.sell_threshold_pct": "baisse tolérée avant de vendre",
}
_EVIDENCE_VALUE_FR = {
    "beginner": "débutant",
    "intermediate": "intermédiaire",
    "advanced": "avancé",
    "daily": "tous les jours",
    "weekly": "chaque semaine",
    "buy_a_lot": "en acheter beaucoup",
    "buy_some": "en acheter un peu",
    "wait": "attendre",
    "no_change": "ne rien changer",
    "lt2": f"moins de 2{NBSP}%",
    "2to5": f"de 2{NBSP}% à moins de 5{NBSP}%",
    "5to10": f"de 5{NBSP}% à moins de 10{NBSP}%",
    "gt10": f"plus de 10{NBSP}%",
    "sell_all": "tout vendre",
    "sell_some": "vendre une partie",
    "sold": "a vendu",
    "none": "aucune baisse acceptée",
    "lt5": f"moins de 5{NBSP}%",
}
_EVIDENCE_FIXED_FR = {
    "knowledge.quiz_diversification": "réponse inexacte à la question sur la diversification",
    "knowledge.quiz_bond_rates": "réponse inexacte à la question sur les taux et les obligations",
    "knowledge.products_known sans « stocks »": "les actions ne figurent pas parmi les produits connus",
    "profile.biases[surconfiance]": "biais de surconfiance relevé au profil",
    "profile.biases[FOMO]": "biais FOMO relevé au profil",
    "profile.biases[aversion_perte]": "aversion aux pertes relevée au profil",
}
_CDAR_EVIDENCE = "risk.cdar_m"


def style_fr(style: str | None) -> str:
    return STYLE_FR.get(style or "", style or "aucun")


def sector_fr(tag: str) -> str:
    """« secteur de l'énergie » ; un tag sans libellé reste cité entre guillemets."""
    of = SECTOR_OF.get(tag)
    return f"secteur {of}" if of else f"thème « {tag} »"


def employment_fr(code: str) -> str:
    return EMPLOYMENT_FR.get(code, code)


def interest_fr(code: str) -> str:
    return INTEREST_FR.get(code, code)


def exclusion_fr(code: str) -> str:
    return EXCLUSION_FR.get(code, code)


def flag_fr(flag: str) -> str:
    return FLAG_FR.get(flag, flag)


def pct_fr(share: float, digits: int = 0) -> str:
    """Une fraction en pourcentage français, espace insécable : 0,93 → « 93 % »."""
    return f"{share * 100:.{digits}f}".replace(".", ",") + f"{NBSP}%"


def evidence_fr(item: str) -> str | None:
    """Texte lisible d'une preuve de signal ; None pour une réponse absente (``champ=None``)."""
    if item in _EVIDENCE_FIXED_FR:
        return _EVIDENCE_FIXED_FR[item]
    if item.startswith(_CDAR_EVIDENCE):
        return "limite de baisse conditionnelle du mandat (aversion aux pertes ou sang-froid faible)"
    field, sep, value = item.partition("=")
    if not sep or field not in _EVIDENCE_FIELD_FR:
        return item
    if value in ("", "None"):
        return None
    return f"{_EVIDENCE_FIELD_FR[field]} : {_EVIDENCE_VALUE_FR.get(value, value)}"


def evidence_text(items: list[str]) -> str:
    """Valeur d'un Fact ``strat.flag.*`` : les preuves lisibles, sans identifiant interne."""
    return " ; ".join(t for t in (evidence_fr(i) for i in items) if t)
