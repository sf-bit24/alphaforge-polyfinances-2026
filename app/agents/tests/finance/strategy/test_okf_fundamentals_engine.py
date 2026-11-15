"""Lot E dans le pipeline complet, mode rules (sauté sans données longues) : les actualités ne changent rien, les
fondamentaux (poids nul) ne changent que la version des données."""

from __future__ import annotations

import pytest

from alphaforge.finance.debate.facts import sha256_json
from alphaforge.finance.debate.okf_bridge import OkfMarketStore
from alphaforge.finance.debate.pipeline import build_portfolio
from alphaforge.finance.policy import compile_profile
from alphaforge.store.local import LocalStore

from ..policy import _personas as P
from ._okf_docs import SOCIETES, news_text


def _store(root, universe, news: bool) -> LocalStore:
    store = LocalStore(root)
    for name in ("atd.md", "csu.md"):
        store.put_text(f"general/societes/{name}", (SOCIETES / name).read_text(encoding="utf-8"))
    if news:  # chaque titre de l'univers a une nouvelle admissible, et une autre publiée après as_of
        store.put_text(
            "general/actualites/2026/09/tout-le-monde-en-parle-aaaa1111.md",
            news_text("Tout le monde en parle", tuple(t.lower() for t in universe), "2026-09-20T12:00:00Z"),
        )
        store.put_text(
            "general/actualites/2026/10/krach-annonce-bbbb2222.md",
            news_text("Krach annoncé", tuple(universe), "2026-10-05T12:00:00Z"),
        )
    return store


def _sig(res):
    d = res.decision
    return {
        "positions": [(p.asset_id, round(p.weight, 10), p.role) for p in d.positions],
        "policy": sha256_json(res.policy.model_dump(mode="json")),
        "data_version": sorted({t.data_version for t in d.trace if t.data_version}),
        "kind": d.kind,
    }


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    universe = compile_profile(P.amira(), P.AS_OF).policy.universe
    out, markets = {}, {}
    for label, news in (("sans_actualites", False), ("avec_actualites", True)):
        markets[label] = OkfMarketStore(_store(tmp_path_factory.mktemp(label), universe, news))
        out[label] = build_portfolio(
            P.amira(), P.AS_OF, strategy=True, mode="rules", evidence_fn=markets[label].evidence
        )
    out["sans_okf"] = build_portfolio(P.amira(), P.AS_OF, strategy=True, mode="rules")
    return out, markets, universe


def test_news_change_nothing(runs):
    out, markets, universe = runs
    assert _sig(out["avec_actualites"]) == _sig(out["sans_actualites"])
    held = [p.asset_id for p in out["avec_actualites"].decision.positions]
    news = markets["avec_actualites"].evidence(held[0], "news", P.AS_OF)  # la nouvelle existe bien, et est vue
    assert [f.value for f in news] == ["Tout le monde en parle"] and news[0].status == "HYPOTHESE"
    assert not any(k.startswith("general/actualites/") for k in markets["avec_actualites"].inputs)


def test_fundamentals_have_zero_weight_and_only_extend_the_data_version(runs):
    out, _, _ = runs
    a, b = _sig(out["sans_actualites"]), _sig(out["sans_okf"])
    assert (a["positions"], a["policy"], a["kind"]) == (b["positions"], b["policy"], b["kind"])
    assert len(b["data_version"]) == 1 and "+okf:" not in b["data_version"][0]
    base = b["data_version"][0]
    assert all(v == base or v.startswith(f"{base}+okf:") for v in a["data_version"])
    assert any("+okf:" in v for v in a["data_version"])


def test_no_okf_fact_drives_an_amendment(runs):
    out, _, _ = runs
    for rnd in out["avec_actualites"].rounds:
        for applied in rnd.decisions:
            if applied.status == "applique" and applied.amendment.kind != "flag_only":
                assert not any(f.startswith("okf.") for f in applied.amendment.evidence_fact_ids)
