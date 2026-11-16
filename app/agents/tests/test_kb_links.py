"""Liens et symboles des documents dans ``kb.list`` (CONTRACTS.md, section 3.2) : le graphe de la base."""

from alphaforge import okf
from alphaforge.profile import kb, kb_links

KNOWN = {
    "general/notions/beta.md",
    "general/notions/volatilite.md",
    "general/methodologie/niveaux.md",
    "general/faits/bankofcanada-ca/2026-11-09-abc.md",
}


def doc(key: str, *, body: str = "", tags: list[str] | None = None, data: dict | None = None):
    return key, okf.render(
        okf.new_doc(
            type="Financial Concept",
            title="Doc",
            description="d",
            tags=tags or ["notions"],
            owners=["x"],
            sensitivity="public",
            generated_by="human",
            at="2026-11-14T00:00:00Z",
            data=data or {},
            body=body,
        )
    )


def test_links_relative_to_the_folder_then_to_the_base_root():
    body = (
        "[Volatilité](volatilite.md), [niveaux](../methodologie/niveaux.md), "
        "[un fait](faits/bankofcanada-ca/2026-11-09-abc.md), [encore](volatilite.md#calcul)"
    )
    assert kb_links.document_links("general/notions/beta.md", body, KNOWN) == [
        "general/notions/volatilite.md",
        "general/methodologie/niveaux.md",
        "general/faits/bankofcanada-ca/2026-11-09-abc.md",
    ]


def test_links_ignore_external_absolute_missing_and_self_targets():
    body = (
        "[web](https://www.bankofcanada.ca/x.md) [mail](mailto:a@b.ca) [ancre](#calcul) "
        "[racine](/general/notions/beta.md) [absent](absent.md) [soi](beta.md) "
        "[hors base](../../clients/x/profil.md)"
    )
    assert kb_links.document_links("general/notions/beta.md", body, KNOWN) == []


def test_links_never_leave_their_base():
    known = {"general/notions/beta.md", "clients/c1/notes/a.md"}
    assert kb_links.resolve_link("clients/c1/notes/a.md", "../../../general/notions/beta.md", known) is None


def test_base_root_of_general_and_client_keys():
    assert kb_links.base_root("general/notions/beta.md") == "general/"
    assert kb_links.base_root("clients/8f0c/dimensions/horizon.md") == "clients/8f0c/"


def test_tag_tickers_need_a_document_that_declares_them():
    company = kb_links.Relations(tickers=["AAPL"])
    fact = kb_links.Relations(tag_tickers=["FAITS", "AAPL", "E2"])
    items = kb_links.attach([({"key": "general/societes/aapl.md"}, company), ({"key": "general/faits/x.md"}, fact)])
    assert [item["tickers"] for item in items] == [["AAPL"], ["AAPL"]]


def test_list_documents_returns_links_and_tickers(store):
    for key, text in (
        doc("general/notions/beta.md", body="Voir [la volatilité](volatilite.md) et [une note](retiree.md)."),
        doc("general/notions/volatilite.md", body="Retour au [bêta](beta.md)."),
        doc("general/notions/retiree.md", data={"retired": True}),
        doc("general/societes/aapl.md", data={"ticker": "AAPL"}),
        doc("general/actualites/2026/11/x.md", tags=["actualites", "energie", "enb.to"], data={"tickers": ["ENB.TO"]}),
        doc("general/faits/yahoo/2026-11-13-f.md", tags=["faits", "apple inc."], data={"tags": ["donnees", "aapl"]}),
    ):
        store.put_text(key, text)

    items = {item["key"]: item for item in kb.list_documents(store, "general/")}

    assert "general/notions/retiree.md" not in items
    assert items["general/notions/beta.md"]["links"] == ["general/notions/volatilite.md"]
    assert items["general/notions/volatilite.md"]["links"] == ["general/notions/beta.md"]
    assert items["general/societes/aapl.md"]["tickers"] == ["AAPL"]
    assert items["general/actualites/2026/11/x.md"]["tickers"] == ["ENB.TO"]
    assert items["general/faits/yahoo/2026-11-13-f.md"]["tickers"] == ["AAPL"]
    fields = {"key", "title", "type", "description", "updated_at", "links", "tickers"}
    assert all(set(item) == fields for item in items.values())


def test_unreadable_document_is_listed_without_relations(store):
    store.put_text("general/notions/casse.md", "---\ntype: [\n---\ncorps")
    (item,) = kb.list_documents(store, "general/")
    assert item["key"] == "general/notions/casse.md" and item["links"] == [] and item["tickers"] == []
