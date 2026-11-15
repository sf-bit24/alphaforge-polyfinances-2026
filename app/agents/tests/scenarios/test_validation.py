"""Tests du volet C (validation hors échantillon), sur données synthétiques : ni réseau, ni AWS, ni données sous
licence."""

from __future__ import annotations

import math

import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")

from alphaforge.scenarios.validation import walkforward as wf  # noqa: E402
from alphaforge.scenarios.validation.analysis import per_mix_summary, pooled_summary  # noqa: E402
from alphaforge.scenarios.validation.scoring import (  # noqa: E402
    crps_samples,
    ks_uniform,
    moving_block_bootstrap,
    pinball,
    pit,
    realized_outcome,
    rolling_outcomes,
)


def test_crps_matches_bruteforce_and_normal():
    rng = np.random.default_rng(0)
    x = rng.normal(size=400)
    y = 0.3
    brute = np.mean(np.abs(x - y)) - 0.5 * np.mean(np.abs(x[:, None] - x[None, :]))
    assert crps_samples(x, y) == pytest.approx(brute, rel=1e-12)
    # loi normale standard : CRPS(y) = y(2Φ(y)-1) + 2φ(y) - 1/√π
    big = rng.normal(size=200_000)
    phi = math.exp(-y * y / 2) / math.sqrt(2 * math.pi)
    Phi = 0.5 * (1 + math.erf(y / math.sqrt(2)))
    exact = y * (2 * Phi - 1) + 2 * phi - 1 / math.sqrt(math.pi)
    assert crps_samples(big, y) == pytest.approx(exact, abs=3e-3)
    # point : CRPS = erreur absolue
    assert crps_samples(np.array([1.0]), 0.25) == pytest.approx(0.75)


def test_pit_uniform_under_correct_model_and_ks():
    rng = np.random.default_rng(1)
    sims = rng.normal(size=2000)
    u = np.array([pit(sims, rng.normal(), rng.random()) for _ in range(300)])
    d, p, n = ks_uniform(u)
    assert n == 300 and p > 0.01
    # modèle trop étroit : PIT en U, rejeté
    narrow = 0.4 * sims
    u2 = np.array([pit(narrow, rng.normal(), rng.random()) for _ in range(300)])
    assert ks_uniform(u2)[1] < 1e-4
    # atome : PIT randomisé sur le saut
    assert pit(np.zeros(10), 0.0, 0.3) == pytest.approx(0.3)


def test_pinball_and_block_bootstrap():
    assert pinball(0.0, 1.0, 0.1) == pytest.approx(0.1)
    assert pinball(0.0, -1.0, 0.1) == pytest.approx(0.9)
    idx = moving_block_bootstrap(10, 3, 5, np.random.default_rng(0))
    assert idx.shape == (5, 10) and idx.max() < 10
    # blocs contigus (circulaires)
    assert all(((idx[:, 1:3] - idx[:, 0:2]) % 10 == 1).all(axis=1))


def test_realized_and_rolling_outcomes_agree_with_engine_definition():
    lr = np.log1p(np.array([0.10, -0.20, 0.05] * 4))
    r, mdd, logw = realized_outcome(lr)
    assert logw == pytest.approx(lr.sum())
    assert r == pytest.approx(math.exp(lr.sum()) - 1)  # H = 1 an
    # perte max. depuis le sommet, capital initial compris
    w = np.exp(np.concatenate([[0.0], np.cumsum(lr)]))
    assert mdd == pytest.approx(float(np.max(1 - w / np.maximum.accumulate(w))))
    ro = rolling_outcomes(np.concatenate([lr, lr]), 1)
    assert len(ro["mdd"]) == 13 and ro["mdd"][0] == pytest.approx(mdd)


@pytest.fixture(scope="module")
def wf_state(inputs):
    wf._STATE["pools"] = wf.make_pools(inputs)
    return wf._STATE["pools"]


def test_mix_labels_are_equity_first(wf_state):
    from alphaforge.scenarios.schema import parse_mix_id

    for fam in ("CAD77", "USD1926"):
        for label, mid in wf._mixes_for(fam).items():
            w = parse_mix_id(mid)
            eq = round(100 * (w["CA_EQ"] + w["US_MKT"]))
            if label.endswith("cs100"):
                assert w["CASH"] == 1.0
            else:
                assert label == f"eq{eq:02d}_fi{100 - eq:02d}" and round(100 * w["BONDS"]) == 100 - eq


def test_walkforward_no_look_ahead(wf_state):
    """Corrompre les mois postérieurs à l'origine ne change aucune quantité prédictive (seulement le réalisé)."""
    opts = {"horizons": (1, 3), "n_paths": 300, "seed": 5}
    task = ("CAD77", "1995-12", ("sbb", "sbb_ca", "hmm_rs"), opts)
    rows1, _ = wf.run_origin(task)
    clean = wf._STATE["pools"]["CAD77"]
    bad = clean._subset(np.arange(clean.n))
    after = np.asarray(bad.dates > pd.Timestamp("1995-12-31"))
    bad.R[after] = bad.R[after] * -1.5 + 0.01
    wf._STATE["pools"] = {**wf_state, "CAD77": bad}
    try:
        rows2, _ = wf.run_origin(task)
    finally:
        wf._STATE["pools"] = wf_state
    a, b = pd.DataFrame(rows1), pd.DataFrame(rows2)
    pred = [c for c in a.columns if c.startswith(("ret_q", "mdd_q", "p_"))]
    models = a["model"] != "stress_2022"  # le repère 2022 lit 2022 par construction (documenté)
    pd.testing.assert_frame_equal(a.loc[models, pred], b.loc[models, pred])
    assert not np.allclose(a["y_ret"], b["y_ret"])


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_run_is_deterministic_and_aggregates(synthetic_dir):
    cfg = wf.WFConfig(
        input_dir=str(synthetic_dir),
        n_paths=200,
        horizons=(1, 3),
        families=("CAD77",),
        models=("sbb", "iid"),
        block_models_families=(),
        max_origins=6,
        workers=1,
    )
    s1, f1 = wf.run_walkforward(cfg)
    cfg.workers = 2
    s2, _ = wf.run_walkforward(cfg)
    pd.testing.assert_frame_equal(s1, s2)
    assert set(s1["model"]) == {"sbb", "iid", "hist_emp", "stress_2022"}
    assert (f1["n_hist"] > 0).all()
    pm = per_mix_summary(s1, 50, 1)
    po = pooled_summary(s1, 50, 1)
    dist = pm[pm["model"] != "stress_2022"]  # repère ponctuel : pas d'intervalle (nan)
    assert ((dist["in80_ret"] >= 0) & (dist["in80_ret"] <= 1)).all()
    assert pm.loc[pm["model"] == "stress_2022", "in80_ret"].isna().all()
    assert "crps_ret_skill" in po.columns and len(po) == 8
