"""``OkfClientStore`` lit ``portefeuille-existant.md`` et sa version entre dans celle des données (pur, en CI)."""

from __future__ import annotations

from alphaforge import okf
from alphaforge.finance.debate.okf_bridge import OkfClientStore, OkfMarketStore
from alphaforge.profile.state import portfolio_key
from alphaforge.store.local import LocalStore

CLIENT = "8f0c1c2e-0000-4000-8000-0000000000bb"
DATA = {
    "view": {
        "status": "confirmed",
        "positions": [
            {"id": "p1", "ticker": "RY.TO", "asset_class": "equity", "value_cad": 40_000.0, "resolved": True}
        ],
    },
    "turn": 2,
}


class _Q:  # le questionnaire n'est pas lu par existing_portfolio
    pass


def _write(store, data=DATA, text=None):
    doc = okf.new_doc(
        type="Existing Portfolio",
        title="Portefeuille existant",
        description="Positions du portefeuille existant.",
        tags=["portefeuille-existant"],
        owners=["alphaforge-a2"],
        sensitivity="client",
        generated_by="agent:A2",
        at="2026-11-15T12:00:00Z",
        status="stable",
        stale_after="2026-12-15T12:00:00Z",
        sources=[],
        data=data,
        body="# Portefeuille existant\n",
    )
    store.put_text(portfolio_key(CLIENT), text if text is not None else okf.render(doc))


def test_absent_portfolio_reads_nothing(tmp_path):
    cs = OkfClientStore(LocalStore(tmp_path), _Q())
    assert cs.existing_portfolio(CLIENT) is None and cs.inputs == {}


def test_portfolio_is_read_and_versioned(tmp_path):
    store = LocalStore(tmp_path)
    _write(store)
    cs = OkfClientStore(store, _Q())
    data = cs.existing_portfolio(CLIENT)
    assert data["view"]["positions"][0]["ticker"] == "RY.TO"
    assert list(cs.inputs) == [portfolio_key(CLIENT)] and cs.inputs[portfolio_key(CLIENT)]


def test_unreadable_portfolio_is_ignored_but_visible_in_the_version(tmp_path):
    store = LocalStore(tmp_path)
    _write(store, text="pas un document OKF")
    cs = OkfClientStore(store, _Q())
    assert cs.existing_portfolio(CLIENT) is None
    assert cs.inputs[portfolio_key(CLIENT)].startswith("illisible:")


def test_client_inputs_enter_the_data_version_only_when_present(tmp_path):
    store = LocalStore(tmp_path)
    base = OkfMarketStore(store).data_version("d1")
    unchanged = OkfMarketStore(store)
    unchanged.note_client_inputs({})
    assert unchanged.data_version("d1") == base  # sans portefeuille existant : même version qu'avant
    _write(store)
    cs = OkfClientStore(store, _Q())
    cs.existing_portfolio(CLIENT)
    market = OkfMarketStore(store)
    market.note_client_inputs(cs.inputs)
    v1 = market.data_version("d1")
    assert v1 != base
    market.reset()  # reset relit les caches, pas les documents du client
    assert market.data_version("d1") == v1
    _write(store, data={**DATA, "turn": 3})
    cs2 = OkfClientStore(store, _Q())
    cs2.existing_portfolio(CLIENT)
    changed = OkfMarketStore(store)
    changed.note_client_inputs(cs2.inputs)
    assert changed.data_version("d1") != v1  # portefeuille modifié : nouvelle version
