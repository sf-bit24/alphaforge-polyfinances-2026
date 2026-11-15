"""Signaux déterministes d'incompréhension, lus dans le journal du profil (aucun modèle).

Deux familles de signaux, chacune citée par sa preuve (texte exact ou réponse, avec provenance et date) :

- **messages** : un message libre de l'investisseur (``kind: "message"``) qui nomme un concept du catalogue
  avec une marque d'incompréhension (« c'est quoi un FNB ? », « je ne comprends pas le REER »);
- **réponses** : des combinaisons de réponses qui trahissent un concept mal compris (accepter de fortes
  variations mais tout vendre à la première baisse, horizon court et goût du risque élevé, comptes
  « je ne sais pas »…), et les drapeaux du portefeuille existant calculés par le code (A2).

A7 reçoit ces candidats et les pèse; sans modèle, les candidats d'au moins ``RULE_THRESHOLD`` suffisent.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .concepts import Catalog, normalize

RULE_THRESHOLD = 0.6
MAX_QUOTE = 180

CONFUSION_MARKERS = (
    # français (forme normalisée : minuscules, sans accents)
    "c'est quoi",
    "cest quoi",
    "c quoi",
    "qu'est-ce qu",
    "qu'est ce qu",
    "qu est ce qu",
    "que veut dire",
    "veut dire quoi",
    "ca veut dire",
    "ca signifie",
    "je comprends pas",
    "je ne comprends pas",
    "comprends pas",
    "j'ai pas compris",
    "je n'ai pas compris",
    "pas compris",
    "je sais pas",
    "je ne sais pas",
    "sais pas trop",
    "aucune idee",
    "je connais pas",
    "je ne connais pas",
    "jamais entendu",
    "comment ca marche",
    "comment ca fonctionne",
    "explique",
    "pas clair",
    "confus",
    "je suis perdu",
    "difference entre",
    # anglais
    "what is",
    "what's",
    "whats",
    "what are",
    "what does",
    "what do you mean",
    "don't understand",
    "dont understand",
    "do not understand",
    "not sure what",
    "no idea",
    "never heard",
    "confused",
    "explain",
    "how does",
    "difference between",
    "not clear",
    "i'm lost",
)
_MARKERS = [re.compile(r"(?<![a-z])" + re.escape(m) + r"(?![a-z])") for m in CONFUSION_MARKERS]


@dataclass
class Evidence:
    kind: str  # "message" ou "answer" ou "portfolio"
    ref: str  # identifiant stable de la preuve, cité par A7 (m1, r_unknown_account_types…)
    provenance: str
    at: str | None
    quote: str | None = None
    field: str | None = None
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        out = {"kind": self.kind, "ref": self.ref, "provenance": self.provenance, "at": self.at}
        for key in ("quote", "field", "value"):
            if getattr(self, key) is not None:
                out[key] = getattr(self, key)
        return out


@dataclass
class Candidate:
    concept_id: str
    score: float
    rule: str
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "score": round(self.score, 2),
            "rule": self.rule,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass
class InvestorMessage:
    ref: str
    text: str
    provenance: str
    at: str | None
    locale: str | None


def investor_messages(entries: Iterable[dict[str, Any]]) -> list[InvestorMessage]:
    messages = []
    for entry in entries:
        if entry.get("kind") != "message":
            continue
        text = entry.get("text") if isinstance(entry.get("text"), str) else entry.get("value")
        if not isinstance(text, str) or not text.strip():
            continue
        messages.append(
            InvestorMessage(
                ref=f"m{len(messages) + 1}",
                text=text.strip()[:2000],
                provenance=str(entry.get("provenance") or "a1"),
                at=entry.get("at"),
                locale=entry.get("locale"),
            )
        )
    return messages


def latest_answers(entries: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Dernière valeur de chaque champ du profil, avec sa provenance (le journal est en ajout seulement)."""
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if entry.get("kind") == "answer" and isinstance(entry.get("field"), str):
            if entry.get("value") is None:
                latest.pop(entry["field"], None)
            else:
                latest[entry["field"]] = entry
    return latest


