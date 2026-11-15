"""Explication déterministe (sans LLM) d'un résultat ``scenario_risk`` : les 4 questions de l'atelier NBDB.

``render_fr(result)`` renvoie les sections de ``Explanation`` (``alphaforge.finance.contracts.decision``) :
``data_used``, ``why``, ``limits``, ``what_would_change``, chacune une liste de ``Statement`` (``text_fr``,
``fact_ids``, ``label``), plus ``headline`` (phrase principale) et ``text`` (tout le texte, prêt à afficher).

Chaque phrase qui contient un nombre du modèle cite les ``fact_id`` correspondants (fidélité par construction);
les hypothèses du modèle sont marquées ``HYPOTHESE``. Aucun chiffre n'est inventé ici : tout vient du résultat.

Arrondis des probabilités (``p_loss_gt_*``, ``p_mdd_gt_*``) : la valeur et la borne haute de l'IC sont arrondies
vers le HAUT, la borne basse vers le BAS (l'affichage ne sous-estime jamais un risque, l'IC affiché contient l'IC
calculé). Une probabilité nulle s'affiche « < 1/n_paths » (aucune trajectoire sur n ne dépasse le seuil : ce n'est
pas une probabilité nulle). Les autres métriques sont arrondies au plus proche.
"""

from __future__ import annotations

import json
import math
from typing import Any

# Constat du volet C (VALIDATION.md, contrôle (i) et 2021-2023), à dire dans chaque explication : le constat mesuré
# (FAIT) et ce qu'on en déduit pour le mélange affiché (HYPOTHESE), séparés.
BOND_RATE_LIMIT = (
    "Validation hors échantillon : dans les hausses de taux testées (1965-1981 en USD, 2021-2023), la perte maximale "
    "d'un portefeuille 100 % obligations a souvent dépassé le 90e centile des modèles ; pour 2022 (CAD77, 1 an), seul "
    "le modèle ancré sur le cash (sbb_ca) la couvrait de justesse (perte max. au 95e centile 15,0 % contre 14,3 % "
    "réalisée), les autres la sous-estimaient."
)
BOND_RATE_HYPOTHESIS = (
    "Pour un mélange riche en obligations, la perte possible lors d'une hausse des taux pourrait donc être plus "
    "grande que ces chiffres."
)

SECTIONS = (
    ("data_used", "Données utilisées"),
    ("why", "Pourquoi ce résultat"),
    ("limits", "Limites"),
    ("what_would_change", "Ce qui changerait la réponse"),
)


def _format_percent(number: float, decimals: int) -> str:
    text = f"{number:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",").replace("-", "−") + " %"


def _step(number: float) -> tuple[float, int]:
    return (0.1, 1) if abs(number) < 10 else (1.0, 0)


def pct(value: float, rounding: str = "nearest") -> str:
    """0.123 -> « 12 % »; 0.042 -> « 4,2 % » (une décimale sous 10 %). ``rounding`` : nearest, up ou down."""
    number = value * 100
    step, decimals = _step(number)
    if rounding != "nearest":
        scaled = number / step
        # Tolérance : 0.125 * 100 vaut 12.500000000000002 et ne doit pas devenir 13.
        scaled = math.ceil(scaled - 1e-9) if rounding == "up" else math.floor(scaled + 1e-9)
        number = scaled * step
        if rounding == "up" and abs(number) >= 10 and decimals:
            decimals = 0
            number = math.ceil(number - 1e-9)
    return _format_percent(number, decimals)


def is_probability(metric: str | None) -> bool:
    return bool(metric) and str(metric).startswith(("p_loss_gt_", "p_mdd_gt_"))


def prob(value: float, n_paths: int | None, rounding: str = "up") -> str:
    """Probabilité affichée sans sous-estimer : 0 -> « < 1/n_paths » (ou « 0 % » si n_paths est inconnu)."""
    if value <= 0 and rounding != "down":
        if n_paths:
            bound = 100 / n_paths
            decimals = max(1, -math.floor(math.log10(bound)) + 1) if bound < 1 else 1
            # Arrondi vers le haut : « < x » doit rester vrai (x >= 1/n_paths).
            return "< " + _format_percent(math.ceil(bound * 10**decimals - 1e-9) / 10**decimals, decimals)
        return "0 %"
    return pct(max(value, 0.0), rounding)


