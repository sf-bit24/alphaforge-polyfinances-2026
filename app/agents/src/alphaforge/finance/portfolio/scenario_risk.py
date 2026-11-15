"""PROB_LOSS : contrôle du Judge (F4) par la table de scénarios précalculée (outil ``scenario_risk``).

Simulation seulement, jamais un conseil. Déterministe, sans LLM : le Judge appelle ``evaluate_prob_loss`` pour une
limite ``kind = "risk"``, ``selector.measure = "PROB_LOSS"`` (proposition ``scenarios/PROPOSAL_PROB_LOSS.md``) :

    P(perte cumulée du portefeuille à l'horizon H > L) ≤ α     (L = loss_level, H = horizon_years, α = Limit.max)

Aucune valeur de α, L ou H n'est fixée ici : elles viennent de F1 (``prob_loss_limit`` est l'aide de F1, non
appelée tant que F1 n'émet pas PROB_LOSS).

Règles (prudentes partout) :
- **Valeur comparée à α : la borne haute ``ci_hi`` de l'IC à 90 %**. ``ci_hi ≤ α`` : respecté ; sinon violé (l'IC
  chevauche α, ou la valeur centrale dépasse α). ``active = |ci_hi − α| ≤ TOL``.
- **Horizon hors grille** : l'outil lit l'horizon inférieur et donne l'horizon supérieur ; la décision porte sur
  ``max(ci_hi inférieur, ci_hi supérieur)``, sans interpolation. Horizon supérieur absent : non vérifiable.
- **Seuil** arrondi vers le bas au palier ``p_loss_gt_XX`` (majorant). L sous le plus petit palier : minorant,
  donc **non vérifiable**.
- **Non vérifiable = violé** (refus prudent, même convention que ``STRESS_2022`` sans 2022 et qu'une mesure
  indisponible) : valeur du Fact ``-1``, raison écrite dans ``Source.processing`` et dans ``JudgeReport.warnings``.
  Cas : actif sans bloc de scénarios, table absente, magasin refusé (AccessDenied / 403), scénarios désactivés,
  refus de l'outil (hors grille, mélange trop éloigné, modèle absent…), minorant. Le Judge ne lève jamais d'erreur
  pour autant : le pipeline continue et la limite apparaît « non vérifiable » dans les contrôles.
- **Désaccord entre modèles** : si un autre modèle affiché de la table donne ``ci_hi > α`` au même point, un
  avertissement non bloquant le nomme (la décision reste sur ``scenario_model_id`` ou le modèle par défaut).

Rattachement des actifs aux blocs (``CA_EQ, US_MKT, BONDS, CASH, GOLD, CRYPTO``), dans cet ordre :
1. ``policy.scenario_blocks[a]`` (déclaré par F1, HYPOTHESE sourcée) ;
2. ``policy.history_proxies[a].proxy`` s'il est la série même d'un bloc de la famille (proposition, § 2) ;
3. l'actif est la série même d'un bloc de la famille (ex. ``CA_GOV_10Y`` = BONDS en CAD77) ;
4. le catalogue de l'engine (``assets.csv``, colonne ``proxy_for_ticker``) désigne **une seule** série qui est
   celle d'un bloc : ``XIU.TO -> CA_EQ``, ``SPY``/``ESGV -> US_MKT``, ``XBB.TO -> CA_GOV_10Y = BONDS``,
   ``ZST.TO -> CA_TBILL = CASH``, ``GLD -> GOLD`` (en CAD77). HYPOTHESE : un FNB n'est pas l'indice du bloc.
Tout le reste n'est **pas** rattaché (titres individuels, secteurs, ``QQQ``, ``AGG``, ``TLT``, obligations
synthétiques autres que la série du bloc, ``ETH-USD``…) : les rattacher à un indice large sous-estimerait leur
risque (concentration, durée, crédit). Un seul actif détenu sans bloc rend le contrôle non vérifiable, avec la
liste des actifs et la raison ; F1 peut les déclarer dans ``scenario_blocks`` en le justifiant.

Disponibilité de la table (aucune erreur levée) : ``ALPHAFORGE_SCENARIOS`` = ``0``/``off``/``false``/``no``
désactive ; sinon le magasin du projet (``ALPHAFORGE_STORE``, local ou S3) est lu en lecture seule.
``set_table_provider`` remplace la source (tests, rejeu).
"""

from __future__ import annotations

