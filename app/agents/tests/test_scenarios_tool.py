"""Outil scenario_risk : lecture de la table, grille, seuils prudents, Facts/TraceEvent, explication, sans numpy.

TABLE DE TEST FICTIVE : toutes les valeurs ci-dessous sont inventées par une formule simple (FICTIF_*), sans
aucun lien avec un modèle ni des données réelles. Elles servent seulement à vérifier la mécanique de l'outil.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import textwrap

import pytest

from alphaforge.scenarios import tool_facts as tf
from alphaforge.scenarios.tool import (
    MAX_L1_DISTANCE,
    ScenarioRiskTool,
    compute_scenario_risk,
    make_scenario_risk_tool,
    normalize_weights,
)
from alphaforge.scenarios.tool_render import _interval, money, pct, prob, render_fr
from alphaforge.scenarios.tool_table import (
    LATEST_KEY,
    ScenarioTableError,
    ScenarioTableLoader,
    build_manifest,
    dumps_table,
    parse_mix_id,
    parse_table,
)
from alphaforge.store.local import LocalStore

RUN_ID = "fixture-run-1"
CODE_SHA = "fictif00"
DATA_SHA = {"CAD77": "d" * 64, "USD1926": "u" * 64}
MODELS = ("FICTIF_boot", "FICTIF_hmm")
MIXES = (
    "ca15-us25-bd45-cs10-gd05",
    "ca20-us40-bd30-cs05-gd05",
    "ca10-us10-bd60-cs20-gd00",
    "ca15-us30-bd40-cs05-gd05-cr05",
)
HORIZONS = (1, 3, 5, 10)
LEVELS = (5, 10, 15, 20, 25, 30, 35, 40, 45, 50)


def _risky(mix: str) -> float:
    w = parse_mix_id(mix)
    return w["CA_EQ"] + w["US_MKT"] + w["GOLD"] + 2 * w["CRYPTO"]


def fictive_rows(family: str = "CAD77", models: tuple[str, ...] = MODELS) -> list[dict]:
    """Valeurs FICTIVES : monotones en seuil, plus risquées avec plus d'actions; FICTIF_hmm un peu plus pessimiste."""
    rows = []
    for m_index, model in enumerate(models):
        bump = 1.0 + 0.25 * m_index
        for mix in MIXES:
            e = _risky(mix)
            for h in (*HORIZONS, 20) if models != MODELS else HORIZONS:
                values = {
                    "ret_ann_p05": -0.20 * e / h**0.5,
                    "ret_ann_p10": -0.12 * e / h**0.5,
                    "ret_ann_p50": 0.02 + 0.04 * e,
                    "ret_ann_p90": 0.04 + 0.10 * e,
                    "wealth_p10": max(0.3, 1 - 0.1 * e * h**0.5),
                    "mdd_p50": 0.10 * e,
                    "mdd_p90": 0.30 * e,
                    "cvar95_12m": 0.25 * e,
                }
                for lv in LEVELS:
                    values[f"p_loss_gt_{lv:02d}"] = min(0.9, bump * 0.4 * e * (1 - lv / 55) / (1 + 0.1 * h))
                for metric, v in values.items():
                    spread = 0.02 + abs(v) * 0.15
                    rows.append(
                        {
                            "schema_version": "0.2",
                            "model_id": model,
                            "family": family,
                            "currency": "CAD" if family.startswith("CAD") else "USD",
                            "mix_id": mix,
                            "horizon_years": h,
                            "basis": "nominal",
                            "metric": metric,
                            "value": round(v, 6),
                            "ci_lo": round(v - spread, 6),
                            "ci_hi": round(v + spread, 6),
                            "n_paths": 1000,
                            "n_boot": 50,
                            "seed": 42,
                            "fitted_through": "2026-10",
                            "window_start": "1977-01" if family == "CAD77" else "1926-07",
                            "n_hist_months": 598,
                            "hypothese": "cr" in mix,
                            "data_sha256": DATA_SHA[family],
                            "code_sha": CODE_SHA,
                        }
                    )
    return rows


def publish(store: LocalStore, rows: list[dict] | None = None, run_id: str = RUN_ID, **manifest_extra) -> bytes:
    body = dumps_table(rows if rows is not None else fictive_rows() + fictive_rows("USD1926"))
    manifest = build_manifest(
        run_id,
        body,
        code_sha=CODE_SHA,
        data_sha256=DATA_SHA,
        default_model="FICTIF_boot",
        models=[
            {"model_id": "FICTIF_boot", "name": "bootstrap fictif", "assumptions": ["Hypothèse fictive de test."]},
            {"model_id": "FICTIF_hmm", "name": "régimes fictifs"},
        ],
        **manifest_extra,
    )
    prefix = f"scenarios/output/{run_id}/"
    store.put(prefix + "table.csv", body, content_type="text/csv")
    store.put_json(prefix + "manifest.json", manifest)
    store.put_json(LATEST_KEY, {"run_id": run_id})
    return body


