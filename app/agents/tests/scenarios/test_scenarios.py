"""Tests du volet B : déterminisme, schéma, absence de look-ahead, cohérence des métriques, bootstrap."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")

from alphaforge.scenarios import schema  # noqa: E402
from alphaforge.scenarios.bootstrap import politis_white, stationary_indices  # noqa: E402
from alphaforge.scenarios.data import build_pool  # noqa: E402
from alphaforge.scenarios.engine import SimulationConfig, historical_reference, run_pool, simulate_metrics  # noqa: E402
from alphaforge.scenarios.grid import enumerate_mixes  # noqa: E402
from alphaforge.scenarios.models import fit, make_model, rng_for  # noqa: E402

CASH = "ca00-us00-bd00-cs100-gd00"
EQ100 = "ca50-us50-bd00-cs00-gd00"
B6040 = "ca30-us30-bd40-cs00-gd00"
BONDS = "ca00-us00-bd100-cs00-gd00"
MIXES = [CASH, EQ100, B6040, BONDS]
H = [1, 5, 10]


def metric(vals, name, h, mix):
    return vals[schema.METRICS.index(name), H.index(h), MIXES.index(mix)]


# --- schéma et identifiants ----------------------------------------------------------------------------------


def test_mix_id_roundtrip_and_validation():
    w = {"CA_EQ": 0.15, "US_MKT": 0.25, "BONDS": 0.45, "CASH": 0.10, "GOLD": 0.05}
    assert schema.mix_id(w) == "ca15-us25-bd45-cs10-gd05"
    assert schema.parse_mix_id("ca15-us25-bd45-cs10-gd05")["BONDS"] == pytest.approx(0.45)
    assert schema.mix_id({"US_MKT": 1.0}) == "ca00-us100-bd00-cs00-gd00"
    assert schema.mix_id({"US_MKT": 0.9, "CRYPTO": 0.1}).endswith("-cr10")
    with pytest.raises(ValueError):
        schema.mix_id({"US_MKT": 0.93, "BONDS": 0.07})
    with pytest.raises(ValueError):
        schema.mix_id({"US_MKT": 0.5})
    best, dist = schema.nearest_mix({"US_MKT": 0.62, "BONDS": 0.38}, ["ca00-us60-bd40-cs00-gd00", CASH])
    assert best == "ca00-us60-bd40-cs00-gd00" and dist == pytest.approx(0.04)


def test_grid_enumeration_sums_to_100():
    ids = enumerate_mixes(
        ["US_MKT", "BONDS", "CASH"],
        {"US_MKT": {"min": 0, "max": 100, "step": 25}, "BONDS": {"min": 0, "max": 100, "step": 25}},
        anchors=[{"CASH": 100}, {"CA_EQ": 50, "US_MKT": 50}],  # la seconde ancre utilise un bloc absent
    )
    assert len(ids) == 5 + 1
    assert all(abs(sum(schema.parse_mix_id(i).values()) - 1) < 1e-12 for i in ids)
    assert "ca50-us50-bd00-cs00-gd00" not in ids


# --- données ------------------------------------------------------------------------------------------------


def test_pools_windows_and_flags(inputs):
    p77 = build_pool(inputs, "CAD77")
    assert p77.window_start == "1977-01" and p77.blocks == ("CA_EQ", "US_MKT", "BONDS", "CASH", "GOLD")
    assert p77.flag_counts["CASH"]["proxy_interbank_rate"] > 0
    pc = build_pool(inputs, "CAD77", crypto=True)
    assert pc.window_start == "2014-10" and pc.hypothese and "CRYPTO" in pc.blocks
    pu = build_pool(inputs, "USD1926")
    assert pu.blocks == ("US_MKT", "BONDS", "CASH") and pu.currency == "USD"
    assert not np.isnan(p77.returns).any() and len(p77.inflation) == p77.n


def test_interior_gap_is_an_error(inputs):
    from alphaforge.scenarios.data import Inputs

    df = inputs.returns
    gap = df[~((df.asset_id == "CA_TBILL") & (df.date == pd.Timestamp("1990-06-30")))]
    broken = Inputs(gap, inputs.inflation, inputs.data_sha256, {}, {}, "x")
    with pytest.raises(ValueError, match="calendrier|manquants"):
        build_pool(broken, "CAD77")


# --- bootstrap ------------------------------------------------------------------------------------------------


def test_stationary_indices_block_structure():
    rng = np.random.default_rng(0)
    idx = stationary_indices(500, 2000, 120, 6.0, rng)
    assert idx.shape == (2000, 120) and idx.min() >= 0 and idx.max() < 500
    cont = (np.diff(idx, axis=1) % 500 == 1).mean()  # proportion de mois qui prolongent le bloc
    assert cont == pytest.approx(1 - 1 / 6, abs=0.02)
    iid = stationary_indices(500, 2000, 120, 1.0, np.random.default_rng(0))
    assert (np.diff(iid, axis=1) % 500 == 1).mean() < 0.01


def test_bootstrap_preserves_marginal_mean_and_correlation(pool77):
    rng = np.random.default_rng(1)
    idx = stationary_indices(pool77.n, 4000, 240, 6.0, rng)
    sim = pool77.returns[idx]  # (N, T, A)
    hist_mean = pool77.returns.mean(axis=0)
    sim_mean = sim.reshape(-1, pool77.returns.shape[1]).mean(axis=0)
    assert np.allclose(sim_mean, hist_mean, atol=3 * pool77.returns.std(axis=0) / np.sqrt(4000 * 240 / 6))
    c_hist = np.corrcoef(pool77.returns[:, 0], pool77.returns[:, 1])[0, 1]
    flat = sim.reshape(-1, pool77.returns.shape[1])
    assert np.corrcoef(flat[:, 0], flat[:, 1])[0, 1] == pytest.approx(c_hist, abs=0.03)


def test_politis_white_detects_dependence():
    rng = np.random.default_rng(2)
    white = rng.normal(size=1000)
    ar = np.empty(1000)
    ar[0] = 0
    for t in range(1, 1000):
        ar[t] = 0.8 * ar[t - 1] + rng.normal()
    assert politis_white(white) < 3
    assert politis_white(ar) > 2 * politis_white(white)


# --- déterminisme ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("model_id", ["sbb", "hmm_rs", "sbb_ca"])
def test_determinism_with_seed(pool77, model_id):
    model = make_model(model_id, {"n_init": 2} if model_id.startswith("hmm") else None)
    kw = dict(seed=7, n_paths=300, n_boot=3, n_paths_boot=100)
    a = run_pool(model, pool77, MIXES, H, SimulationConfig(**kw))
    twin = make_model(model_id, {"n_init": 2} if model_id.startswith("hmm") else None)
    b = run_pool(twin, pool77, MIXES, H, SimulationConfig(**kw))
    for basis in ("nominal", "real"):
        assert np.array_equal(a.point[basis], b.point[basis])
        assert np.array_equal(a.ci_lo[basis], b.ci_lo[basis])
    c = run_pool(model, pool77, MIXES, H, SimulationConfig(**{**kw, "seed": 8}))
    assert not np.array_equal(a.point["nominal"], c.point["nominal"])


# --- absence de look-ahead -------------------------------------------------------------------------------------


@pytest.mark.parametrize("model_id", ["sbb", "hmm_rs", "sbb_ca", "hmm_rs_ca"])
def test_no_look_ahead(pool77, model_id):
    """Changer (même violemment) les mois postérieurs à ``fitted_through`` ne change rien à l'ajustement ni aux
    trajectoires simulées, et aucun mois postérieur ne peut être tiré."""
    cut = "2000-12"
    params = {"n_init": 2} if model_id.startswith("hmm") else None
    f1 = fit(pool77, model_id, fitted_through=cut, seed=3, params=params)
    corrupted = pool77._subset(np.arange(pool77.n))
    after = np.asarray(corrupted.dates > pd.Timestamp("2000-12-31"))
    corrupted.returns[after] = np.random.default_rng(9).normal(0.0, 0.5, size=corrupted.returns[after].shape)
    corrupted.inflation[after] = 0.5
    f2 = fit(corrupted, model_id, fitted_through=cut, seed=3, params=params)
    assert f1.fitted_through == f2.fitted_through == cut
    assert f1.pool.n == int((~after).sum())
    assert json.dumps(f1.info, sort_keys=True, default=str) == json.dumps(f2.info, sort_keys=True, default=str)
    i1 = f1.simulate_indices(200, 120, rng_for(1, "x"))
    i2 = f2.simulate_indices(200, 120, rng_for(1, "x"))
    assert np.array_equal(i1, i2) and i1.max() < f1.pool.n
    m1 = simulate_metrics(f1, MIXES, H, 200, rng_for(1, "y"))
    m2 = simulate_metrics(f2, MIXES, H, 200, rng_for(1, "y"))
    assert np.array_equal(m1["nominal"], m2["nominal"]) and np.array_equal(m1["real"], m2["real"])


# --- cohérence des métriques ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sbb_result(pool77):
    config = SimulationConfig(seed=11, n_paths=3000, n_boot=8, n_paths_boot=300)
    return run_pool(make_model("sbb"), pool77, MIXES, H, config)


def test_cash_has_no_nominal_loss(sbb_result):
    v = sbb_result.point["nominal"]
    for h in H:
        assert metric(v, "p_loss_gt_05", h, CASH) == 0.0
        assert metric(v, "mdd_p90", h, CASH) == 0.0
        assert metric(v, "p_mdd_gt_10", h, CASH) == 0.0


def test_equity_heavy_is_riskier(sbb_result):
    v = sbb_result.point["nominal"]
    assert (
        metric(v, "p_mdd_gt_30", 10, EQ100) > metric(v, "p_mdd_gt_30", 10, B6040) >= metric(v, "p_mdd_gt_30", 10, CASH)
    )
    assert metric(v, "cvar95_12m", 5, EQ100) > metric(v, "cvar95_12m", 5, B6040)
    assert metric(v, "mdd_p90", 10, EQ100) > metric(v, "mdd_p90", 10, BONDS)


def test_metric_monotonicity_and_ranges(sbb_result):
    for basis in ("nominal", "real"):
        v = sbb_result.point[basis]
        q = [v[schema.METRICS.index(f"ret_ann_p{p:02d}")] for p in schema.RET_QUANTILES]
        assert all((a <= b + 1e-12).all() for a, b in zip(q, q[1:], strict=False))
        losses = [v[schema.METRICS.index(f"p_loss_gt_{x:02d}")] for x in schema.LOSS_THRESHOLDS]
        assert all((a >= b - 1e-12).all() for a, b in zip(losses, losses[1:], strict=False))
        mdd = v[schema.METRICS.index("mdd_p90")]
        assert ((mdd >= 0) & (mdd <= 1)).all()
        # la perte maximale ne peut que croître avec l'horizon (mêmes trajectoires, préfixes)
        assert (np.diff(mdd, axis=0) >= -1e-12).all()
    lo, hi = sbb_result.ci_lo["nominal"], sbb_result.ci_hi["nominal"]
    assert (lo <= hi + 1e-12).all()


def test_real_below_nominal_with_positive_inflation(sbb_result):
    i = schema.METRICS.index("ret_ann_p50")
    assert (sbb_result.point["real"][i] < sbb_result.point["nominal"][i]).all()


def test_historical_reference_2022(pool77):
    rows = historical_reference(pool77, MIXES, H)
    r22 = {r["mix_id"]: r["value"] for r in rows if r["metric"] == "ret_2022" and r["basis"] == "nominal"}
    j = pool77.blocks.index("CASH")
    in22 = np.asarray(pool77.dates.year == 2022)
    assert r22[CASH] == pytest.approx(np.prod(1 + pool77.returns[in22, j]) - 1)


@pytest.mark.parametrize("name", ["small", "full"])
def test_shipped_configs_have_no_duplicate_mixes(name):
    from alphaforge.scenarios import job

    cfg = job.load_config(name)
    sens = cfg["sensitivity"]["mixes"]
    assert len(sens) == len(set(sens)), f"doublon dans sensitivity.mixes de {name}"
    for family, anchors in {**cfg["grid"]["anchors"], **cfg["grid"]["anchors_crypto"]}.items():
        ids = [schema.mix_id({b: w / 100 for b, w in a.items()}) for a in anchors]
        assert len(ids) == len(set(ids)), f"ancre en double pour {family} dans {name}"
    assert cfg["default_model"] in cfg["models"]


def test_sensitivity_deduplicates_targets(pool77):
    from alphaforge.scenarios import job

    cfg = {"sensitivity": {"enabled": True, "block_lengths": [3], "n_paths": 50, "mixes": [CASH, CASH, BONDS]}}
    rows = job._sensitivity(cfg, pool77, MIXES, [1], seed=1)
    keys = [(r["mix_id"], r["horizon_years"], r["metric"]) for r in rows]
    assert len(keys) == len(set(keys)) and {r["mix_id"] for r in rows} == {CASH, BONDS}


def test_hmm_k_streams_are_independent(pool77):
    """Le K = 2 ajusté ne dépend pas de la présence de K = 1 dans la liste des candidats."""
    a = fit(pool77, "hmm_rs", seed=4, params={"k_candidates": [1, 2], "n_init": 2})
    b = fit(pool77, "hmm_rs", seed=4, params={"k_candidates": [2], "n_init": 2})
    assert a.info["bic"]["2"] == b.info["bic"]["2"]


def test_hmm_filtered_last_variant(pool77):
    f = fit(pool77, "hmm_rs_fl", seed=4, params={"k_candidates": [1, 2], "n_init": 1})
    assert f.model_id == "hmm_rs_fl" and f.info["initial_state"] == "filtered_last"


# --- job de bout en bout ---------------------------------------------------------------------------------------


def _tiny_config():
    return {
        "seed": 5,
        "workers": 1,
        "default_model": "sbb",
        "families": ["CAD77", "USD1926"],
        "models": ["sbb", "hmm_rs"],
        "horizons": [1, 5],
        "crypto": {"enabled": True, "families": ["CAD77"]},
        "simulation": {"n_paths": 200, "n_boot": 3, "n_paths_boot": 50, "ci_level": 0.9, "mem_budget_mb": 64},
        "model_params": {"hmm_rs": {"k_candidates": [1, 2], "n_init": 1}},
        "grid": {
            "core": {
                "CAD77": {
                    "CA_EQ": {"values": [0, 50]},
                    "US_MKT": {"values": [0, 50]},
                    "BONDS": {"values": [0, 50, 100]},
                },
                "default": {"US_MKT": {"values": [0, 50, 100]}, "BONDS": {"values": [0, 50, 100]}},
            },
            "crypto": {"CAD77": {"US_MKT": {"values": [90, 95]}, "CRYPTO": {"values": [5, 10]}}},
            "anchors": {"CAD77": [{"CASH": 100}], "USD1926": [{"CASH": 100}]},
        },
        "sensitivity": {"enabled": True, "block_lengths": [1, 6], "n_paths": 100, "mixes": [CASH]},
        "runtime": {"models": ["sbb"], "digits": 4},
    }


def test_job_end_to_end(synthetic_dir, tmp_path):
    from alphaforge.scenarios import job

    manifest = job.run(_tiny_config(), str(synthetic_dir), str(tmp_path))
    table = pd.read_parquet(tmp_path / "table" / "scenarios.parquet")
    assert list(table.columns) == list(schema.COLUMN_NAMES)
    assert not schema.validate_rows(table.to_dict("records"))
    assert set(table["data_sha256"]) == {"synthetic0001"}
    assert manifest["rows"]["table"] == len(table)
    assert table.loc[table.mix_id.str.contains("-cr"), "hypothese"].all()
    assert not table.loc[~table.mix_id.str.contains("-cr"), "hypothese"].any()
    rt = json.loads((tmp_path / "runtime" / "scenarios_runtime.json").read_text())
    assert rt["data_sha256"] == "synthetic0001" and set(rt["tables"]) == {
        "sbb|CAD77",
        "sbb|CAD77+CRYPTO",
        "sbb|USD1926",
    }
    for name in ("manifest.json", "fits.json", "historical_reference.csv", "sensitivity_block_length.csv"):
        assert (tmp_path / name).exists()
    # contrat avec l'outil : manifest["table"] désigne le CSV compact, sha256 vérifiable, colonnes du schéma
    import hashlib

    declared = manifest["table"]
    body = (tmp_path / declared["file"]).read_bytes()
    assert declared["format"] == "csv" and hashlib.sha256(body).hexdigest() == declared["sha256"]
    assert pd.read_csv(tmp_path / declared["file"]).columns.tolist() == list(schema.COLUMN_NAMES)
    assert set(manifest["outputs_sha256"]) >= {"runtime/scenarios_runtime.json", "table/scenarios.parquet"}
    assert [p.suffix for p in (tmp_path / "table").iterdir()] == [".parquet"]
    assert manifest["validated_horizons"] == [1, 3, 5, 10]
    entries = {m["model_id"]: m for m in manifest["models"]}
    assert entries["sbb"]["display"] == "compare" and entries["hmm_rs"]["display"] == "sensitivity_only"
    assert entries["sbb"]["validation"]
    # run_id local (sans ALPHAFORGE_RUN_ID) : le nom du dossier de sortie, lisible par l'outil une fois publié.
    assert manifest["run_id"] == tmp_path.name
    from alphaforge.scenarios.tool_table import LATEST_KEY, ScenarioTableLoader
    from alphaforge.store.local import LocalStore

    store = LocalStore(tmp_path / "kb")
    prefix = f"scenarios/output/{manifest['run_id']}/"
    store.put(prefix + declared["file"], body, content_type="text/csv")
    store.put_json(prefix + "manifest.json", manifest)
    store.put_json(LATEST_KEY, {"run_id": manifest["run_id"]})
    assert ScenarioTableLoader(store).load().run_id == manifest["run_id"]
    # même graine -> mêmes octets de table (hors horodatage, qui n'est pas dans la table)
    other = tmp_path / "again"
    job.run(_tiny_config(), str(synthetic_dir), str(other), run_id="run-again")
    assert pd.read_parquet(other / "table" / "scenarios.parquet").equals(table)


def test_job_run_id_resolution(tmp_path, monkeypatch):
    from alphaforge.scenarios import job

    monkeypatch.delenv("ALPHAFORGE_RUN_ID", raising=False)
    assert job.resolve_run_id("explicit-1", str(tmp_path)) == "explicit-1"
    assert job.resolve_run_id(None, str(tmp_path / "local-run")) == "local-run"
    monkeypatch.setenv("ALPHAFORGE_RUN_ID", "sfn-uuid-1")
    assert job.resolve_run_id(None, str(tmp_path / "output")) == "sfn-uuid-1"
    with pytest.raises(ValueError, match="run_id invalide"):
        job.resolve_run_id("a.b", str(tmp_path))


def test_anchor_cash_deflation_keeps_inflation_sign(pool77):
    """Inflation récente négative : l'ancrage devient additif, sans inverser le signe des mois (M2)."""
    from dataclasses import replace

    infl = pool77.inflation.copy()
    infl[-12:] = -0.002  # déflation sur les 12 derniers mois
    pool = replace(pool77, inflation=infl)
    anchored, info = pool.anchor_cash(12)
    assert info["infl_anchor"] == "additive" and info["infl_scale"] is None
    assert anchored.inflation.mean() == pytest.approx(infl[-12:].mean())
    assert np.corrcoef(anchored.inflation, infl)[0, 1] == pytest.approx(1.0)
    _, normal = pool77.anchor_cash(12)
    assert normal["infl_anchor"] == "scale" and normal["infl_scale"] > 0


def _real_data_dir() -> Path | None:
    """Données longues réelles : ALPHAFORGE_SCENARIOS_DATA, sinon celles du moteur de backtest (ALPHAFORGE_BT_DATA ou
    alphaforge/data/long) si les parquets y sont (jamais versionnés : absents en CI)."""
    if os.environ.get("ALPHAFORGE_SCENARIOS_DATA"):
        return Path(os.environ["ALPHAFORGE_SCENARIOS_DATA"])
    from alphaforge.finance.backtest import paths

    return paths.data_dir() if paths.long_data_available(("numpy", "pandas", "pyarrow")) else None


@pytest.mark.skipif(_real_data_dir() is None, reason="données longues absentes (parquets non versionnés)")
def test_real_data_pools():
    from alphaforge.scenarios.data import load_inputs

    inp = load_inputs(_real_data_dir())
    for fam in schema.FAMILIES:
        p = build_pool(inp, fam)
        assert p.n > 500 and not np.isnan(p.returns).any()