import math
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..contracts import Fact, Limit, PolicySpec, Selector, Source, TraceEvent

TOL = 1e-4
TOOL = "scenario_risk"
DISABLED_VALUES = ("0", "off", "false", "no", "non")
UNAVAILABLE_FR = "scénarios indisponibles"
ACCESS_DENIED_CODES = ("AccessDenied", "403", "Forbidden")
# Séries du build long qui forment chaque bloc, par famille (miroir de alphaforge.scenarios.data.FAMILIES et du
# README des scénarios ; CRYPTO n'existe que dans le pool CAD77+CRYPTO, rangé sous la famille CAD77).
FAMILY_BLOCK_SERIES: dict[str, dict[str, str]] = {
    "CAD77": {
        "CA_EQ": "CA_EQ",
        "US_MKT": "US_MKT",
        "BONDS": "CA_GOV_10Y",
        "CASH": "CA_TBILL",
        "GOLD": "GOLD",
        "CRYPTO": "BTC-USD",
    },
    "CAD71": {"US_MKT": "US_MKT", "BONDS": "CA_GOV_10Y", "CASH": "CA_TBILL"},
    "USD1926": {"US_MKT": "US_MKT", "BONDS": "UST_10Y", "CASH": "UST_TBILL"},
}


# --------------------------------------------------------------------------- source de la table

TableProvider = Callable[[str | None], Any]  # run_id -> ScenarioTable (lève si indisponible)


class _TableSource:
    """Lecture de la table : fournisseur injecté (tests, rejeu) ou magasin du projet, un chargeur par run_id."""

    def __init__(self) -> None:
        self.provider: TableProvider | None = None
        self._loaders: dict[str | None, Any] = {}
        self._lock = threading.Lock()

    def replace(self, provider: TableProvider | None) -> None:
        with self._lock:
            self.provider = provider
            self._loaders.clear()

    def read(self, run_id: str | None) -> Any:
        """La table du run (lève si indisponible)."""
        if self.provider is not None:
            return self.provider(run_id)
        return self._store_loader(run_id).load()

    def _store_loader(self, run_id: str | None) -> Any:
        """Un chargeur par run_id et par processus (cache de la table), sur le magasin du projet."""
        with self._lock:
            loader = self._loaders.get(run_id)
            if loader is None:
                from ...config import Settings
                from ...scenarios.tool_table import ScenarioTableLoader
                from ...store import make_store

                loader = ScenarioTableLoader(make_store(Settings.from_env()), run_id=run_id)
                self._loaders[run_id] = loader
            return loader


_SOURCE = _TableSource()


def scenarios_enabled(environ=None) -> bool:
    env = os.environ if environ is None else environ
    return (env.get("ALPHAFORGE_SCENARIOS") or "").strip().lower() not in DISABLED_VALUES


def set_table_provider(provider: TableProvider | None) -> None:
    """Remplace la lecture de la table (tests, rejeu) ; ``None`` revient au magasin du projet."""
    _SOURCE.replace(provider)