@pytest.fixture
def kb(tmp_path):
    store = LocalStore(tmp_path / "kb")
    publish(store)
    return store


@pytest.fixture
def table(kb):
    return ScenarioTableLoader(kb).load()


ON_GRID = {"CA_EQ": 0.15, "US_MKT": 0.25, "BONDS": 0.45, "CASH": 0.10, "GOLD": 0.05}
NO_GOLD = {"CA_EQ": 0.10, "US_MKT": 0.10, "BONDS": 0.60, "CASH": 0.20}  # MIXES[2], sans or ni crypto


# --------------------------------------------------------------------------- chargeur


def test_loader_reads_latest_verifies_and_caches(kb, table):
    assert table.run_id == RUN_ID and table.code_sha == CODE_SHA
    assert table.data_sha256("CAD77") == DATA_SHA["CAD77"]
    assert table.models == ["FICTIF_boot", "FICTIF_hmm"] and table.default_model == "FICTIF_boot"
    assert table.table_sha256 == table.source()["sha256"]
    loader = ScenarioTableLoader(kb)
    first = loader.load()
    kb.put(f"scenarios/output/{RUN_ID}/table.csv", b"corrupt", content_type="text/csv")
    assert loader.load() is first  # cache mémoire : pas de relecture
    with pytest.raises(ScenarioTableError, match="sha256"):
        ScenarioTableLoader(kb).load()


def _parse(run_id, manifest, key, body):
    return parse_table(run_id, manifest, key, body, expected_sha256=manifest["table"]["sha256"])


def test_parse_table_refuses_undeclared_sha256():
    body = dumps_table(fictive_rows()[:10])
    manifest = build_manifest("r", body, code_sha=CODE_SHA, data_sha256=DATA_SHA)
    with pytest.raises(ScenarioTableError, match="non déclaré"):
        parse_table("r", manifest, "t.csv", body)


def test_pinned_run_requires_done_marker_ok(tmp_path):
    store = LocalStore(tmp_path)
    publish(store)
    prefix = f"scenarios/output/{RUN_ID}/"
    with pytest.raises(ScenarioTableError, match="_done.json"):
        ScenarioTableLoader(store, run_id=RUN_ID).load()
    store.put_json(prefix + "_done.json", {"status": "error", "run_id": RUN_ID})
    with pytest.raises(ScenarioTableError, match="'error'"):
        ScenarioTableLoader(store, run_id=RUN_ID).load()
    store.put_json(prefix + "_done.json", {"status": "ok", "run_id": RUN_ID})
    assert ScenarioTableLoader(store, run_id=RUN_ID).load().run_id == RUN_ID


def test_loader_refuses_inconsistent_rows(tmp_path):
    store = LocalStore(tmp_path)
    rows = fictive_rows()
    rows[3]["code_sha"] = "autre"
    publish(store, rows)
    with pytest.raises(ScenarioTableError, match="code_sha"):
        ScenarioTableLoader(store).load()
    rows = fictive_rows()
    rows[0]["ci_hi"] = rows[0]["value"] - 1
    body = dumps_table(rows)
    with pytest.raises(ScenarioTableError, match="ci_lo > ci_hi"):
        _parse("r", build_manifest("r", body, code_sha=CODE_SHA, data_sha256=DATA_SHA), "t.csv", body)
    rows = fictive_rows()
    rows[0]["value"] = rows[0]["ci_hi"] + 0.01  # IC valide qui n'encadre pas la valeur : gardé, compté
    body = dumps_table(rows)
    kept = _parse("r", build_manifest("r", body, code_sha=CODE_SHA, data_sha256=DATA_SHA), "t.csv", body)
    assert kept.integrity["ci_not_enclosing"] == 1
    with pytest.raises(ScenarioTableError, match="pointeur"):
        ScenarioTableLoader(LocalStore(tmp_path / "vide")).load()


def test_loader_accepts_schema_01_without_basis():
    rows = [{k: v for k, v in r.items() if k not in ("basis", "currency", "hypothese")} for r in fictive_rows()[:30]]
    body = dumps_table(rows).replace(b",nominal,", b",,")
    table = _parse(
        "r", build_manifest("r", body, code_sha=CODE_SHA, data_sha256=DATA_SHA, schema_version="0.1"), "t.csv", body
    )
    assert {k[4] for k in table.rows} == {"nominal"}


# --------------------------------------------------------------------------- entrées et grille