def has_confusion(text: str) -> bool:
    normalized = normalize(text)
    return any(pattern.search(normalized) for pattern in _MARKERS)


def quote_around(text: str, alias: str) -> str:
    """Phrase du message qui contient l'alias, tronquée : la citation montrée à l'investisseur."""
    sentences = re.split(r"(?<=[.!?\n])\s+", text.strip())
    for sentence in sentences:
        if alias and alias in normalize(sentence):
            return sentence.strip()[:MAX_QUOTE]
    return text.strip()[:MAX_QUOTE]


def message_candidates(catalog: Catalog, messages: list[InvestorMessage]) -> list[Candidate]:
    candidates = []
    for message in messages:
        confused = has_confusion(message.text)
        asks = "?" in message.text
        for concept in catalog.concepts.values():
            mentions = concept.mentioned_in(message.text)
            if not mentions:
                continue
            score = 0.85 if confused else (0.6 if asks else 0.3)
            candidates.append(
                Candidate(
                    concept_id=concept.id,
                    score=score,
                    rule="message_confusion" if confused else ("message_question" if asks else "message_mention"),
                    evidence=[
                        Evidence(
                            "message",
                            message.ref,
                            message.provenance,
                            message.at,
                            quote=quote_around(message.text, mentions[0]),
                        )
                    ],
                )
            )
    return candidates


# --------------------------------------------------------------------------- règles sur les réponses
Rule = Callable[[dict[str, dict[str, Any]], dict[str, Any] | None, str | None], tuple[float, list[str]] | None]


def _value(answers: dict[str, dict[str, Any]], field_id: str) -> Any:
    entry = answers.get(field_id)
    return entry.get("value") if entry else None


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list | tuple) else ([] if value is None else [value])


def _r_products_without_etf(answers, portfolio, level):
    products = _as_list(_value(answers, "knowledge.products_known"))
    if not products or "etf" in products:
        return None
    holds_etf = any(str(p.get("asset_class", "")).startswith("etf") for p in (portfolio or {}).get("positions") or [])
    return (0.7 if holds_etf else 0.5), ["knowledge.products_known"]


def _r_attitude_vs_reaction(answers, portfolio, level):
    if (
        _value(answers, "risk_tolerance.risk_attitude") in ("moderate", "large")
        and _value(answers, "risk_tolerance.drop_reaction") == "sell_all"
    ):
        return 0.65, ["risk_tolerance.risk_attitude", "risk_tolerance.drop_reaction"]
    return None


def _r_reaction_sell_all(answers, portfolio, level):
    if _value(answers, "risk_tolerance.drop_reaction") == "sell_all":
        return 0.5, ["risk_tolerance.drop_reaction"]
    return None


def _r_short_horizon_high_risk(answers, portfolio, level):
    if _value(answers, "horizon.horizon_band") == "lt3" and _value(answers, "risk_tolerance.risk_attitude") == "large":
        return 0.65, ["horizon.horizon_band", "risk_tolerance.risk_attitude"]
    return None


def _r_loss_impact_vs_attitude(answers, portfolio, level):
    if _value(answers, "risk_capacity.loss_impact") == "major" and _value(answers, "risk_tolerance.risk_attitude") in (
        "moderate",
        "large",
    ):
        return 0.65, ["risk_capacity.loss_impact", "risk_tolerance.risk_attitude"]
    return None


def _r_low_emergency_fund(answers, portfolio, level):
    months = _value(answers, "risk_capacity.emergency_fund")
    if isinstance(months, int | float) and not isinstance(months, bool) and months < 3:
        return (0.65 if months == 0 else 0.55), ["risk_capacity.emergency_fund"]
    return None


def _r_high_interest_debt(answers, portfolio, level):
    if _value(answers, "risk_capacity.high_interest_debt") is True:
        return 0.5, ["risk_capacity.high_interest_debt"]
    return None