def describe_error(exc: BaseException) -> str:
    """Raison lisible d'une indisponibilité, sans rien recopier d'une réponse AWS (ni ARN, ni identifiant)."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = str((response.get("Error") or {}).get("Code") or "")
        if code in ACCESS_DENIED_CODES:
            return "lecture du magasin refusée (AccessDenied)"
        return f"erreur du magasin ({type(exc).__name__} {code})".strip()
    from ...scenarios.tool_table import ScenarioTableError

    if isinstance(exc, ScenarioTableError):
        return str(exc)[:300]
    return f"{type(exc).__name__}"


def load_table(run_id: str | None = None) -> tuple[Any | None, str | None]:
    """(table, None) ou (None, raison). Ne lève jamais : désactivé, absent, refusé et illisible sont des raisons."""
    if not scenarios_enabled():
        return None, f"{UNAVAILABLE_FR} : désactivés (ALPHAFORGE_SCENARIOS)"
    try:
        table = _SOURCE.read(run_id)
    except Exception as exc:  # une table indisponible n'arrête jamais le Judge ni le pipeline
        return None, f"{UNAVAILABLE_FR} : {describe_error(exc)}"
    if table is None:
        return None, f"{UNAVAILABLE_FR} : table absente"
    return table, None


class SafeTableLoader:
    """Chargeur compatible ``ScenarioRiskTool`` : toute indisponibilité devient ``ScenarioTableError`` (refus de
    l'outil ``table_unavailable``), y compris AccessDenied et les scénarios désactivés."""

    def __init__(self, run_id: str | None = None):
        self.run_id = run_id
        self.reason: str | None = None

    def load(self, *, refresh: bool = False):  # même signature que ScenarioTableLoader.load
        from ...scenarios.tool_table import ScenarioTableError

        table, reason = load_table(self.run_id)
        self.reason = reason
        if table is None:
            raise ScenarioTableError(reason)
        return table


# --------------------------------------------------------------------------- rattachement aux blocs


@dataclass(frozen=True)
class BlockMapping:
    weights: dict[str, float]  # bloc -> poids (somme des actifs rattachés)
    assets: dict[str, tuple[str, str]]  # actif -> (bloc, justification)
    unmapped: dict[str, str]  # actif -> raison

    @property
    def ok(self) -> bool:
        return not self.unmapped and bool(self.weights)

    def describe(self) -> str:
        return ", ".join(f"{asset}->{block}" for asset, (block, _) in sorted(self.assets.items()))


def _catalog():
    from ..backtest import data as bt_data

    return bt_data.load_assets()


def _declared_block(asset: str, policy: PolicySpec, family: str) -> tuple[str | None, str] | None:
    """Rattachement déclaré par le mandat (``scenario_blocks``, puis ``history_proxies``), ou None s'il n'y en a pas."""
    series = FAMILY_BLOCK_SERIES.get(family, {})
    by_series = {name: block for block, name in series.items()}
    declared = policy.scenario_blocks.get(asset)
    if declared is not None:
        if declared.block not in series:
            return None, f"bloc déclaré {declared.block} absent de la famille {family}"
        return declared.block, f"policy.scenario_blocks ({declared.source})"
    proxy = policy.history_proxies.get(asset)
    if proxy is not None and proxy.proxy in by_series:
        return by_series[proxy.proxy], f"policy.history_proxies -> {proxy.proxy} ({proxy.source})"
    if asset in by_series:
        return by_series[asset], f"série {asset} = bloc {by_series[asset]} de {family}"
    return None


def _catalog_block(asset: str, family: str, catalog) -> tuple[str | None, str]:
    """Rattachement par le catalogue de l'engine : une seule série ``proxy_for_ticker`` qui est celle d'un bloc."""
    by_series = {name: block for block, name in FAMILY_BLOCK_SERIES.get(family, {}).items()}
    if asset not in catalog.index:
        return None, "actif inconnu du catalogue de l'engine"
    proxy = str(catalog.at[asset, "proxy_for_ticker"] or "").strip()
    if proxy and ";" not in proxy and "(" not in proxy and proxy in by_series:
        return by_series[proxy], f"catalogue engine : proxy_for_ticker {proxy} = bloc {by_series[proxy]} de {family}"
    asset_class = str(catalog.at[asset, "asset_class"])
    return None, (
        f"aucun bloc de {family} ne représente {asset} ({asset_class}"
        + (f", proxy {proxy}" if proxy else "")
        + ") sans sous-estimer son risque"
    )


def block_of(asset: str, policy: PolicySpec, family: str, catalog=None) -> tuple[str | None, str]:
    """(bloc, justification) ou (None, raison). Ordre et prudence : voir la docstring du module."""
    declared = _declared_block(asset, policy, family)
    if declared is not None:
        return declared
    return _catalog_block(asset, family, catalog if catalog is not None else _catalog())


def map_to_blocks(weights: dict[str, float], policy: PolicySpec, family: str, catalog=None) -> BlockMapping:
    blocks: dict[str, float] = {}
    assets: dict[str, tuple[str, str]] = {}
    unmapped: dict[str, str] = {}
    held = {asset: float(x) for asset, x in weights.items() if float(x) > 1e-9}
    if any(asset not in policy.scenario_blocks for asset in held):
        catalog = catalog if catalog is not None else _catalog()
    for asset, x in sorted(held.items()):
        block, why = block_of(asset, policy, family, catalog)
        if block is None:
            unmapped[asset] = why
            continue
        assets[asset] = (block, why)
        blocks[block] = blocks.get(block, 0.0) + x
    return BlockMapping(blocks, assets, unmapped)


# --------------------------------------------------------------------------- évaluation


@dataclass
class ProbLossResult:
    value: float  # ci_hi décisif, NaN si non vérifiable
    violated: bool
    active: bool
    processing: str
    source: Source
    facts: list[Fact] = field(default_factory=list)  # Facts de l'outil (trace_id = trace de l'outil)
    traces: list[TraceEvent] = field(default_factory=list)  # TraceEvent de l'outil, enfant du Judge
    warnings: list[str] = field(default_factory=list)
    unverifiable: str | None = None


class _UnverifiableError(Exception):
    """Contrôle impossible à décider : refus prudent, avec la trace et la source de l'outil s'il a tourné."""

    def __init__(self, reason: str, *, traces=(), source: Source | None = None):
        super().__init__(reason)
        self.reason = reason
        self.traces = list(traces)
        self.source = source


def _unverifiable(rule_id: str, reason: str, *, traces=(), source: Source | None = None) -> ProbLossResult:
    return ProbLossResult(
        value=float("nan"),
        violated=True,
        active=False,
        processing=f"scenario_risk : NON VÉRIFIABLE ({reason}) : refus prudent",
        source=source or Source(dataset="scenarios:indisponible", processing=reason[:300]),
        traces=list(traces),
        warnings=[f"{rule_id}: PROB_LOSS non vérifiable : {reason}"],
        unverifiable=reason,
    )


def _trace(raw: dict, parent_id: str) -> TraceEvent:
    return TraceEvent.model_validate({**raw, "parent_id": parent_id})


@dataclass(frozen=True)
class _ToolRun:
    """Un appel de l'outil pour le Judge : le résultat, sa trace (enfant du Judge) et la source de la table."""

    result: dict
    traces: list[TraceEvent]
    source: Source

    def refuse(self, reason: str) -> _UnverifiableError:
        return _UnverifiableError(reason, traces=self.traces, source=self.source)


def _mapped_blocks(weights: dict[str, float], policy: PolicySpec, family: str, catalog) -> BlockMapping:
    mapping = map_to_blocks(weights, policy, family, catalog)
    if mapping.unmapped:
        reasons = "; ".join(f"{asset} : {why}" for asset, why in sorted(mapping.unmapped.items()))
        raise _UnverifiableError(f"actifs sans bloc de scénarios ({reasons})")
    if not mapping.weights:
        raise _UnverifiableError("aucun actif détenu")
    return mapping


def _run_tool(request: dict, run_id: str | None, parent_trace_id: str) -> _ToolRun:
    """Lit la table et appelle l'outil ; table indisponible : refus de l'outil tracé, puis non vérifiable."""
    from ...scenarios.tool import RefusalError, _refusal, compute_scenario_risk
    from ...scenarios.tool_facts import trace_id_for

    table, reason = load_table(run_id)
    if table is None:
        full = {**request, "basis": "nominal", "include_sensitivity": False}
        refusal = _refusal(
            None,
            full,
            trace_id_for(full, None),
            datetime.now(UTC).isoformat(),
            RefusalError("table_unavailable", reason),
        )
        raise _UnverifiableError(reason, traces=[_trace(refusal["trace_event"], parent_trace_id)])
    result = compute_scenario_risk(table, **request)
    run = _ToolRun(result, [_trace(result["trace_event"], parent_trace_id)], Source.model_validate(table.source()))
    if result["status"] != "ok":
        error = result["error"]
        raise run.refuse(f"refus de l'outil ({error['code']}) : {error['message']}")
    return run


def _decisive_ci_hi(run: _ToolRun, selector: Selector) -> tuple[float, str]:
    """Borne haute décisive et horizon lu ; horizon hors grille : max des deux horizons qui l'encadrent."""
    result = run.result
    threshold, horizon = result["threshold"], result["horizon"]
    metric = threshold["bucket_metric"]
    if threshold["is_lower_bound"]:
        raise run.refuse(
            f"seuil {selector.loss_level:.0%} sous le plus petit palier ({metric}) : la probabilité "
            "lue serait un minorant"
        )
    ci_hi, horizon_used = float(result["primary"][metric]["ci_hi"]), str(horizon["used"])
    if not horizon["exact"]:
        upper = result.get("upper_horizon")
        if not upper or upper.get("metric") != metric:
            raise run.refuse(
                f"horizon {selector.horizon_years} ans hors grille et horizon supérieur "
                f"{horizon['upper']} ans sans {metric}"
            )
        ci_hi = max(ci_hi, float(upper["ci_hi"]))
        horizon_used = f"max({horizon['used']}, {horizon['upper']})"
    if not math.isfinite(ci_hi):
        raise run.refuse("borne haute non finie")
    return ci_hi, horizon_used


def _warnings(result: dict, rule_id: str, alpha: float) -> list[str]:
    """Désaccord entre modèles affichés et lecture hors du domaine validé : avertissements non bloquants."""
    metric, horizon_used = result["threshold"]["bucket_metric"], result["horizon"]["used"]
    warnings = [
        f"{rule_id}: désaccord entre modèles : {entry['model_id']} donne une borne haute "
        f"{entry['metrics'][metric]['ci_hi']:.4f} > α {alpha:.4f} ({metric}, {horizon_used} ans) ; "
        f"décision sur {result['model_id']}"
        for entry in result["all_models"]
        if entry["model_id"] != result["model_id"]
        and metric in entry["metrics"]
        and entry["metrics"][metric]["ci_hi"] > alpha + TOL
    ]
    if not result.get("validated", False):
        warnings.append(
            f"{rule_id}: PROB_LOSS lue hors du domaine validé hors échantillon : "
            + "; ".join(result.get("validation_reasons") or ["non validé"])
        )
    return warnings


def _processing(result: dict, family: str, horizon_used: str, mapping: BlockMapping) -> str:
    grid, run = result["grid"], result["run"]
    return (
        f"scenario_risk {result['model_id']}, famille {family}, mix {grid['mix_id']} "
        f"(L1 {grid['l1_distance']:.2f}), horizon {horizon_used} ans, palier {result['threshold']['bucket_metric']}, "
        f"run {run['run_id']}, table sha256 {run['table_sha256'][:12]}, code {run['code_sha']}, ajusté jusqu'à "
        f"{result['fitted_through']} ; borne haute IC 90 % décisive ; blocs {mapping.describe()} (HYPOTHESE)"
    )


def _evaluate(
    limit: Limit, weights: dict[str, float], policy: PolicySpec, parent_trace_id: str, catalog
) -> ProbLossResult:
    selector, alpha = limit.selector, float(limit.max)
    family = policy.scenario_family_used
    mapping = _mapped_blocks(weights, policy, family, catalog)
    request = {
        "weights": mapping.weights,
        "horizon_years": int(selector.horizon_years),
        "loss_threshold_cad": selector.loss_level,
        "amount_cad": 1.0,
        "family": family,
        "model_id": policy.scenario_model_id,
    }
    run = _run_tool(request, policy.scenario_run_id, parent_trace_id)
    ci_hi, horizon_used = _decisive_ci_hi(run, selector)
    processing = _processing(run.result, family, horizon_used, mapping)
    return ProbLossResult(
        value=ci_hi,
        violated=ci_hi > alpha + TOL,
        active=abs(ci_hi - alpha) <= TOL,
        processing=processing,
        source=run.source.model_copy(update={"processing": processing}),
        facts=[Fact.model_validate(fact) for fact in run.result["facts"]],
        traces=run.traces,
        warnings=_warnings(run.result, limit.rule_id, alpha),
    )


def evaluate_prob_loss(
    limit: Limit, weights: dict[str, float], policy: PolicySpec, parent_trace_id: str, catalog=None
) -> ProbLossResult:
    """Évalue une limite PROB_LOSS sur les poids détenus. Ne lève pas : un échec est « non vérifiable »."""
    try:
        return _evaluate(limit, weights, policy, parent_trace_id, catalog)
    except _UnverifiableError as exc:
        return _unverifiable(limit.rule_id, exc.reason, traces=exc.traces, source=exc.source)


# --------------------------------------------------------------------------- crochet F1 (non appelé)


def prob_loss_limit(rule_id: str, *, alpha: float, loss_level: float, horizon_years: int, **limit_fields: Any) -> Limit:
    """Aide pour F1 : une limite PROB_LOSS. α, L et H sont des ENTRÉES de F1 (profil, validées par l'équipe) ;
    aucune valeur par défaut. ``limit_fields`` : les autres champs de ``Limit`` (``derived_from`` requis,
    ``source``, ``blocking``, ``description_fr``). F1 n'émet pas encore PROB_LOSS : le Judge ne l'évalue que si une
    limite existe."""
    return Limit(
        rule_id=rule_id,
        kind="risk",
        max=alpha,
        selector=Selector(measure="PROB_LOSS", loss_level=loss_level, horizon_years=horizon_years),
        **limit_fields,
    )