def test_weights_normalization():
    w, flags = normalize_weights({"ca": 15, "us": 25, "bonds": 45, "CASH": 10, "GOLD": 5})
    assert w["CA_EQ"] == pytest.approx(0.15) and "poids lus en pourcentages" in flags
    w, flags = normalize_weights({"CA_EQ": 0.16, "US_MKT": 0.25, "BONDS": 0.45, "CASH": 0.10, "GOLD": 0.05})
    assert sum(w.values()) == pytest.approx(1.0) and any("renormalisés" in f for f in flags)


@pytest.mark.parametrize(
    "weights",
    [{"CA_EQ": 0.5, "US_MKT": 0.3}, {"NVDA": 1.0}, {"CA_EQ": -0.1, "US_MKT": 1.1}, {}],
)
def test_bad_weights_are_refused(table, weights):
    result = compute_scenario_risk(table, weights, 5)
    assert result["status"] == "refus" and result["error"]["code"] == "bad_weights"
    assert result["facts"] == [] and result["trace_event"]["status"] == "refus"


def test_snaps_to_nearest_grid_mix_and_reports_l1(table):
    exact = compute_scenario_risk(table, ON_GRID, 5)
    assert exact["status"] == "ok" and exact["grid"]["mix_id"] == MIXES[0] and exact["grid"]["l1_distance"] == 0
    near = compute_scenario_risk(table, {"CA_EQ": 0.17, "US_MKT": 0.25, "BONDS": 0.43, "CASH": 0.10, "GOLD": 0.05}, 5)
    assert near["grid"]["mix_id"] == MIXES[0]
    assert near["grid"]["l1_distance"] == pytest.approx(0.04)
    l1_fact = next(f for f in near["facts"] if f["fact_id"] == near["grid"]["l1_fact_id"])
    assert l1_fact["value"] == pytest.approx(0.04)


def test_refuses_out_of_grid_mix(table):
    result = compute_scenario_risk(table, {"CA_EQ": 0.0, "US_MKT": 1.0}, 5)
    assert result["status"] == "refus" and result["error"]["code"] == "out_of_grid"
    assert result["error"]["details"]["l1_distance"] > MAX_L1_DISTANCE
    assert "extrapolation" in result["error"]["message"]
    assert result["facts"] == []


def test_horizon_exact_lower_with_flag_or_refused(table):
    approx = compute_scenario_risk(table, ON_GRID, 4, loss_threshold_cad=20000, amount_cad=100000)
    assert approx["horizon"] == {"requested": 4, "used": 3, "exact": False, "upper": 5, "available": [1, 3, 5, 10]}
    assert approx["upper_horizon"]["horizon_years"] == 5
    assert any("Horizon 4 ans absent" in s["text_fr"] for s in approx["explanation"]["limits"])
    for bad in (0, 11, 2.5, True):
        result = compute_scenario_risk(table, ON_GRID, bad)
        assert result["status"] == "refus", bad


# --------------------------------------------------------------------------- seuil de perte


def _ploss(table, level, horizon=5, model="FICTIF_boot", mix=MIXES[0]):
    return table.rows[(model, "CAD77", mix, horizon, "nominal", f"p_loss_gt_{level:02d}")].value


def test_threshold_rounded_down_so_probability_not_understated(table):
    result = compute_scenario_risk(table, ON_GRID, 5, loss_threshold_cad=17600, amount_cad=100000)
    thr = result["threshold"]
    assert thr["bucket_metric"] == "p_loss_gt_15" and thr["requested_pct"] == pytest.approx(0.176)
    assert thr["bucket_cad"] == pytest.approx(15000) and not thr["exact"] and not thr["is_lower_bound"]
    shown = result["primary"]["p_loss_gt_15"]["value"]
    assert shown == _ploss(table, 15) >= _ploss(table, 20)  # majorant de P(perte > 17,6 %)
    assert set(result["primary"]) >= {"p_loss_gt_10", "p_loss_gt_15", "p_loss_gt_20"}  # palier et voisins
    assert "majorant" in result["explanation"]["headline"]


def test_threshold_exact_and_lower_bound(table):
    exact = compute_scenario_risk(table, ON_GRID, 5, loss_threshold_cad=20000, amount_cad=100000)
    assert exact["threshold"]["bucket_metric"] == "p_loss_gt_20" and exact["threshold"]["exact"]
    tiny = compute_scenario_risk(table, ON_GRID, 5, loss_threshold_cad=3000, amount_cad=100000)
    assert tiny["threshold"]["bucket_metric"] == "p_loss_gt_05" and tiny["threshold"]["is_lower_bound"]
    assert "au moins" in tiny["explanation"]["headline"]


@pytest.mark.parametrize("threshold,amount", [(20000, None), (200000, 100000), (-5, 100000), (1000, 0)])
def test_bad_threshold_refused(table, threshold, amount):
    result = compute_scenario_risk(table, ON_GRID, 5, loss_threshold_cad=threshold, amount_cad=amount)
    assert result["status"] == "refus" and result["error"]["code"] == "bad_threshold"


