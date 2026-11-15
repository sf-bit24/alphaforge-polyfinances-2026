"""Moteur déterministe du questionnaire : chargement du YAML, conditions, rendu et validation des réponses.

Aucun modèle n'intervient ici. Le contenu (textes, options, poids, barèmes) vit dans ``questionnaire.yaml``;
ce module ne fait que l'appliquer, toujours de la même façon pour les mêmes réponses.

Types de champ et genre de question correspondant (CONTRACTS.md 3.3) :
``enum`` ↔ ``single_choice``, ``multi_enum`` ↔ ``multi_choice``, ``boolean``, ``number``, ``money``,
``percent``, ``scale`` et ``text`` portent le même nom des deux côtés.

Exception : un champ ``number``, ``money`` ou ``percent`` peut être demandé par une question ``single_choice``
à tranches. Chaque option porte un identifiant de tranche (``value``, une chaîne) et la valeur numérique écrite
dans le champ (``number``); le code convertit l'une en l'autre avant d'écrire le fait (``numeric_choices``).
Le fait garde aussi la tranche choisie (``band`` : identifiant, bornes et libellé dans les deux langues) : la
valeur écrite n'est que le chiffre prudent du calcul, et tout ce qui montre le fait cite la tranche
(``format_fact``).
"""

from __future__ import annotations

import math
import operator
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

import yaml

DIMENSIONS = (
    "knowledge",
    "objective",
    "horizon",
    "risk_tolerance",
    "risk_capacity",
    "constraints",
    "preferences",
    "behavior",  # réaction à un titre médiatisé (profil court, lu par l'étape 0); hors des cinq dimensions de la vue
    "context",
)
KINDS = ("single_choice", "multi_choice", "boolean", "number", "money", "percent", "scale", "text")
TYPE_TO_KIND = {
    "enum": "single_choice",
    "multi_enum": "multi_choice",
    "boolean": "boolean",
    "number": "number",
    "money": "money",
    "percent": "percent",
    "scale": "scale",
    "text": "text",
}
CHOICE_KINDS = ("single_choice", "multi_choice")
NUMERIC_KINDS = ("number", "money", "percent", "scale")
# Types de champ numériques demandés par des tranches (single_choice) plutôt qu'en saisie libre.
CHOICE_NUMBER_TYPES = ("number", "money", "percent")
DEFAULT_TEXT_MAX = 2000
# Valeurs retenues quand ``questionnaire.yaml`` ne les précise pas.
DEFAULT_THRESHOLD = 0.7
DEFAULT_CAP = 0.95
DEFAULT_MAX_GENERATED = 8
DEFAULT_MAX_OPEN_QUESTIONS = 2
OPTION_VALUE = re.compile(r"^[a-z0-9_]{1,40}$")
# Langues des libellés : une tranche gardée avec un fait porte son libellé dans chacune.
LOCALES = ("fr", "en")
_NUMERIC_COMPARISONS = (("gte", operator.ge), ("gt", operator.gt), ("lte", operator.le), ("lt", operator.lt))

YAML_PATH = Path(__file__).with_name("questionnaire.yaml")


class InvalidValueError(ValueError):
    """Valeur refusée; ``reason`` est un code stable, ``params`` précise l'écart."""

    def __init__(self, reason: str, **params: Any):
        super().__init__(reason)
        self.reason = reason
        self.params = params


REASON_TEXT = {
    "required": ("Une réponse est requise.", "An answer is required."),
    "not_a_string": ("La réponse doit être une chaîne.", "The answer must be a string."),
    "not_in_options": ("La réponse doit être une des options proposées.", "The answer must be one of the options."),
    "not_a_list": ("La réponse doit être une liste d'options.", "The answer must be a list of options."),
    "empty": ("Choisissez au moins une option.", "Choose at least one option."),
    "duplicate": ("Une option est répétée.", "An option is repeated."),
    "exclusive": ("Cette option ne se combine pas avec les autres.", "This option cannot be combined with others."),
    "not_boolean": ("La réponse doit être oui ou non (booléen).", "The answer must be yes or no (boolean)."),
    "not_a_number": ("La réponse doit être un nombre.", "The answer must be a number."),
    "not_integer": ("La réponse doit être un nombre entier.", "The answer must be a whole number."),
    "below_min": ("La réponse est sous le minimum permis.", "The answer is below the allowed minimum."),
    "above_max": ("La réponse dépasse le maximum permis.", "The answer is above the allowed maximum."),
    "too_long": ("La réponse est trop longue.", "The answer is too long."),
}


def reason_text(reason: str, locale: str) -> str:
    fr, en = REASON_TEXT.get(reason, ("Réponse invalide.", "Invalid answer."))
    return en if locale == "en" else fr


