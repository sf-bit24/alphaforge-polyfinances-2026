"""Repérage local d'un NAS (numéro d'assurance sociale) dans le texte de l'investisseur (#77).

Le garde-fou Bedrock bloque un NAS en entrée, mais pas toujours : sur Bedrock réel, « Mon NAS est 046454286 »
(9 chiffres collés, phrase française) passe (``apply-guardrail`` : action ``NONE``). Le filtre géré
``CA_SOCIAL_INSURANCE_NUMBER`` ne le reconnaît pas en français, et la regex ``nas-canadien`` exige des séparateurs.
``contains_sin`` refuse donc, avant l'appel au modèle :

1. un NAS écrit en trois groupes de trois chiffres séparés par une espace ou un tiret (``SIN_PATTERN``, même motif que
   la regex ``nas-canadien`` de ``infrastructure/infra/bedrock.tf``) ;
2. 9 chiffres collés qui suivent de près (20 caractères au plus, sans chiffre ni retour à la ligne) un mot-clé du NAS,
   en français ou en anglais, sans égard à la casse : NAS, N.A.S., (numéro d')assurance sociale, SIN, S.I.N.,
   social insurance (number) ;
3. 9 chiffres collés sans mot-clé, seulement s'ils passent la clé de Luhn (celle du NAS) et ne ressemblent pas à une
   donnée de portefeuille, que A2 doit pouvoir lire.

Pour la règle 3, un CUSIP numérique passe toujours Luhn : il double les mêmes chiffres. Luhn ne suffit donc pas, et le
contexte tranche. Le numéro n'est **pas** refusé :

- si le texte nomme un CUSIP, un ISIN ou un SEDOL, ou s'il contient plusieurs numéros de 9 chiffres différents (une
  liste d'identifiants : une personne n'a qu'un NAS) ;
- s'il touche un montant : symbole ou code de devise, ``%``, partie décimale ;
- si son voisin immédiat sur la ligne est un autre nombre, un symbole boursier ou une place (``AAPL``, ``RY.TO``,
  ``NASDAQ``) : ligne de positions ou de CSV ;
- si un mot de compte, de quantité ou de montant est à 40 caractères au plus, sur la même ligne (« compte »,
  « actions », « valeur », « account », « shares »…).

Ce choix accepte quelques NAS manqués (un NAS sans mot-clé collé à « actions ») plutôt que des portefeuilles refusés.
Le simulateur du mode ``mock`` applique la même règle (``app/web/src/lib/mock/agents.ts``). Les deux sont testés sur
le même tableau de cas : ``tests/fixtures/issue_77_sin_cases.json``.
"""

from __future__ import annotations

import re

# Lettres, pour borner un mot sans dépendre du \b de chaque moteur (le simulateur reprend ces motifs en JavaScript).
_LETTER = "A-Za-zÀ-ÿ"

SIN_PATTERN = re.compile(r"\b\d{3}[ -]\d{3}[ -]\d{3}\b", re.ASCII)
SIN_AFTER_KEYWORD = re.compile(
    rf"(?<![{_LETTER}])(?:n\.?a\.?s|s\.?i\.?n|assurance[-\s]+sociale|social[-\s]+insurance)\.?(?![{_LETTER}])"
    r"[^0-9\n]{0,20}(?<![0-9])[0-9]{9}(?![0-9])",
    re.IGNORECASE,
)
_BARE_NINE_DIGITS = re.compile(r"(?<![0-9A-Za-z])[0-9]{9}(?![0-9A-Za-z])")
_SECURITY_IDS = re.compile(rf"(?<![{_LETTER}])(?:cusip|isin|sedol)(?![{_LETTER}])", re.IGNORECASE)
_HOLDING_WORDS = re.compile(
    rf"(?<![{_LETTER}])(?:compte|account|acct|folio|quantit[ée]|qt[ée]|qty|quantity|actions?|parts?|unit[ée]s?|units?"
    rf"|titres?|shares?|montant|amount|valeur|value|prix|price|total|solde|balance|dollars?|r[ée]f[ée]rence"
    rf"|reference|ref)(?![{_LETTER}])",
    re.IGNORECASE,
)
_AMOUNT_BEFORE = re.compile(r"(?:[$€£]|\b(?:CAD|USD|EUR)|[0-9][.,])\s?$", re.IGNORECASE)
_AMOUNT_AFTER = re.compile(r"^(?:\s?(?:[$€£%]|(?:CAD|USD|EUR|dollars?)\b)|[.,][0-9])", re.IGNORECASE)
# Séparateurs d'une ligne de positions ou de CSV, entre le numéro et ses voisins.
_SEPARATORS = re.compile(r"[\s,;|:/()\[\]-]+")
# Voisin d'une donnée de portefeuille : un nombre, un symbole boursier ou une place (AAPL, RY.TO, NASDAQ).
_HOLDING_TOKEN = re.compile(r"[0-9]|^[A-Z]{1,6}(?:\.[A-Z]{1,3})?$")
_WORD_WINDOW = 40


def luhn_valid(digits: str) -> bool:
    """Clé de Luhn, celle du NAS : en partant de la droite, un chiffre sur deux est doublé."""
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char) * (2 if index % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def _neighbours(before: str, after: str) -> list[str]:
    """Le mot qui précède le numéro sur sa ligne et celui qui le suit, sans les séparateurs."""
    left = [token for token in _SEPARATORS.split(before) if token]
    right = [token for token in _SEPARATORS.split(after) if token]
    return [token.strip(".") for token in left[-1:] + right[:1]]


def _looks_like_holding(text: str, match: re.Match[str]) -> bool:
    """Le numéro touche un montant, un autre nombre, un symbole boursier ou un mot de compte, de quantité ou de
    montant de sa ligne : c'est une donnée de portefeuille, pas un NAS."""
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    before = text[line_start : match.start()]
    after = text[match.end() : line_end if line_end >= 0 else len(text)]
    if _AMOUNT_BEFORE.search(before) or _AMOUNT_AFTER.search(after):
        return True
    if any(_HOLDING_TOKEN.search(token) for token in _neighbours(before, after)):
        return True
    return bool(_HOLDING_WORDS.search(before[-_WORD_WINDOW:] + " " + after[:_WORD_WINDOW]))


def _bare_sin(text: str) -> bool:
    """Règle 3 : 9 chiffres collés, sans mot-clé, qui passent Luhn hors de tout contexte de portefeuille."""
    candidates = [match for match in _BARE_NINE_DIGITS.finditer(text) if luhn_valid(match.group())]
    if not candidates or _SECURITY_IDS.search(text) or len({match.group() for match in candidates}) > 1:
        return False
    return not _looks_like_holding(text, candidates[0])


def contains_sin(text: str) -> bool:
    """Vrai si le texte contient un NAS selon les trois règles du module."""
    return bool(SIN_PATTERN.search(text) or SIN_AFTER_KEYWORD.search(text) or _bare_sin(text))