# --------------------------------------------------------------------------- modèles, Facts, trace


def test_all_models_side_by_side(table):
    result = compute_scenario_risk(table, ON_GRID, 5, loss_threshold_cad=20000, amount_cad=100000)
    assert [m["model_id"] for m in result["all_models"]] == list(MODELS)
    values = {m["model_id"]: m["metrics"]["p_loss_gt_20"]["value"] for m in result["all_models"]}
    assert values["FICTIF_hmm"] > values["FICTIF_boot"]
    spread = result["model_spread"]["p_loss_gt_20"]
    assert spread["min_model"] == "FICTIF_boot" and spread["max_model"] == "FICTIF_hmm"
    assert any("FICTIF_hmm" in s["text_fr"] for s in result["explanation"]["what_would_change"])
    other = compute_scenario_risk(table, ON_GRID, 5, model_id="FICTIF_hmm")
    assert other["model_id"] == "FICTIF_hmm"
    assert compute_scenario_risk(table, ON_GRID, 5, model_id="absent")["status"] == "refus"
    assert compute_scenario_risk(table, ON_GRID, 5, family="CAD71")["status"] == "refus"


def test_facts_and_trace_match_decision_contract(table):
    result = compute_scenario_risk(table, ON_GRID, 5, loss_threshold_cad=20000, amount_cad=100000)
    facts = result["facts"]
    ids = [f["fact_id"] for f in facts]
    assert len(ids) == len(set(ids))
    for fact in facts:
        assert tuple(fact) == tf.CONTRACT_FACT_KEYS
        assert fact["status"] in ("FAIT", "HYPOTHESE") and fact["sources"] and fact["trace_id"]
        assert set(fact["sources"][0]) == {"dataset", "url", "licence", "retrieved_utc", "sha256", "processing"}
    head = next(f for f in facts if f["fact_id"].endswith("p_loss_gt_20"))
    assert head["as_of"] == "2026-10-31" and head["currency"] == "CAD" and head["status"] == "FAIT"
    assert head["sources"][0]["dataset"] == f"scenarios:{RUN_ID}" and head["sources"][0]["sha256"] == table.table_sha256
    event = result["trace_event"]
    assert tuple(event) == tf.CONTRACT_TRACE_KEYS
    assert event["tool"] == "scenario_risk" and event["status"] == "ok" and event["model_id"] is None
    assert event["data_version"] == DATA_SHA["CAD77"] and event["code_version"] == CODE_SHA and event["seed"] == 42
    assert set(event["fact_ids"]) == set(ids) and all(f["trace_id"] == event["trace_id"] for f in facts)
    # Fidélité : toute phrase ne cite que des Facts existants, et porte un label du contrat.
    for statement in result["explanation_facts"]:
        assert set(statement["fact_ids"]) <= set(ids)
        assert statement["label"] in ("FAIT", "HYPOTHESE", "FICTION")
    assert result["fitted_through"] == "2026-10" and result["data_sha256"] == DATA_SHA["CAD77"]


def test_crypto_mix_is_hypothese(table):
    result = compute_scenario_risk(table, {"ca": 15, "us": 30, "bd": 40, "cs": 5, "gd": 5, "cr": 5}, 5)
    assert result["hypothese"] and all(
        f["status"] == "HYPOTHESE" for f in result["facts"] if f["fact_id"].startswith(f"scn.{MODELS[0]}")
    )
    assert any("crypto" in s["text_fr"] for s in result["explanation"]["limits"])
    assert result["validated"] is False and any("CRYPTO" in r for r in result["validation_reasons"])


def _load_contracts():
    """Le vrai contrat pydantic (alphaforge.finance.contracts.decision); saute si pydantic n'est pas installé
    (CI : uv sync --frozen sans le groupe finance)."""
    pytest.importorskip("pydantic")
    decision = pytest.importorskip("alphaforge.finance.contracts.decision")
    return vars(decision)


def test_facts_validate_against_real_contract_when_available(table):
    contracts = _load_contracts()
    result = compute_scenario_risk(table, ON_GRID, 4, loss_threshold_cad=17600, amount_cad=100000)
    for fact in result["facts"]:
        contracts["Fact"].model_validate(fact)
    contracts["TraceEvent"].model_validate(result["trace_event"])
    explanation = {
        k: [contracts["Statement"].model_validate(s) for s in result["explanation"][k]]
        for k in ("data_used", "why", "limits", "what_would_change")
    }
    contracts["Explanation"].model_validate(explanation)


# --------------------------------------------------------------------------- explication et outil Strands