def localized(text: Any, locale: str) -> str | None:
    if text is None:
        return None
    if isinstance(text, dict):
        return text.get(locale) or text.get("fr") or text.get("en")
    return str(text)


@dataclass(frozen=True)
class FieldSpec:
    id: str
    type: str
    weight: float
    label: dict[str, str]
    values: tuple[dict[str, Any], ...] = ()
    min: float | None = None
    max: float | None = None
    unit: dict[str, str] | None = None
    max_length: int | None = None
    exclusive: tuple[str, ...] = ()
    when: dict[str, Any] | None = None
    writable_by: tuple[str, ...] = ()
    computed: bool = False
    summary: bool = False
    fallback: dict[str, Any] | None = None
    choices: dict[str, Any] | None = None

    @property
    def dimension(self) -> str:
        return self.id.split(".", 1)[0]

    @property
    def name(self) -> str:
        return self.id.split(".", 1)[1]

    @property
    def kind(self) -> str:
        return TYPE_TO_KIND[self.type]

    @property
    def value_ids(self) -> tuple[str, ...]:
        return tuple(item["value"] for item in self.values)

    def value_label(self, value: Any, locale: str) -> str:
        for item in self.values:
            if item["value"] == value:
                return localized(item["label"], locale) or str(value)
        return str(value)

    def label_text(self, locale: str) -> str:
        return localized(self.label, locale) or self.id

    @property
    def bounds(self) -> tuple[float | None, float | None]:
        low = self.min if self.min is not None else default_min(self.kind)
        high = self.max if self.max is not None else default_max(self.kind)
        return low, high


@dataclass(frozen=True)
class QuestionSpec:
    id: str
    field: FieldSpec
    kind: str
    prompt: dict[str, str]
    help: dict[str, str] | None = None
    options: tuple[dict[str, Any], ...] = ()
    when: dict[str, Any] | None = None
    required: bool = True

    @property
    def option_ids(self) -> tuple[str, ...]:
        return tuple(item["value"] for item in self.options)

    @property
    def numeric_choice(self) -> bool:
        """Question à tranches sur un champ numérique : la réponse est un identifiant, le fait un nombre."""
        return self.kind == "single_choice" and self.field.type in CHOICE_NUMBER_TYPES

    def option_number(self, option: str) -> float | int:
        for item in self.options:
            if item["value"] == option:
                return item["number"]
        raise KeyError(option)

    def option_band(self, option: str) -> dict[str, Any]:
        """Tranche d'une option, gardée avec le fait : identifiant, bornes (nulles quand l'option n'en a pas,
        comme « Je ne sais pas ») et libellé dans les deux langues."""
        for item in self.options:
            if item["value"] == option:
                return {
                    "option": option,
                    "min": _plain_number(item.get("min")),
                    "max": _plain_number(item.get("max")),
                    "label": {locale: localized(item["label"], locale) or option for locale in LOCALES},
                }
        raise KeyError(option)


def _field_spec(item: dict[str, Any]) -> FieldSpec:
    return FieldSpec(
        id=item["id"],
        type=item["type"],
        weight=float(item.get("weight", 0)),
        label=item["label"],
        values=tuple(item.get("values") or ()),
        min=item.get("min"),
        max=item.get("max"),
        unit=item.get("unit"),
        max_length=item.get("max_length"),
        exclusive=tuple(item.get("exclusive") or ()),
        when=item.get("when"),
        writable_by=tuple(item.get("writable_by") or ()),
        computed=bool(item.get("computed", False)),
        summary=bool(item.get("summary", False)),
        fallback=item.get("fallback"),
        choices=item.get("choices"),
    )


def _load_fields(items: list[dict[str, Any]]) -> dict[str, FieldSpec]:
    fields: dict[str, FieldSpec] = {}
    for item in items:
        spec = _field_spec(item)
        if spec.dimension not in DIMENSIONS:
            raise ValueError(f"field {spec.id}: unknown dimension")
        if spec.type not in TYPE_TO_KIND:
            raise ValueError(f"field {spec.id}: unknown type {spec.type}")
        if spec.id in fields:
            raise ValueError(f"duplicate field {spec.id}")
        if spec.choices is not None:
            _check_field_choices(spec)
        fields[spec.id] = spec
    return fields


