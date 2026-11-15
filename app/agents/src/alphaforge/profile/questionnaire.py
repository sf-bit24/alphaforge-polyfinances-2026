"""Moteur déterministe du questionnaire : chargement du YAML, conditions, rendu et validation des réponses.

Aucun modèle n'intervient ici. Le contenu (textes, options, poids, barèmes) vit dans ``questionnaire.yaml``;
ce module ne fait que l'appliquer, toujours de la même façon pour les mêmes réponses.

Types de champ et genre de question correspondant (CONTRACTS.md 3.3) :
``enum`` ↔ ``single_choice``, ``multi_enum`` ↔ ``multi_choice``, ``boolean``, ``number``, ``money``,
``percent``, ``scale`` et ``text`` portent le même nom des deux côtés.

Exception : un champ ``number``, ``money`` ou ``percent`` peut être demandé par une question ``single_choice``
à tranches. Chaque option porte un identifiant de tranche (``value``, une chaîne) et la valeur numérique écrite
dans le champ (``number``); le code convertit l'une en l'autre avant d'écrire le fait (``numeric_choices``).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

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
OPTION_VALUE = re.compile(r"^[a-z0-9_]{1,40}$")

YAML_PATH = Path(__file__).with_name("questionnaire.yaml")


class InvalidValue(ValueError):
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
        lo = self.min if self.min is not None else default_min(self.kind)
        hi = self.max if self.max is not None else default_max(self.kind)
        return lo, hi


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
        return int(self.followups.get("max_generated", 8))

    @property
    def max_open_questions(self) -> int:
        return int(self.followups.get("max_open_questions", 2))

    @property
    def open_fields(self) -> tuple[str, ...]:
        return tuple(self.followups.get("open_fields") or ())

    # ------------------------------------------------------------------ chargement
    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Questionnaire:
        fields: dict[str, FieldSpec] = {}
        for item in raw["fields"]:
            spec = FieldSpec(
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
            if spec.dimension not in DIMENSIONS:
                raise ValueError(f"field {spec.id}: unknown dimension")
            if spec.type not in TYPE_TO_KIND:
                raise ValueError(f"field {spec.id}: unknown type {spec.type}")
            if spec.id in fields:
                raise ValueError(f"duplicate field {spec.id}")
            if spec.choices is not None:
                _check_field_choices(spec)
            fields[spec.id] = spec
        questions: list[QuestionSpec] = []
        seen: set[str] = set()
        for item in raw["questions"]:
            spec_field = fields[item["field"]]
            kind = item["kind"]
            options = tuple(item.get("options") or spec_field.values)
            if kind == "single_choice" and spec_field.type in CHOICE_NUMBER_TYPES:
                _check_number_options(item["id"], spec_field, options)
            elif kind != spec_field.kind:
                raise ValueError(f"question {item['id']}: kind {kind} does not match field type {spec_field.type}")
            elif kind in CHOICE_KINDS:
                if {o["value"] for o in options} != set(spec_field.value_ids):
                    raise ValueError(f"question {item['id']}: options must match the field values")
            if item["id"] in seen:
                raise ValueError(f"duplicate question {item['id']}")
            seen.add(item["id"])
            questions.append(
                QuestionSpec(
                    id=item["id"],
                    field=spec_field,
                    kind=kind,
                    prompt=item["prompt"],
                    help=item.get("help"),
                    options=options if kind in CHOICE_KINDS else (),
                    when=item.get("when"),
                    required=bool(item.get("required", True)),
                )
            )
        completeness = raw.get("completeness") or {}
        followups = raw.get("followups") or {}
        for field_id in followups.get("open_fields") or ():
            if field_id not in fields or fields[field_id].type != "text":
                raise ValueError(f"followups.open_fields: {field_id} is not a text field")
        return cls(
            version=str(raw["version"]),
            threshold=float(completeness.get("threshold", 0.7)),
            cap=float(completeness.get("cap", 0.95)),
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
        return [q for q in self.questions if self.is_question_applicable(q, values)]

    # ------------------------------------------------------------------ rendu
    def render(self, question: QuestionSpec, locale: str) -> dict[str, Any]:
        return render_question(
            question_id=question.id,
            source="deterministic",
            field=question.field,
            kind=question.kind,
            prompt=localized(question.prompt, locale) or "",
            help_text=localized(question.help, locale),
            options=[{"value": o["value"], "label": localized(o["label"], locale)} for o in question.options],
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
    lo, hi = spec.bounds
    return (lo is None or number >= lo) and (hi is None or number <= hi)


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
        lo, hi = item.get("min"), item.get("max")
        if not _is_number(lo) or not _within(spec, lo) or (hi is not None and (not _is_number(hi) or hi < lo)):
            raise ValueError(f"{where}: tranche {item['value']} needs min <= max within the field bounds")
    if config.get("relative_to"):
        shares = config.get("shares") or []
        if not shares or any(not _is_number(s) or s <= 0 for s in shares) or sorted(shares) != list(shares):
            raise ValueError(f"{where}: shares must be increasing positive numbers")


def _tranche(spec: FieldSpec, item: dict[str, Any], locale: str) -> dict[str, Any]:
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


def _relative_tranches(
    spec: FieldSpec, config: dict[str, Any], values: dict[str, Any], locale: str
) -> list[dict[str, Any]] | None:
    """Tranches en dollars, parts du montant de référence; ``None`` si ce montant est inconnu ou trop petit."""
    base = values.get(config["relative_to"])
    if not _is_number(base) or base <= 0:
        return None
    shares = [float(s) for s in config["shares"]]
    cuts = [int(round(s * base)) for s in shares]
    if cuts[0] <= 0 or any(b <= a for a, b in zip(cuts, cuts[1:], strict=False)):
        return None
    if not _within(spec, cuts[-1]):
        return None
    en = locale == "en"
    of_amount = " of the amount" if en else " du montant"
    pct = "%" if en else " %"
    out = [
        {
            "value": f"lt{_share_id(shares[0])}pct",
            "label": (
                f"Less than {format_money(cuts[0], locale)} ({_share_text(shares[0], locale)}{pct}{of_amount})"
                if en
                else f"Moins de {format_money(cuts[0], locale)} ({_share_text(shares[0], locale)}{pct}{of_amount})"
            ),
            "number": 0,
            "min": 0,
            "max": cuts[0],
        }
    ]
    for (s_lo, s_hi), (lo, hi) in zip(
        zip(shares, shares[1:], strict=False), zip(cuts, cuts[1:], strict=False), strict=False
    ):
        a, b = _share_text(s_lo, locale), _share_text(s_hi, locale)
        out.append(
            {
                "value": f"{_share_id(s_lo)}to{_share_id(s_hi)}pct",
                "label": (
                    f"{format_money(lo, locale)} to less than {format_money(hi, locale)} ({a} to {b}{pct})"
                    if en
                    else f"De {format_money(lo, locale)} à moins de {format_money(hi, locale)} ({a} à {b}{pct})"
                ),
                "number": lo,
                "min": lo,
                "max": hi,
            }
        )
    last = _share_text(shares[-1], locale)
    out.append(
        {
            "value": f"{_share_id(shares[-1])}pct_plus",
            "label": (
                f"{format_money(cuts[-1], locale)} or more ({last}{pct} or more)"
                if en
                else f"{format_money(cuts[-1], locale)} ou plus ({last}{pct} ou plus)"
            ),
            "number": cuts[-1],
            "min": cuts[-1],
            "max": None,
        }
    )
    return out


def numeric_choices(q: Questionnaire, field_id: str, values: dict[str, Any], locale: str) -> list[dict[str, Any]]:
    """Tranches d'un champ ``number``, ``money`` ou ``percent`` : ``value`` (identifiant), ``label``, ``number``
    (la valeur écrite dans le champ, la plus prudente de la tranche), ``min`` et ``max`` (bornes, ``max`` nul
    sans borne haute). Fonction pure : mêmes tranches pour les mêmes valeurs confirmées.

    Sources, dans l'ordre : ``choices`` du champ dans le YAML (parts d'un montant de référence, sinon tranches
    absolues, filtrées par la bande ``within`` déjà connue), puis les options de la question de base du champ.
    Liste vide pour un champ qui n'est pas numérique ou qui n'a aucune tranche.
    """
    spec = q.fields.get(field_id)
    if spec is None or spec.type not in CHOICE_NUMBER_TYPES:
        return []
    config = spec.choices
    if config:
        tranches = _relative_tranches(spec, config, values, locale) if config.get("relative_to") else None
        if tranches is None:
            tranches = [_tranche(spec, item, locale) for item in config.get("tranches") or []]
        within = config.get("within")
        if within:
            band = values.get(within["field"])
            limits = (within.get("ranges") or {}).get(band) if band is not None else None
            if limits:
                lo, hi = limits
                tranches = [
                    t for t in tranches if t["min"] >= lo and (hi is None or (t["max"] is not None and t["max"] <= hi))
                ]
        return tranches
    question = q.question_for_field(field_id)
    if question is not None and question.numeric_choice:
        return [_tranche(spec, item, locale) for item in question.options]
    return []


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


def render_question(
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
        lo = minimum if minimum is not None else (field.min if field and field.min is not None else default_min(kind))
        hi = maximum if maximum is not None else (field.max if field and field.max is not None else default_max(kind))
    else:
        lo = hi = None
    return {
        "id": question_id,
        "source": source,
        "dimension": dimension or (field.dimension if field else "context"),
        "kind": kind,
        "prompt": prompt,
        "help": help_text,
        "options": options if kind in CHOICE_KINDS else [],
        "min": _plain_number(lo),
        "max": _plain_number(hi),
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


def _to_number(value: Any) -> float:
    if isinstance(value, bool):
        raise InvalidValue("not_a_number")
    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip().replace(" ", "").replace(" ", "").replace(" ", "")
        text = text.replace("$", "").replace("%", "")
        if text.count(",") == 1 and "." not in text:
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")
        try:
            number = float(text)
        except ValueError as exc:
            raise InvalidValue("not_a_number") from exc
    else:
        raise InvalidValue("not_a_number")
    if not math.isfinite(number):
        raise InvalidValue("not_a_number")
    return number


def validate_value(
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
    """Valide et normalise une valeur selon le genre de question; lève ``InvalidValue``."""
    if value is None or (isinstance(value, str) and not value.strip() and kind != "text"):
        if required:
            raise InvalidValue("required")
        return None
    if kind == "single_choice":
        if not isinstance(value, str):
            raise InvalidValue("not_a_string")
        if value not in options:
            raise InvalidValue("not_in_options", allowed=list(options))
        return value
    if kind == "multi_choice":
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise InvalidValue("not_a_list")
        if not value:
            if required:
                raise InvalidValue("empty")
            return []
        if len(set(value)) != len(value):
            raise InvalidValue("duplicate")
        unknown = [v for v in value if v not in options]
        if unknown:
            raise InvalidValue("not_in_options", allowed=list(options), unknown=unknown)
        if len(value) > 1 and any(v in exclusive for v in value):
            raise InvalidValue("exclusive", exclusive=list(exclusive))
        order = {v: i for i, v in enumerate(options)}
        return sorted(value, key=lambda v: order[v])
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
            return value.strip().lower() == "true"
        raise InvalidValue("not_boolean")
    if kind in NUMERIC_KINDS:
        number = _to_number(value)
        if kind == "scale":
            if not number.is_integer():
                raise InvalidValue("not_integer")
        if minimum is not None and number < minimum:
            raise InvalidValue("below_min", min=minimum)
        if maximum is not None and number > maximum:
            raise InvalidValue("above_max", max=maximum)
        if kind == "scale" or number.is_integer():
            return int(number)
        return round(number, 2)
    if kind == "text":
        if not isinstance(value, str):
            raise InvalidValue("not_a_string")
        text = value.strip()
        if not text:
            if required:
                raise InvalidValue("required")
            return None
        if len(text) > max_length:
            raise InvalidValue("too_long", max=max_length)
        return text
    raise InvalidValue("unknown_kind")


def evaluate(condition: dict[str, Any] | None, values: dict[str, Any]) -> bool:
    """Condition ``when`` sur des champs connus; un champ inconnu rend la condition fausse.

    Formes acceptées : ``{field, in}``, ``{field, not_in}``, ``{field, eq}``, ``{field, gte|gt|lte|lt}``,
    ``{field, contains}`` (liste), et les combinaisons ``{all: [...]}``, ``{any: [...]}``, ``{not: {...}}``.
    """
    if not condition:
        return True
    if "all" in condition:
        return all(evaluate(c, values) for c in condition["all"])
    if "any" in condition:
        return any(evaluate(c, values) for c in condition["any"])
    if "not" in condition:
        return not evaluate(condition["not"], values)
    value = values.get(condition["field"])
    if value is None:
        return False
    if "in" in condition:
        return value in condition["in"]
    if "not_in" in condition:
        return value not in condition["not_in"]
    if "eq" in condition:
        return value == condition["eq"]
    if "contains" in condition:
        return isinstance(value, list) and condition["contains"] in value
    for op, test in (
        ("gte", lambda a, b: a >= b),
        ("gt", lambda a, b: a > b),
        ("lte", lambda a, b: a <= b),
        ("lt", lambda a, b: a < b),
    ):
        if op in condition:
            try:
                return bool(test(float(value), float(condition[op])))
            except (TypeError, ValueError):
                return False
    raise ValueError(f"unsupported condition {condition!r}")


def format_field_value(spec: FieldSpec, value: Any, locale: str) -> str:
    if value is None:
        return "—"
    if spec.type == "enum":
        return spec.value_label(value, locale)
    if spec.type == "multi_enum":
        return ", ".join(spec.value_label(v, locale) for v in value) if value else "—"
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


def _number_text(value: Any, locale: str) -> str:
    number = float(value)
    text = f"{int(number):,}" if number.is_integer() else f"{number:,.2f}"
    if locale == "en":
        return text
    return text.replace(",", " ").replace(".", ",")


def format_money(value: Any, locale: str) -> str:
    number = float(value)
    if locale == "en":
        return f"${number:,.0f}" if number.is_integer() else f"${number:,.2f}"
    text = f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}"
    return text.replace(",", " ").replace(".", ",") + " $"


@lru_cache(maxsize=1)
def default_questionnaire() -> Questionnaire:
    return Questionnaire.load()