def test_render_fr_four_questions(table):
    result = compute_scenario_risk(table, ON_GRID, 5, loss_threshold_cad=20000, amount_cad=100000)
    out = render_fr(result)
    assert set(out) >= {"data_used", "why", "limits", "what_would_change", "headline", "text"}
    head = out["headline"]
    assert head.startswith("Selon le modèle bootstrap fictif (données 1977–2026, CAD)")
    assert "IC 90 %" in head and "20 000 $" in head and "sur 5 ans" in head
    assert "c'est un modèle, pas une prévision" in head
    assert all(out[k] for k in ("data_used", "why", "limits", "what_would_change"))
    assert "Hypothèse fictive de test." in out["text"] and "ni un conseil" in out["text"]
    assert pct(0.123) == "12 %" and pct(0.042) == "4,2 %" and money(20000) == "20 000 $"
    refused = render_fr(compute_scenario_risk(table, {"US_MKT": 1}, 5))
    assert refused["headline"].startswith("Aucun chiffre produit")


def test_probability_rounding_never_understates():
    # Arrondi au plus proche pour les autres métriques, vers le haut / le bas pour les probabilités.
    assert pct(0.1249) == "12 %" and pct(0.1249, "up") == "13 %" and pct(0.1249, "down") == "12 %"
    assert pct(0.0401, "up") == "4,1 %" and pct(0.0409, "down") == "4 %" and pct(0.125, "up") == "13 %"
    assert pct(0.12, "up") == "12 %" and pct(0.0996, "up") == "10 %" and pct(0.043, "up") == "4,3 %"
    # Probabilité nulle : aucune trajectoire sur n, donc « < 1/n ».
    assert prob(0.0, 2000) == "< 0,05 %" and prob(0.0, 500) == "< 0,2 %" and prob(0.0, 3000) == "< 0,034 %"
    assert prob(0.0, 2000, "down") == "0 %" and prob(0.0, None) == "0 %"
    view = {"value": 0.0, "ci_lo": 0.0, "ci_hi": 0.0041, "n_paths": 2000}
    assert _interval(view, "p_loss_gt_20") == "< 0,05 % [IC 90 % : 0 %–0,5 %]"
    assert _interval(dict(view, ci_hi=0.0), "p_loss_gt_20") == "< 0,05 % [IC 90 % : 0 %–0,05 %]"
    view = {"value": 0.1249, "ci_lo": 0.1049, "ci_hi": 0.1401, "n_paths": 2000}
    assert _interval(view, "p_mdd_gt_20") == "13 % [IC 90 % : 10 %–15 %]"
    assert _interval(view, "ret_ann_p10") == "12 % [IC 90 % : 10 %–14 %]"


def test_strands_tool_and_ledger(kb):
    owner = make_scenario_risk_tool(kb)
    scenario_risk = owner.tool()
    spec = scenario_risk.tool_spec
    assert spec["name"] == "scenario_risk" and "NOT a forecast" in spec["description"]
    payload = json.loads(scenario_risk(weights=ON_GRID, horizon_years=5, loss_threshold_cad=20000, amount_cad=100000))
    assert payload["status"] == "ok" and "facts" not in payload and payload["run_id"] == RUN_ID
    assert payload["primary"]["p_loss_gt_20"]["fact_id"].startswith("scn.FICTIF_boot.CAD77.")
    assert owner.facts() and owner.trace_events()[0]["trace_id"] == payload["trace_id"]


def test_tool_refuses_cleanly_without_table(tmp_path):
    owner = ScenarioRiskTool(ScenarioTableLoader(LocalStore(tmp_path)))
    result = owner.run(weights=ON_GRID, horizon_years=5)
    assert result["status"] == "refus" and result["error"]["code"] == "table_unavailable"
    assert result["trace_event"]["status"] == "refus"


def test_runtime_path_imports_no_heavy_dependency(kb, tmp_path):
    script = textwrap.dedent(
        f"""
        import json, sys
        from alphaforge.store.local import LocalStore
        from alphaforge.scenarios.tool import make_scenario_risk_tool
        owner = make_scenario_risk_tool(LocalStore({str(kb.root)!r}))
        out = json.loads(owner.tool()(weights={json.dumps(ON_GRID)}, horizon_years=5,
                                      loss_threshold_cad=20000, amount_cad=100000))
        assert out["status"] == "ok", out
        heavy = sorted(m for m in ("numpy", "pandas", "pyarrow", "scipy", "sklearn") if m in sys.modules)
        print(json.dumps(heavy))
        """
    )
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout.strip().splitlines()[-1]) == []


# --------------------------------------------------------------------------- format du job (runtime JSON)