def _decimal(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def money(value: float) -> str:
    return f"{round(value):,}".replace(",", " ") + " $"


def _fact_ids(view: dict[str, Any]) -> list[str]:
    base = view["fact_id"]
    return [base, base + ".ci_lo", base + ".ci_hi"]


def _interval(view: dict[str, Any], metric: str | None = None) -> str:
    metric = metric or view.get("metric")
    if is_probability(metric):
        n = view.get("n_paths")
        # Borne haute nulle : on affiche 1/n_paths sans « < » (l'intervalle affiché contient toujours le calculé).
        low, high = prob(view["ci_lo"], n, "down"), prob(view["ci_hi"], n, "up").removeprefix("< ")
        return f"{prob(view['value'], n, 'up')} [IC 90 % : {low}–{high}]"
    return f"{pct(view['value'])} [IC 90 % : {pct(view['ci_lo'])}–{pct(view['ci_hi'])}]"


def _statement(text: str, fact_ids: list[str] | None = None, label: str = "FAIT") -> dict[str, Any]:
    return {"text_fr": text, "fact_ids": list(fact_ids or []), "label": label}


def _paths(result: dict[str, Any]) -> str:
    paths = f"{result['n_paths']} trajectoires" if result.get("n_paths") else "nombre de trajectoires non indiqué"
    return f"{paths}, graine {result['seed']}" if result.get("seed") is not None else paths


def _years(result: dict[str, Any]) -> str:
    start = str(result.get("window_start") or "")[:4]
    end = str(result.get("fitted_through") or "")[:4]
    return f"{start}–{end}" if start else f"jusqu'à {end}"


def _headline(result: dict[str, Any]) -> tuple[str, list[str]]:
    primary, bucket, horizon = result["primary"], result["threshold"], result["horizon"]
    who = f"Selon le modèle {result['model_name']} (données {_years(result)}, {result['currency'] or result['family']})"
    years = f"{horizon['used']} ans"
    if not horizon["exact"]:
        years += f" (horizon de la grille juste sous les {horizon['requested']} ans demandés)"
    tail = " ; c'est un modèle, pas une prévision."
    if bucket:
        view = {"metric": bucket["bucket_metric"], **primary[bucket["bucket_metric"]]}
        if bucket["is_lower_bound"]:
            text = (
                f"{who}, au moins {_interval(view)} de probabilité de perdre plus de "
                f"{money(bucket['loss_threshold_cad'])} sur {years} (plus petit palier de la table : "
                f"{pct(bucket['bucket_pct'])} du montant){tail}"
            )
        elif bucket["exact"]:
            loss = money(bucket["bucket_cad"])
            text = f"{who}, {_interval(view)} de probabilité de perdre plus de {loss} sur {years}{tail}"
        else:
            text = (
                f"{who}, {_interval(view)} de probabilité de perdre plus de {money(bucket['bucket_cad'])} "
                f"({pct(bucket['bucket_pct'])} du montant) sur {years} ; pour le seuil demandé de "
                f"{money(bucket['loss_threshold_cad'])}, c'est un majorant{tail}"
            )
        return text, _fact_ids(view)
    if "ret_ann_p10" in primary:
        view = primary["ret_ann_p10"]
        text = (
            f"{who}, dans 10 % des scénarios le rendement annualisé sur {years} est inférieur à {_interval(view)}{tail}"
        )
        return text, _fact_ids(view)
    metric, view = next(iter(primary.items()))
    return f"{who}, {metric} = {_interval(view, metric)} sur {years}{tail}", _fact_ids(view)


def _refusal_explanation(result: dict[str, Any]) -> dict[str, Any]:
    message = (result.get("error") or {}).get("message", "refus")
    statement = _statement(f"Aucun chiffre produit : {message}. {result.get('disclaimer_fr', '')}".strip(), [], "FAIT")
    out = {key: [] for key, _ in SECTIONS} | {"limits": [statement], "headline": statement["text_fr"]}
    out["text"] = statement["text_fr"]
    return out


def _data_used(result: dict[str, Any], headline_fact_id: str) -> list[dict[str, Any]]:
    run, grid = result["run"], result["grid"]
    return [
        _statement(
            f"Table de scénarios {run['run_id']} (sha256 {run['table_sha256'][:12]}…, code {run['code_sha']}), "
            f"modèle {result['model_name']} ({result['model_id']}), famille {result['family']} "
            f"({result['currency'] or '?'}, base {result['basis']}), données {_years(result)} "
            f"(ajusté jusqu'à {result['fitted_through'] or 'non indiqué'}), {_paths(result)}.",
            [headline_fact_id],
        ),
        _statement(
            f"Mélange de la grille retenu : {grid['mix_id']}, à une distance L1 de {_decimal(grid['l1_distance'])} "
            f"du mélange demandé (tolérance {_decimal(grid['max_l1_distance'])}).",
            [grid["l1_fact_id"]],
        ),
    ]


def _why(result: dict[str, Any], headline: str, headline_fact_ids: list[str]) -> list[dict[str, Any]]:
    primary, horizon = result["primary"], result["horizon"]
    why = [_statement(headline, headline_fact_ids, "HYPOTHESE" if result["hypothese"] else "FAIT")]
    if "ret_ann_p10" in primary and "ret_ann_p50" in primary:
        p10, p50 = primary["ret_ann_p10"], primary["ret_ann_p50"]
        why.append(
            _statement(
                f"Rendement annualisé sur {horizon['used']} ans : médiane {_interval(p50)}, "
                f"10e centile {_interval(p10)}.",
                _fact_ids(p50) + _fact_ids(p10),
            )
        )
    if "mdd_p90" in primary:
        view = primary["mdd_p90"]
        why.append(
            _statement(
                f"Dans 10 % des scénarios, la baisse maximale en cours de route dépasse {_interval(view)}.",
                _fact_ids(view),
            )
        )
    if result.get("wealth_p10_amount"):
        wealth = result["wealth_p10_amount"]
        why.append(
            _statement(
                f"Patrimoine final au 10e centile : environ {money(wealth['value'])} "
                f"[IC 90 % : {money(wealth['ci_lo'])}–{money(wealth['ci_hi'])}].",
                [wealth["fact_id"], *_fact_ids(primary["wealth_p10"])],
            )
        )
    return why


def _model_limits(result: dict[str, Any]) -> list[dict[str, Any]]:
    limits = [
        _statement(
            "C'est un modèle statistique des rendements passés, pas une prévision : il suppose que l'avenir "
            "ressemble aux périodes historiques rééchantillonnées; un choc sans précédent n'y figure pas.",
            [],
            "HYPOTHESE",
        )
    ]
    limits += [_statement(str(assumption), [], "HYPOTHESE") for assumption in result.get("model_assumptions") or []]
    limits.append(_statement(BOND_RATE_LIMIT, [], "FAIT"))
    limits.append(_statement(BOND_RATE_HYPOTHESIS, [], "HYPOTHESE"))
    return limits


def _validation_limits(result: dict[str, Any]) -> list[dict[str, Any]]:
    limits: list[dict[str, Any]] = []
    if result.get("validated") is False:
        limits.append(
            _statement(
                "Résultat non validé hors échantillon : " + "; ".join(result.get("validation_reasons") or []) + ".",
                [],
            )
        )
    if result.get("degraded_calibration"):
        limits.append(
            _statement(
                f"Mise en garde : calibration dégradée à long horizon ({result['horizon']['used']} ans) ; "
                "les probabilités sont moins fiables qu'à 1 ou 3 ans.",
                [],
            )
        )
    by_model = result.get("validation_by_model") or {result["model_id"]: result.get("validation")}
    for model, validation in by_model.items():
        if validation:
            text = validation if isinstance(validation, str) else json.dumps(validation, ensure_ascii=False)
            limits.append(
                _statement(f"Validation hors échantillon de {model} (manifeste, citée telle quelle) : {text}", [])
            )
        else:
            limits.append(_statement(f"Le manifeste ne fournit pas de validation hors échantillon pour {model}.", []))
    return limits


def _data_limits(result: dict[str, Any]) -> list[dict[str, Any]]:
    limits: list[dict[str, Any]] = []
    integrity = result.get("integrity") or {}
    if integrity.get("ci_not_enclosing"):
        limits.append(
            _statement(
                f"Pour {integrity['ci_not_enclosing']} valeur(s) de la table, l'IC à 90 % (bootstrap des paramètres) "
                "n'encadre pas la valeur centrale : l'estimation est instable à cet endroit.",
                [],
            )
        )
    if result["hypothese"]:
        limits.append(
            _statement(
                "Le mélange contient de la crypto, dont l'historique ne commence qu'en 2014 : chiffres HYPOTHESE.",
                [],
                "HYPOTHESE",
            )
        )
    return limits


def _grid_limits(result: dict[str, Any]) -> list[dict[str, Any]]:
    horizon, bucket, grid = result["horizon"], result["threshold"], result["grid"]
    limits: list[dict[str, Any]] = []
    if not horizon["exact"]:
        limits.append(
            _statement(
                f"Horizon {horizon['requested']} ans absent de la grille : chiffres à {horizon['used']} ans, sans "
                "interpolation. La probabilité de perte ne varie pas forcément de façon régulière avec l'horizon.",
                [],
                "HYPOTHESE",
            )
        )
    if bucket and bucket["is_lower_bound"]:
        limits.append(
            _statement(
                f"Seuil demandé ({pct(bucket['requested_pct'])} du montant) sous le plus petit palier de la table : "
                "le chiffre est un minorant.",
                [],
            )
        )
    if bucket and result["currency"] and result["currency"] != "CAD":
        limits.append(
            _statement(
                f"Famille en {result['currency']} : le seuil en dollars canadiens est appliqué en pourcentage, sans "
                "conversion de change.",
                [],
                "HYPOTHESE",
            )
        )
    if grid["l1_distance"] > 0:
        limits.append(
            _statement("Le mélange demandé a été rapproché de la grille ; aucune extrapolation.", [grid["l1_fact_id"]])
        )
    return limits


def _limits(result: dict[str, Any]) -> list[dict[str, Any]]:
    return _model_limits(result) + _validation_limits(result) + _data_limits(result) + _grid_limits(result)


def _model_disagreement(result: dict[str, Any], focus: str | None) -> list[dict[str, Any]]:
    statements = []
    others = [
        entry for entry in result["all_models"] if entry["model_id"] != result["model_id"] and focus in entry["metrics"]
    ]
    for other in others:
        view = other["metrics"][focus]
        text = f"Avec le modèle {other['name']} ({other['model_id']}) : {_interval(view, focus)}."
        statements.append(_statement(text, _fact_ids(view)))
    spread = result["model_spread"].get(focus) if focus else None
    if spread and spread["max"] - spread["min"] > 0:
        if is_probability(focus):
            low, high = prob(spread["min"], None, "down"), prob(spread["max"], None, "up")
        else:
            low, high = pct(spread["min"]), pct(spread["max"])
        statements.append(
            _statement(
                f"Écart entre modèles : de {low} ({spread['min_model']}) à {high} "
                f"({spread['max_model']}); ce désaccord fait partie de l'incertitude.",
                [entry["metrics"][focus]["fact_id"] for entry in result["all_models"] if focus in entry["metrics"]],
            )
        )
    return statements


def _threshold_alternatives(result: dict[str, Any]) -> list[dict[str, Any]]:
    bucket = result["threshold"]
    if not bucket:
        return []
    return [
        _statement(
            f"Avec un seuil de perte de {int(metric[-2:])} % du montant : {_interval(view, metric)}.",
            _fact_ids(view),
        )
        for metric, view in result["primary"].items()
        if metric.startswith("p_loss_gt_") and metric != bucket["bucket_metric"]
    ]


def _what_would_change(result: dict[str, Any]) -> list[dict[str, Any]]:
    primary, bucket = result["primary"], result["threshold"]
    focus = bucket["bucket_metric"] if bucket else ("ret_ann_p10" if "ret_ann_p10" in primary else None)
    change = _model_disagreement(result, focus) + _threshold_alternatives(result)
    upper = result.get("upper_horizon")
    if upper:
        change.append(
            _statement(
                f"À {upper['horizon_years']} ans (horizon supérieur de la grille) : {_interval(upper)}.",
                _fact_ids(upper),
            )
        )
    change.append(
        _statement(
            "Un autre mélange (plus ou moins d'actions), un autre horizon, la base réelle (après inflation) ou une "
            "autre famille de données changeraient ces chiffres : relancer l'outil plutôt que d'extrapoler.",
            [],
            "HYPOTHESE",
        )
    )
    return change


def _display_text(explanation: dict[str, Any], disclaimer_fr: str) -> str:
    lines = [explanation["headline"], ""]
    for key, title in SECTIONS:
        lines.append(f"{title} :")
        lines += [
            f"- {statement['text_fr']}" + (" (hypothèse)" if statement["label"] == "HYPOTHESE" else "")
            for statement in explanation[key]
        ]
    lines.append(disclaimer_fr)
    return "\n".join(lines)


def render_fr(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "ok":
        return _refusal_explanation(result)
    headline, headline_fact_ids = _headline(result)
    out = {
        "headline": headline,
        "data_used": _data_used(result, headline_fact_ids[0]),
        "why": _why(result, headline, headline_fact_ids),
        "limits": _limits(result),
        "what_would_change": _what_would_change(result),
    }
    out["text"] = _display_text(out, result["disclaimer_fr"])
    return out