def _check_question_options(question_id: str, kind: str, spec: FieldSpec, options: tuple[dict[str, Any], ...]) -> None:
    """Le genre de la question convient au type du champ, et ses options aux valeurs du champ."""
    if kind == "single_choice" and spec.type in CHOICE_NUMBER_TYPES:
        _check_number_options(question_id, spec, options)
    elif kind != spec.kind:
        raise ValueError(f"question {question_id}: kind {kind} does not match field type {spec.type}")
    elif kind in CHOICE_KINDS and {option["value"] for option in options} != set(spec.value_ids):
        raise ValueError(f"question {question_id}: options must match the field values")


def _load_questions(items: list[dict[str, Any]], fields: dict[str, FieldSpec]) -> list[QuestionSpec]:
    questions: list[QuestionSpec] = []
    seen: set[str] = set()
    for item in items:
        spec = fields[item["field"]]
        kind = item["kind"]
        options = tuple(item.get("options") or spec.values)
        _check_question_options(item["id"], kind, spec, options)
        if item["id"] in seen:
            raise ValueError(f"duplicate question {item['id']}")
        seen.add(item["id"])
        questions.append(
            QuestionSpec(
                id=item["id"],
                field=spec,
                kind=kind,
                prompt=item["prompt"],
                help=item.get("help"),
                options=options if kind in CHOICE_KINDS else (),
                when=item.get("when"),
                required=bool(item.get("required", True)),
            )
        )
    return questions


def _check_open_fields(followups: dict[str, Any], fields: dict[str, FieldSpec]) -> None:
    for field_id in followups.get("open_fields") or ():
        if field_id not in fields or fields[field_id].type != "text":
            raise ValueError(f"followups.open_fields: {field_id} is not a text field")


@dataclass
class Questionnaire:
    version: str
    threshold: float
    cap: float
    fields: dict[str, FieldSpec]
    questions: list[QuestionSpec]
    rules: dict[str, Any]
    followups: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def max_generated(self) -> int:
        return int(self.followups.get("max_generated", DEFAULT_MAX_GENERATED))

    @property
    def max_open_questions(self) -> int:
        return int(self.followups.get("max_open_questions", DEFAULT_MAX_OPEN_QUESTIONS))

    @property
    def open_fields(self) -> tuple[str, ...]:
        return tuple(self.followups.get("open_fields") or ())

    # ------------------------------------------------------------------ chargement
    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Questionnaire:
        fields = _load_fields(raw["fields"])
        questions = _load_questions(raw["questions"], fields)
        completeness = raw.get("completeness") or {}
        followups = raw.get("followups") or {}
        _check_open_fields(followups, fields)
        return cls(
            version=str(raw["version"]),
            threshold=float(completeness.get("threshold", DEFAULT_THRESHOLD)),
            cap=float(completeness.get("cap", DEFAULT_CAP)),
            fields=fields,
            questions=questions,
            rules=raw.get("rules") or {},
            followups=followups,
            raw=raw,
        )

    @classmethod
    def load(cls, path: Path | None = None) -> Questionnaire:
        return cls.from_dict(yaml.safe_load((path or YAML_PATH).read_text(encoding="utf-8")))

    # ------------------------------------------------------------------ recherche
    def question(self, question_id: str) -> QuestionSpec | None:
        for question in self.questions:
            if question.id == question_id:
                return question
        return None

    def question_for_field(self, field_id: str) -> QuestionSpec | None:
        for question in self.questions:
            if question.field.id == field_id:
                return question
        return None

    def applicable(self, condition: dict[str, Any] | None, values: dict[str, Any]) -> bool:
        return evaluate(condition, values)

    def is_question_applicable(self, question: QuestionSpec, values: dict[str, Any]) -> bool:
        return evaluate(question.when, values) and evaluate(question.field.when, values)

    def next_question(self, values: dict[str, Any], answered: set[str] | dict[str, Any]) -> QuestionSpec | None:
        """Première question applicable sans réponse, dans l'ordre du fichier."""
        for question in self.questions:
            if question.id in answered:
                continue
            if self.is_question_applicable(question, values):
                return question
        return None

    def applicable_questions(self, values: dict[str, Any]) -> list[QuestionSpec]:
        return [question for question in self.questions if self.is_question_applicable(question, values)]

    # ------------------------------------------------------------------ rendu
    def render(self, question: QuestionSpec, locale: str) -> dict[str, Any]:
        return render_question(
            question_id=question.id,
            source="deterministic",
            field=question.field,
            kind=question.kind,
            prompt=localized(question.prompt, locale) or "",
            help_text=localized(question.help, locale),
            options=[
                {"value": option["value"], "label": localized(option["label"], locale)} for option in question.options
            ],
            required=question.required,
            locale=locale,
        )

    # ------------------------------------------------------------------ validation
    def validate_answer(self, question: QuestionSpec, value: Any) -> Any:
        spec = question.field
        return validate_value(
            question.kind,
            value,
            options=question.option_ids,
            minimum=spec.min if spec.min is not None else default_min(question.kind),
            maximum=spec.max if spec.max is not None else default_max(question.kind),
            exclusive=spec.exclusive,
            max_length=spec.max_length or DEFAULT_TEXT_MAX,
            required=question.required,
        )

    def validate_field_value(self, field_id: str, value: Any) -> Any:
        spec = self.fields[field_id]
        return validate_value(
            spec.kind,
            value,
            options=spec.value_ids,
            minimum=spec.min if spec.min is not None else default_min(spec.kind),
            maximum=spec.max if spec.max is not None else default_max(spec.kind),
            exclusive=spec.exclusive,
            max_length=spec.max_length or DEFAULT_TEXT_MAX,
            required=True,
        )

    def format_value(self, field_id: str, value: Any, locale: str) -> str:
        spec = self.fields[field_id]
        return format_field_value(spec, value, locale)