def runtime_doc(rows: list[dict]) -> dict:
    """Même disposition que job._runtime_outputs (valeurs FICTIVES de fictive_rows)."""
    tables: dict = {}
    for r in rows:
        key = f"{r['model_id']}|{r['family']}{'+CRYPTO' if r['hypothese'] else ''}"
        sub = tables.setdefault(
            key,
            {
                "model_id": r["model_id"],
                "family": r["family"],
                "currency": r["currency"],
                "hypothese": r["hypothese"],
                "window_start": r["window_start"],
                "fitted_through": r["fitted_through"],
                "n_hist_months": r["n_hist_months"],
                "n_paths": r["n_paths"],
                "n_boot": r["n_boot"],
                "seed": r["seed"],
                "mixes": {},
            },
        )
        cell = (
            sub["mixes"].setdefault(r["mix_id"], {}).setdefault(r["basis"], {}).setdefault(str(r["horizon_years"]), {})
        )
        cell[r["metric"]] = [r["value"], r["ci_lo"], r["ci_hi"]]
    return {
        "schema_version": "0.2",
        "data_sha256": DATA_SHA["CAD77"],
        "code_sha": CODE_SHA,
        "value_order": ["value", "ci_lo", "ci_hi"],
        "tables": tables,
    }


def publish_runtime(store: LocalStore, doc: dict | None = None, *, declare_sha: bool = True, sha: str | None = None):
    body = json.dumps(doc or runtime_doc(fictive_rows()), separators=(",", ":")).encode()
    path = "runtime/scenarios_runtime.json"
    manifest = {
        "schema_version": "0.2",
        "data_sha256": DATA_SHA["CAD77"],
        "code_sha": CODE_SHA,
        "generated_utc": "2026-11-14T20:00:00Z",
        "config": {"models": ["FICTIF_boot", "FICTIF_hmm"], "runtime": {"models": ["FICTIF_boot", "FICTIF_hmm"]}},
        "outputs": {"runtime_json": path, "table": "table/scenarios.parquet"},
    }
    if declare_sha:
        manifest["outputs_sha256"] = {path: sha or hashlib.sha256(body).hexdigest()}
    prefix = f"scenarios/output/{RUN_ID}/"
    store.put(prefix + path, body, content_type="application/json")
    store.put_json(prefix + "manifest.json", manifest)
    store.put_json(LATEST_KEY, {"run_id": RUN_ID, "manifest": prefix + "manifest.json"})


def test_loader_reads_job_runtime_json_same_numbers_as_csv(tmp_path, table):
    store = LocalStore(tmp_path / "job")
    publish_runtime(store)
    rt = ScenarioTableLoader(store).load()
    assert rt.integrity["format"] == "runtime_json" and rt.integrity["file_sha256_verified"]
    assert rt.warnings == [
        "manifest.table absent : repli sur manifest.outputs.runtime_json = runtime/scenarios_runtime.json"
    ]
    assert rt.models == ["FICTIF_boot", "FICTIF_hmm"] and rt.default_model == "FICTIF_boot"
    a = compute_scenario_risk(rt, ON_GRID, 5, loss_threshold_cad=20000, amount_cad=100000)
    b = compute_scenario_risk(table, ON_GRID, 5, loss_threshold_cad=20000, amount_cad=100000)
    assert a["primary"] == b["primary"] and a["fitted_through"] == "2026-10"
    assert a["trace_event"]["code_version"] == CODE_SHA and a["data_sha256"] == DATA_SHA["CAD77"]
    crypto = compute_scenario_risk(rt, {"ca": 15, "us": 30, "bd": 40, "cs": 5, "gd": 5, "cr": 5}, 5)
    assert crypto["status"] == "ok" and crypto["hypothese"]


def test_runtime_json_integrity_checks(tmp_path):
    store = LocalStore(tmp_path / "bad")
    publish_runtime(store, sha="0" * 64)
    with pytest.raises(ScenarioTableError, match="sha256"):
        ScenarioTableLoader(store).load()
    doc = runtime_doc(fictive_rows())
    doc["code_sha"] = "autre"
    publish_runtime(store, doc)
    with pytest.raises(ScenarioTableError, match="code_sha"):
        ScenarioTableLoader(store).load()


def test_runtime_json_without_declared_sha_is_refused(tmp_path):
    store = LocalStore(tmp_path / "nosha")
    publish_runtime(store, declare_sha=False)
    with pytest.raises(ScenarioTableError, match="non déclaré"):
        ScenarioTableLoader(store).load()


def test_runtime_json_nan_is_dropped_and_flagged(tmp_path):
    store = LocalStore(tmp_path / "nan")
    doc = runtime_doc(fictive_rows())
    first = next(iter(doc["tables"].values()))
    first["mixes"][MIXES[1]]["nominal"]["5"]["cvar95_12m"] = [None, None, None]  # NaN du job
    publish_runtime(store, doc)
    rt = ScenarioTableLoader(store).load()
    assert rt.integrity["file_sha256_verified"] is True and any("NaN" in w for w in rt.warnings)