def _r_unknown_account_types(answers, portfolio, level):
    if "unknown" in _as_list(_value(answers, "constraints.account_types")):
        return 0.7, ["constraints.account_types"]
    return None


def _r_cad_only_with_usd(answers, portfolio, level):
    usd = ((portfolio or {}).get("exposures") or {}).get("by_currency", {}).get("USD", 0)
    if _value(answers, "constraints.currency_preference") == "cad_only" and float(usd or 0) > 0.2:
        return 0.6, ["constraints.currency_preference"]
    return None


def _flag_rule(flag_names: tuple[str, ...], score: float) -> Rule:
    def rule(answers, portfolio, level):
        flags = set(((portfolio or {}).get("exposures") or {}).get("flags") or [])
        flags |= set(_as_list(_value(answers, "context.portfolio_flags")))
        if flags & set(flag_names):
            return score, []
        return None

    return rule


def _r_crypto_interest_beginner(answers, portfolio, level):
    if "crypto" in _as_list(_value(answers, "preferences.interests")) and level == "beginner":
        return 0.55, ["preferences.interests"]
    return None


RULES: dict[str, Rule] = {
    "products_without_etf": _r_products_without_etf,
    "attitude_vs_reaction": _r_attitude_vs_reaction,
    "reaction_sell_all": _r_reaction_sell_all,
    "short_horizon_high_risk": _r_short_horizon_high_risk,
    "loss_impact_vs_attitude": _r_loss_impact_vs_attitude,
    "low_emergency_fund": _r_low_emergency_fund,
    "high_interest_debt": _r_high_interest_debt,
    "unknown_account_types": _r_unknown_account_types,
    "cad_only_with_usd": _r_cad_only_with_usd,
    "flag_concentration": _flag_rule(("concentration_single_position",), 0.6),
    "flag_home_bias": _flag_rule(("home_bias_canada",), 0.6),
    "flag_sector_concentration": _flag_rule(("concentration_sector", "sector_concentration"), 0.55),
    "flag_few_holdings": _flag_rule(("few_holdings",), 0.5),
    "flag_crypto_heavy": _flag_rule(("crypto_exposure_high",), 0.6),
    "crypto_interest_beginner": _r_crypto_interest_beginner,
}


def rule_candidates(
    catalog: Catalog,
    answers: dict[str, dict[str, Any]],
    portfolio: dict[str, Any] | None,
    level: str | None,
    *,
    portfolio_key: str | None = None,
) -> list[Candidate]:
    candidates = []
    for concept in catalog.concepts.values():
        for rule_name in concept.signals:
            rule = RULES.get(rule_name)
            if rule is None:
                continue
            outcome = rule(answers, portfolio, level)
            if outcome is None:
                continue
            score, fields = outcome
            evidence = [
                Evidence(
                    "answer",
                    f"r_{rule_name}_{i + 1}",
                    str(answers[f].get("provenance") or "base"),
                    answers[f].get("at"),
                    field=f,
                    value=answers[f].get("value"),
                )
                for i, f in enumerate(fields)
                if f in answers
            ]
            if not fields:
                evidence.append(
                    Evidence("portfolio", f"r_{rule_name}_1", "a2", None, field="exposures.flags", value=portfolio_key)
                )
            candidates.append(Candidate(concept.id, score, rule_name, evidence))
    return candidates


def merge(candidates: Iterable[Candidate]) -> dict[str, Candidate]:
    """Un candidat par concept : le meilleur score, toutes les preuves (sans doublon)."""
    merged: dict[str, Candidate] = {}
    for candidate in candidates:
        current = merged.get(candidate.concept_id)
        if current is None:
            merged[candidate.concept_id] = Candidate(
                candidate.concept_id, candidate.score, candidate.rule, list(candidate.evidence)
            )
            continue
        if candidate.score > current.score:
            current.score, current.rule = candidate.score, candidate.rule
        refs = {e.ref for e in current.evidence}
        current.evidence.extend(e for e in candidate.evidence if e.ref not in refs)
    return merged