# ---------------------------------------------------------------------- tranches des champs numériques
def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _within(spec: FieldSpec, number: float) -> bool:
    low, high = spec.bounds
    return (low is None or number >= low) and (high is None or number <= high)


def _check_options_ids(where: str, options: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for option in options:
        value = option.get("value")
        if not isinstance(value, str) or not OPTION_VALUE.match(value) or value in seen:
            raise ValueError(f"{where}: option values must be unique identifiers matching {OPTION_VALUE.pattern}")
        seen.add(value)


def _check_number_options(question_id: str, spec: FieldSpec, options: tuple[dict[str, Any], ...]) -> None:
    """Question à tranches sur un champ numérique : chaque option porte ``number``, dans les bornes du champ."""
    where = f"question {question_id}"
    if len(options) < 2:
        raise ValueError(f"{where}: a choice question on {spec.id} needs at least two options")
    _check_options_ids(where, options)
    for option in options:
        number = option.get("number")
        if not _is_number(number):
            raise ValueError(f"{where}: option {option['value']} needs a numeric number for field {spec.id}")
        if not _within(spec, number):
            raise ValueError(f"{where}: option {option['value']} number {number} is outside the bounds of {spec.id}")


def _check_field_choices(spec: FieldSpec) -> None:
    config = spec.choices or {}
    where = f"field {spec.id} choices"
    if spec.type not in CHOICE_NUMBER_TYPES:
        raise ValueError(f"{where}: only number, money and percent fields take computed choices")
    tranches = config.get("tranches") or []
    _check_options_ids(where, tranches)
    for item in tranches:
        low, high = item.get("min"), item.get("max")
        if not _is_number(low) or not _within(spec, low) or (high is not None and (not _is_number(high) or high < low)):
            raise ValueError(f"{where}: tranche {item['value']} needs min <= max within the field bounds")
    if config.get("relative_to"):
        shares = config.get("shares") or []
        if not shares or any(not _is_number(share) or share <= 0 for share in shares) or sorted(shares) != list(shares):
            raise ValueError(f"{where}: shares must be increasing positive numbers")


def _tranche(item: dict[str, Any], locale: str) -> dict[str, Any]:
    number = item.get("number", item.get("min"))
    return {
        "value": item["value"],
        "label": localized(item["label"], locale) or item["value"],
        "number": _plain_number(number),
        "min": _plain_number(item.get("min")),
        "max": _plain_number(item.get("max")),
    }


def _share_text(share: float, locale: str) -> str:
    text = f"{round(share * 100, 4):g}"
    return text if locale == "en" else text.replace(".", ",")


def _share_id(share: float) -> str:
    return f"{round(share * 100, 4):g}".replace(".", "_")


class _Cut(NamedTuple):
    """Borne entre deux tranches relatives : part du montant de référence, et montant en dollars."""

    share: float
    amount: int


def _relative_cuts(spec: FieldSpec, config: dict[str, Any], values: dict[str, Any]) -> list[_Cut] | None:
    base = values.get(config["relative_to"])
    if not _is_number(base) or base <= 0:
        return None
    shares = [float(share) for share in config["shares"]]
    amounts = [int(round(share * base)) for share in shares]
    if amounts[0] <= 0 or any(upper <= lower for lower, upper in zip(amounts, amounts[1:], strict=False)):
        return None
    if not _within(spec, amounts[-1]):
        return None
    return [_Cut(share, amount) for share, amount in zip(shares, amounts, strict=True)]


def _of_base(base: str | None, locale: str) -> str:
    """Complément d'une part : « de 10 000 $ » quand le montant de référence est le chiffre prudent d'une tranche
    (il n'est pas le montant de l'investisseur), rien sinon."""
    if base is None:
        return ""
    return f" of {base}" if locale == "en" else f" de {base}"


def _tranche_below(cut: _Cut, locale: str, base: str | None = None) -> dict[str, Any]:
    amount, percent = format_money(cut.amount, locale), _share_text(cut.share, locale)
    of = _of_base(base, locale) or (" of the amount" if locale == "en" else " du montant")
    label = f"Less than {amount} ({percent}%{of})" if locale == "en" else f"Moins de {amount} ({percent} %{of})"
    return {"value": f"lt{_share_id(cut.share)}pct", "label": label, "number": 0, "min": 0, "max": cut.amount}


def _tranche_between(lower: _Cut, upper: _Cut, locale: str, base: str | None = None) -> dict[str, Any]:
    low, high = format_money(lower.amount, locale), format_money(upper.amount, locale)
    low_percent, high_percent = _share_text(lower.share, locale), _share_text(upper.share, locale)
    of = _of_base(base, locale)
    label = (
        f"{low} to less than {high} ({low_percent} to {high_percent}%{of})"
        if locale == "en"
        else f"De {low} à moins de {high} ({low_percent} à {high_percent} %{of})"
    )
    return {
        "value": f"{_share_id(lower.share)}to{_share_id(upper.share)}pct",
        "label": label,
        "number": lower.amount,
        "min": lower.amount,
        "max": upper.amount,
    }


def _tranche_from(cut: _Cut, locale: str, base: str | None = None) -> dict[str, Any]:
    amount, percent = format_money(cut.amount, locale), _share_text(cut.share, locale)
    of = _of_base(base, locale)
    if locale == "en":
        label = f"{amount} or more ({percent}% or more{of})"
    else:
        label = f"{amount} ou plus ({percent} % ou plus{of})"
    return {
        "value": f"{_share_id(cut.share)}pct_plus",
        "label": label,
        "number": cut.amount,
        "min": cut.amount,
        "max": None,
    }


def _relative_tranches(
    spec: FieldSpec, config: dict[str, Any], values: dict[str, Any], locale: str, bands: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """Tranches en dollars, parts du montant de référence; ``None`` si ce montant est inconnu ou trop petit.

    Quand ce montant a été répondu par une tranche (``bands``), il n'est que le chiffre prudent du calcul : les
    libellés disent « 2,5 % de 10 000 $ », pas « 2,5 % du montant », qui serait faux pour 45 000 $.
    """
    cuts = _relative_cuts(spec, config, values)
    if cuts is None:
        return None
    reference = config["relative_to"]
    base = format_money(values[reference], locale) if band_is_range(bands.get(reference)) else None
    return [
        _tranche_below(cuts[0], locale, base),
        *(_tranche_between(lower, upper, locale, base) for lower, upper in zip(cuts, cuts[1:], strict=False)),
        _tranche_from(cuts[-1], locale, base),
    ]


def _within_band(
    tranches: list[dict[str, Any]], within: dict[str, Any], values: dict[str, Any]
) -> list[dict[str, Any]]:
    """Tranches comprises dans la bande ``within`` déjà connue; toutes quand elle ne l'est pas."""
    band = values.get(within["field"])
    limits = (within.get("ranges") or {}).get(band) if band is not None else None
    if not limits:
        return tranches
    low, high = limits
    return [
        tranche
        for tranche in tranches
        if tranche["min"] >= low and (high is None or (tranche["max"] is not None and tranche["max"] <= high))
    ]


def numeric_choices(
    questionnaire: Questionnaire,
    field_id: str,
    values: dict[str, Any],
    locale: str,
    *,
    bands: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Tranches d'un champ ``number``, ``money`` ou ``percent`` : ``value`` (identifiant), ``label``, ``number``
    (la valeur écrite dans le champ, la plus prudente de la tranche), ``min`` et ``max`` (bornes, ``max`` nul
    sans borne haute). Fonction pure : mêmes tranches pour les mêmes valeurs confirmées.

    Sources, dans l'ordre : ``choices`` du champ dans le YAML (parts d'un montant de référence, sinon tranches
    absolues, filtrées par la bande ``within`` déjà connue), puis les options de la question de base du champ.
    Liste vide pour un champ qui n'est pas numérique ou qui n'a aucune tranche. ``bands`` : tranches des faits
    confirmés, par champ (``ClientSession.bands``); elles ne changent que les libellés, jamais les nombres.
    """
    spec = questionnaire.fields.get(field_id)
    if spec is None or spec.type not in CHOICE_NUMBER_TYPES:
        return []
    config = spec.choices
    if config:
        tranches = _relative_tranches(spec, config, values, locale, bands or {}) if config.get("relative_to") else None
        if tranches is None:
            tranches = [_tranche(item, locale) for item in config.get("tranches") or []]
        within = config.get("within")
        return _within_band(tranches, within, values) if within else tranches
    question = questionnaire.question_for_field(field_id)
    if question is not None and question.numeric_choice:
        return [_tranche(item, locale) for item in question.options]
    return []


def tranche_bands(
    questionnaire: Questionnaire,
    field_id: str,
    values: dict[str, Any],
    *,
    bands: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Tranche de chaque option de ``numeric_choices``, à garder avec le fait si elle est choisie : identifiant,
    bornes et libellé dans les deux langues (le libellé d'une part dépend du montant connu à ce moment)."""
    by_locale = {locale: numeric_choices(questionnaire, field_id, values, locale, bands=bands) for locale in LOCALES}
    labels = {locale: {tranche["value"]: tranche["label"] for tranche in by_locale[locale]} for locale in LOCALES}
    return {
        tranche["value"]: {
            "option": tranche["value"],
            "min": tranche["min"],
            "max": tranche["max"],
            "label": {locale: labels[locale].get(tranche["value"], tranche["value"]) for locale in LOCALES},
        }
        for tranche in by_locale[LOCALES[0]]
    }


# ---------------------------------------------------------------------- tranche d'un fait
def band_is_range(band: Any) -> bool:
    """Vrai pour une tranche qui ne donne pas un nombre exact : deux bornes différentes, une seule borne ou
    aucune (« Je ne sais pas »). « Aucun fonds d'urgence » (0 à 0) est exact."""
    if not isinstance(band, dict):
        return False
    low, high = band.get("min"), band.get("max")
    return low is None or low != high


def fact_band(fact: dict[str, Any] | None) -> dict[str, Any] | None:
    """Tranche gardée avec un fait, si elle s'accorde avec sa valeur (un fait réécrit sans tranche la perd)."""
    fact = fact or {}
    band = fact.get("band")
    if not isinstance(band, dict) or not isinstance(band.get("label"), dict):
        return None
    value, low, high = fact.get("value"), band.get("min"), band.get("max")
    if not _is_number(value) or (low is not None and value < low) or (high is not None and value > high):
        return None
    return band


def band_brief(band: dict[str, Any], locale: str) -> dict[str, Any]:
    """Ce qu'un agent lit de la tranche d'un fait : identifiant, libellé dans la langue de la session, bornes."""
    return {
        "option": band.get("option"),
        "label": localized(band.get("label"), locale),
        "min": band.get("min"),
        "max": band.get("max"),
    }


def _lower_first(text: str) -> str:
    """« Moins de 1 mois » → « moins de 1 mois », pour suivre un libellé; « I don't know » et un sigle gardent
    leur majuscule."""
    word = text.split(" ", 1)[0]
    if len(word) > 1 and word[1:].islower():
        return text[:1].lower() + text[1:]
    return text


def _retained_note(spec: FieldSpec, band: dict[str, Any], value: float, locale: str) -> str | None:
    """Le nombre que le code retient, quand la tranche ne le dit pas déjà : rien pour 0 (« moins de 1 mois »
    n'est pas « 0 mois »), pour « 12 mois ou plus » ni pour une option sans bornes, qui le nomme dans son libellé."""
    low, high = band.get("min"), band.get("max")
    if (low is None and high is None) or value == 0 or (high is None and value == low):
        return None
    shown = format_field_value(spec, value, locale)
    cautious = value in (low, high)
    if locale == "en":
        return f"{shown} used as a cautious figure" if cautious else f"{shown} used for the calculations"
    retained = "retenus" if abs(value) >= 2 else "retenu"
    return f"{shown} {retained} par prudence" if cautious else f"{shown} {retained} pour les calculs"


def format_fact(spec: FieldSpec, fact: dict[str, Any] | None, locale: str) -> str:
    """Valeur d'un fait telle que le profil la montre. Un fait répondu par une tranche montre la tranche choisie
    (« moins de 1 mois », « de 10 000 $ à moins de 50 000 $ (10 000 $ retenus par prudence) »), jamais la
    borne seule comme si l'investisseur l'avait donnée."""
    value = (fact or {}).get("value")
    band = fact_band(fact)
    label = localized(band["label"], locale) if band else None
    if not label:
        return format_field_value(spec, value, locale)
    text = _lower_first(label)
    note = _retained_note(spec, band, value, locale)
    if not note:
        return text
    return f"{text[:-1]}; {note})" if text.endswith(")") else f"{text} ({note})"


# ---------------------------------------------------------------------- fonctions partagées
def default_min(kind: str) -> float | None:
    return {"money": 0, "percent": 0, "scale": 1}.get(kind)


def default_max(kind: str) -> float | None:
    return {"percent": 100, "scale": 5}.get(kind)


def unit_for(kind: str, spec: FieldSpec | None, locale: str) -> str | None:
    if kind == "money":
        return "CAD"
    if kind == "percent":
        return "%"
    if kind == "number" and spec is not None and spec.unit:
        return localized(spec.unit, locale)
    return None


def render_question(  # noqa: PLR0913 - un argument par champ de la question; a1.py l'appelle par mots-clés
    *,
    question_id: str,
    source: str,
    field: FieldSpec | None,
    kind: str,
    prompt: str,
    help_text: str | None,
    options: list[dict[str, Any]],
    required: bool,
    locale: str,
    dimension: str | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    if kind in NUMERIC_KINDS:
        low = minimum if minimum is not None else (field.min if field and field.min is not None else default_min(kind))
        high = maximum if maximum is not None else (field.max if field and field.max is not None else default_max(kind))
    else:
        low = high = None
    return {
        "id": question_id,
        "source": source,
        "dimension": dimension or (field.dimension if field else "context"),
        "kind": kind,
        "prompt": prompt,
        "help": help_text,
        "options": options if kind in CHOICE_KINDS else [],
        "min": _plain_number(low),
        "max": _plain_number(high),
        "unit": unit if unit is not None else unit_for(kind, field, locale),
        "required": required,
        "field": field.id if field else None,
    }


def _plain_number(value: float | None) -> float | int | None:
    if value is None:
        return None
    if float(value).is_integer():
        return int(value)
    return float(value)


def _parse_number_text(value: str) -> float:
    """Nombre saisi en texte (« 1 000,50 $ », « 12,5 % ») : espaces, ``$`` et ``%`` ignorés."""
    # Espaces insécables U+00A0 et U+202F de la typographie française, puis espaces ordinaires.
    text = value.strip().replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    text = text.replace("$", "").replace("%", "")
    # Une seule virgule sans point est une virgule décimale; sinon les virgules séparent les milliers.
    text = text.replace(",", ".") if text.count(",") == 1 and "." not in text else text.replace(",", "")
    try:
        return float(text)
    except ValueError as exc:
        raise InvalidValueError("not_a_number") from exc


def _to_number(value: Any) -> float:
    if isinstance(value, bool):
        raise InvalidValueError("not_a_number")
    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str):
        number = _parse_number_text(value)
    else:
        raise InvalidValueError("not_a_number")
    if not math.isfinite(number):
        raise InvalidValueError("not_a_number")
    return number


def _validate_single_choice(value: Any, options: tuple[str, ...] | list[str]) -> str:
    if not isinstance(value, str):
        raise InvalidValueError("not_a_string")
    if value not in options:
        raise InvalidValueError("not_in_options", allowed=list(options))
    return value


def _validate_multi_choice(
    value: Any, options: tuple[str, ...] | list[str], exclusive: tuple[str, ...] | list[str], *, required: bool
) -> list[str]:
    """Options choisies, remises dans l'ordre des options de la question."""
    chosen = [value] if isinstance(value, str) else value
    if not isinstance(chosen, list) or not all(isinstance(option, str) for option in chosen):
        raise InvalidValueError("not_a_list")
    if not chosen:
        if required:
            raise InvalidValueError("empty")
        return []
    if len(set(chosen)) != len(chosen):
        raise InvalidValueError("duplicate")
    unknown = [option for option in chosen if option not in options]
    if unknown:
        raise InvalidValueError("not_in_options", allowed=list(options), unknown=unknown)
    if len(chosen) > 1 and any(option in exclusive for option in chosen):
        raise InvalidValueError("exclusive", exclusive=list(exclusive))
    rank = {option: index for index, option in enumerate(options)}
    return sorted(chosen, key=lambda option: rank[option])


def _validate_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise InvalidValueError("not_boolean")


def _validate_number(kind: str, value: Any, minimum: float | None, maximum: float | None) -> float | int:
    number = _to_number(value)
    if kind == "scale" and not number.is_integer():
        raise InvalidValueError("not_integer")
    if minimum is not None and number < minimum:
        raise InvalidValueError("below_min", min=minimum)
    if maximum is not None and number > maximum:
        raise InvalidValueError("above_max", max=maximum)
    if kind == "scale" or number.is_integer():
        return int(number)
    return round(number, 2)


def _validate_text(value: Any, max_length: int, *, required: bool) -> str | None:
    if not isinstance(value, str):
        raise InvalidValueError("not_a_string")
    text = value.strip()
    if not text:
        if required:
            raise InvalidValueError("required")
        return None
    if len(text) > max_length:
        raise InvalidValueError("too_long", max=max_length)
    return text


def validate_value(  # noqa: PLR0913 - signature gardée : a1.py et les tests l'appellent par mots-clés
    kind: str,
    value: Any,
    *,
    options: tuple[str, ...] | list[str] = (),
    minimum: float | None = None,
    maximum: float | None = None,
    exclusive: tuple[str, ...] | list[str] = (),
    max_length: int = DEFAULT_TEXT_MAX,
    required: bool = True,
) -> Any:
    """Valide et normalise une valeur selon le genre de question; lève ``InvalidValueError``."""
    if value is None or (isinstance(value, str) and not value.strip() and kind != "text"):
        if required:
            raise InvalidValueError("required")
        return None
    if kind == "single_choice":
        return _validate_single_choice(value, options)
    if kind == "multi_choice":
        return _validate_multi_choice(value, options, exclusive, required=required)
    if kind == "boolean":
        return _validate_boolean(value)
    if kind in NUMERIC_KINDS:
        return _validate_number(kind, value, minimum, maximum)
    if kind == "text":
        return _validate_text(value, max_length, required=required)
    raise InvalidValueError("unknown_kind")


def _compare_as_numbers(compare: Callable[[float, float], bool], value: Any, bound: Any) -> bool:
    """Comparaison numérique; fausse quand l'une des deux valeurs n'est pas un nombre."""
    try:
        return bool(compare(float(value), float(bound)))
    except (TypeError, ValueError):
        return False


def _field_matches(value: Any, condition: dict[str, Any]) -> bool:
    """Condition simple (``in``, ``eq``, ``gte``...) sur la valeur connue d'un champ."""
    if "in" in condition:
        return value in condition["in"]
    if "not_in" in condition:
        return value not in condition["not_in"]
    if "eq" in condition:
        return value == condition["eq"]
    if "contains" in condition:
        return isinstance(value, list) and condition["contains"] in value
    for name, compare in _NUMERIC_COMPARISONS:
        if name in condition:
            return _compare_as_numbers(compare, value, condition[name])
    raise ValueError(f"unsupported condition {condition!r}")


def evaluate(condition: dict[str, Any] | None, values: dict[str, Any]) -> bool:
    """Condition ``when`` sur des champs connus; un champ inconnu rend la condition fausse.

    Formes acceptées : ``{field, in}``, ``{field, not_in}``, ``{field, eq}``, ``{field, gte|gt|lte|lt}``,
    ``{field, contains}`` (liste), et les combinaisons ``{all: [...]}``, ``{any: [...]}``, ``{not: {...}}``.
    """
    if not condition:
        return True
    if "all" in condition:
        return all(evaluate(part, values) for part in condition["all"])
    if "any" in condition:
        return any(evaluate(part, values) for part in condition["any"])
    if "not" in condition:
        return not evaluate(condition["not"], values)
    value = values.get(condition["field"])
    if value is None:
        return False
    return _field_matches(value, condition)


def format_field_value(spec: FieldSpec, value: Any, locale: str) -> str:
    if value is None:
        return "—"
    if spec.type == "enum":
        return spec.value_label(value, locale)
    if spec.type == "multi_enum":
        return ", ".join(spec.value_label(option, locale) for option in value) if value else "—"
    if spec.type == "boolean":
        return ("Yes" if value else "No") if locale == "en" else ("Oui" if value else "Non")
    if spec.type == "money":
        return format_money(value, locale)
    if spec.type == "percent":
        return f"{_number_text(value, locale)} %" if locale != "en" else f"{_number_text(value, locale)}%"
    if spec.type == "scale":
        return f"{value}/{int(spec.max or 5)}"
    if spec.type == "number":
        unit = localized(spec.unit, locale) if spec.unit else ""
        return f"{_number_text(value, locale)} {unit}".strip()
    return str(value)


# En français, les milliers sont séparés par une espace fine insécable (U+202F) et la virgule est décimale.
def _number_text(value: Any, locale: str) -> str:
    number = float(value)
    text = f"{int(number):,}" if number.is_integer() else f"{number:,.2f}"
    if locale == "en":
        return text
    return text.replace(",", "\u202f").replace(".", ",")


def format_money(value: Any, locale: str) -> str:
    number = float(value)
    if locale == "en":
        return f"${number:,.0f}" if number.is_integer() else f"${number:,.2f}"
    text = f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}"
    return text.replace(",", "\u202f").replace(".", ",") + " $"


@lru_cache(maxsize=1)
def default_questionnaire() -> Questionnaire:
    return Questionnaire.load()