JOB_CSV_COLUMNS = ("model_id", "family", "mix_id", "horizon_years", "basis", "metric", "value", "ci_lo", "ci_hi")


def test_agreed_format_manifest_table_runtime_csv(tmp_path):
    """Format convenu avec le job : manifest.table -> runtime/scenarios_runtime.csv (colonnes compactes du job)."""
    store = LocalStore(tmp_path / "agreed")
    lines = [",".join(JOB_CSV_COLUMNS)] + [",".join(str(r[c]) for c in JOB_CSV_COLUMNS) for r in fictive_rows()]
    body = ("\n".join(lines) + "\n").encode()
    prefix = f"scenarios/output/{RUN_ID}/"
    store.put(prefix + "runtime/scenarios_runtime.csv", body, content_type="text/csv")
    manifest = {
        "schema_version": "0.2",
        "data_sha256": DATA_SHA["CAD77"],
        "code_sha": CODE_SHA,
        "seed": 7,
        "config": {"fitted_through": "2026-09", "simulation": {"n_paths": 2000}, "models": list(MODELS)},
        "table": {"file": "runtime/scenarios_runtime.csv", "format": "csv", "sha256": hashlib.sha256(body).hexdigest()},
        "outputs": {"table": "table/scenarios.parquet"},
    }
    store.put_json(prefix + "manifest.json", manifest)
    store.put_json(LATEST_KEY, {"run_id": RUN_ID, "release": CODE_SHA})
    rt = ScenarioTableLoader(store).load()
    assert rt.table_key == prefix + "runtime/scenarios_runtime.csv" and rt.integrity["format"] == "csv"
    assert rt.integrity["row_provenance"] is False and rt.integrity["file_sha256_verified"] is True
    result = compute_scenario_risk(rt, ON_GRID, 5, loss_threshold_cad=20000, amount_cad=100000)
    assert result["status"] == "ok" and result["n_paths"] == 2000 and result["seed"] == 7
    assert result["fitted_through"] == "2026-09" and result["code_sha"] == CODE_SHA
    assert result["primary"]["p_loss_gt_20"]["value"] == pytest.approx(_ploss_rows(20))
    # sha256 déclaré et faux : refus
    manifest["table"]["sha256"] = "0" * 64
    store.put_json(prefix + "manifest.json", manifest)
    with pytest.raises(ScenarioTableError, match="sha256"):
        ScenarioTableLoader(store).load()


def _ploss_rows(level: int) -> float:
    return next(
        r["value"]
        for r in fictive_rows()
        if r["model_id"] == "FICTIF_boot"
        and r["mix_id"] == MIXES[0]
        and r["horizon_years"] == 5
        and r["metric"] == f"p_loss_gt_{level:02d}"
    )


def test_manifest_without_table_is_a_clear_error(tmp_path):
    store = LocalStore(tmp_path / "notable")
    prefix = f"scenarios/output/{RUN_ID}/"
    store.put_json(prefix + "manifest.json", {"schema_version": "0.2", "data_sha256": "x", "code_sha": "y"})
    store.put_json(LATEST_KEY, {"run_id": RUN_ID})
    with pytest.raises(ScenarioTableError, match='manifeste sans "table"'):
        ScenarioTableLoader(store).load()
    store.put_json(
        prefix + "manifest.json",
        {"schema_version": "0.2", "data_sha256": "x", "code_sha": "y", "table": {"file": "table/scenarios.parquet"}},
    )
    with pytest.raises(ScenarioTableError, match="format de table"):
        ScenarioTableLoader(store).load()
    store.put_json(
        prefix + "manifest.json",
        {"schema_version": "0.2", "data_sha256": "x", "code_sha": "y", "table": {"file": "../secret.csv"}},
    )
    with pytest.raises(ScenarioTableError, match="chemin"):
        ScenarioTableLoader(store).load()


# --------------------------------------------------------------------------- affichage et validation (volet C)

JOB_MODELS = ("sbb_ca", "sbb", "hmm_rs", "iid")


def display_table(tmp_path, *, display: bool = True, validation: bool = True):
    rows = []
    for basis in ("nominal", "real"):
        for r in fictive_rows(models=JOB_MODELS):
            rows.append({**r, "basis": basis})
    body = dumps_table(rows)
    models = []
    for model, role in zip(JOB_MODELS, ("default", "compare", "sensitivity_only", "hidden"), strict=True):
        entry = {"model_id": model}
        if display:
            entry["display"] = role
        if validation:
            entry["validation"] = f"FICTIF : couverture p10-p90 de {model} sur 1-10 ans."
        models.append(entry)
    manifest = build_manifest(RUN_ID, body, code_sha=CODE_SHA, data_sha256=DATA_SHA, models=models)
    if display:
        manifest["validated_horizons"] = [1, 3, 5, 10]
    store = LocalStore(tmp_path / ("disp" if display else "nodisp"))
    prefix = f"scenarios/output/{RUN_ID}/"
    store.put(prefix + "table.csv", body, content_type="text/csv")
    store.put_json(prefix + "manifest.json", manifest)
    store.put_json(LATEST_KEY, {"run_id": RUN_ID})
    return ScenarioTableLoader(store).load()


def test_display_default_and_compare_only(tmp_path):
    t = display_table(tmp_path)
    assert t.default_model == "sbb_ca"
    result = compute_scenario_risk(t, ON_GRID, 3, loss_threshold_cad=20000, amount_cad=100000)
    assert result["model_id"] == "sbb_ca"
    assert [m["model_id"] for m in result["all_models"]] == ["sbb_ca", "sbb"]
    assert not any("hmm_rs" in f["fact_id"] or ".iid." in f["fact_id"] for f in result["facts"])
    sens = compute_scenario_risk(t, ON_GRID, 3, include_sensitivity=True)
    assert [m["model_id"] for m in sens["all_models"]] == ["sbb_ca", "sbb", "hmm_rs"]
    refused = compute_scenario_risk(t, ON_GRID, 3, model_id="hmm_rs")
    assert refused["status"] == "refus" and refused["error"]["code"] == "sensitivity_only"
    explicit = compute_scenario_risk(t, ON_GRID, 3, model_id="hmm_rs", include_sensitivity=True)
    assert explicit["status"] == "ok" and explicit["model_id"] == "hmm_rs"
    assert [m["model_id"] for m in explicit["all_models"]] == ["sbb_ca", "sbb", "hmm_rs"]
    hidden = compute_scenario_risk(t, ON_GRID, 3, model_id="iid")
    assert hidden["status"] == "refus" and "masqué" in hidden["error"]["message"]
    assert all(
        m["model_id"] != "iid" for m in compute_scenario_risk(t, ON_GRID, 3, include_sensitivity=True)["all_models"]
    )


def test_display_fallback_without_manifest_field(tmp_path):
    t = display_table(tmp_path, display=False)
    assert t.default_model == "sbb_ca"
    assert [t.display(m) for m in JOB_MODELS] == ["default", "compare", "sensitivity_only", "hidden"]
    result = compute_scenario_risk(t, NO_GOLD, 3)
    assert [m["model_id"] for m in result["all_models"]] == ["sbb_ca", "sbb"]
    assert result["validated_horizons_declared"] is False and result["validated"] is True


def test_validated_flags_and_limits(tmp_path):
    t = display_table(tmp_path)
    short = compute_scenario_risk(t, NO_GOLD, 3)
    assert short["validated"] is True and short["degraded_calibration"] is False
    limits = short["explanation"]["limits"]
    texts = [s["text_fr"] for s in limits]
    assert any("hausses de taux testées" in s["text_fr"] and s["label"] == "FAIT" for s in limits)
    assert any("pourrait donc être plus grande" in s["text_fr"] and s["label"] == "HYPOTHESE" for s in limits)
    assert any("FICTIF : couverture p10-p90 de sbb_ca sur 1-10 ans." in x for x in texts)
    assert any("FICTIF : couverture p10-p90 de sbb sur 1-10 ans." in x for x in texts)
    for horizon in (5, 10):
        r = compute_scenario_risk(t, NO_GOLD, horizon)
        assert r["validated"] is True and r["degraded_calibration"] is True
        assert any("calibration dégradée à long horizon" in s["text_fr"] for s in r["explanation"]["limits"])
    long = compute_scenario_risk(t, NO_GOLD, 20)
    assert long["status"] == "ok" and long["validated"] is False and not long["degraded_calibration"]
    assert any("non validé hors échantillon" in s["text_fr"] for s in long["explanation"]["limits"])
    real = compute_scenario_risk(t, NO_GOLD, 3, basis="real")
    assert real["validated"] is False and "base real non validée" in real["validation_reasons"]
    assert "non validé hors échantillon" in real["explanation"]["text"]
    # Or ou crypto : blocs jamais testés hors échantillon, même à un horizon validé en base nominale.
    gold = compute_scenario_risk(t, ON_GRID, 3)
    assert gold["validated"] is False and not gold["degraded_calibration"]
    assert any("GOLD" in r and "non testés" in r for r in gold["validation_reasons"])


def test_tool_exposes_include_sensitivity_and_validated(tmp_path, kb):
    owner = make_scenario_risk_tool(kb)
    spec = owner.tool().tool_spec
    assert "include_sensitivity" in spec["inputSchema"]["json"]["properties"]
    payload = json.loads(owner.tool()(weights=NO_GOLD, horizon_years=3))
    assert payload["validated"] is True and "degraded_calibration" in payload
