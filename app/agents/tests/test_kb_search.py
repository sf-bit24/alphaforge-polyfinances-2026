"""Recherche dans la Knowledge Base (Retrieve) avec un client factice : filtre facultatif, identifiant de passage."""

import pytest

from alphaforge.config import Settings
from alphaforge.profile import kb


class StubClient:
    def __init__(self, response=None, error=None):
        self.calls = []
        self.response = response or {
            "retrievalResults": [
                {
                    "content": {"text": "  Une actualité sur SHOP.TO.  "},
                    "location": {"type": "S3", "s3Location": {"uri": "s3://b/general/actualites/2026/11/x.md"}},
                    "score": 0.81234,
                    "metadata": {
                        "x-amz-bedrock-kb-chunk-id": "chunk-1",
                        "x-amz-bedrock-kb-source-uri": "s3://b/general/actualites/2026/11/x.md",
                        "ticker": "SHOP.TO",
                    },
                },
                {"content": {"text": "sans métadonnées"}, "location": {"type": "S3"}, "score": 0.5},
            ]
        }
        self.error = error

    def retrieve(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def search(client, **settings):
    env = {"ALPHAFORGE_KB_ID": "KB123", **settings}
    return kb.KnowledgeSearch(Settings.from_env(env), client=client)


def test_search_without_filter_keeps_the_previous_request_and_returns_chunk_ids():
    client = StubClient()
    results = search(client).search("rendement de SHOP", limit=3)
    assert client.calls == [
        {
            "knowledgeBaseId": "KB123",
            "retrievalQuery": {"text": "rendement de SHOP"},
            "retrievalConfiguration": {"vectorSearchConfiguration": {"numberOfResults": 3}},
        }
    ]
    assert results == [
        {
            "source": "s3://b/general/actualites/2026/11/x.md",
            "score": 0.812,
            "excerpt": "Une actualité sur SHOP.TO.",
            "chunk_id": "chunk-1",
        },
        {"source": "S3", "score": 0.5, "excerpt": "sans métadonnées", "chunk_id": None},
    ]


def test_search_passes_the_filter_to_vector_search_configuration():
    client = StubClient()
    flt = kb.retrieval_filter(equals={"ticker": "SHOP.TO", "type": "News"}, at_most={"published_epoch": 1794497400})
    assert flt == {
        "andAll": [
            {"equals": {"key": "ticker", "value": "SHOP.TO"}},
            {"equals": {"key": "type", "value": "News"}},
            {"lessThanOrEquals": {"key": "published_epoch", "value": 1794497400}},
        ]
    }
    search(client).search("SHOP", filter=flt)
    assert client.calls[0]["retrievalConfiguration"] == {
        "vectorSearchConfiguration": {"numberOfResults": 4, "filter": flt}
    }


def test_a_single_condition_is_not_wrapped_in_and_all():
    assert kb.retrieval_filter(equals={"ticker": "RY.TO"}) == {"equals": {"key": "ticker", "value": "RY.TO"}}
    assert kb.retrieval_filter() is None


@pytest.mark.parametrize(
    "flt",
    [
        {"startsWith": {"key": "ticker", "value": "SHOP"}},
        {"listContains": {"key": "tickers", "value": "SHOP.TO"}},
        {"andAll": [{"equals": {"key": "ticker", "value": "RY.TO"}}]},
        {"lessThanOrEquals": {"key": "published_epoch", "value": "1794497400"}},
        {"lessThanOrEquals": {"key": "published_epoch", "value": True}},
        {"in": {"key": "ticker", "value": ["RY.TO", 3]}},
        {"equals": {"key": "ticker"}},
        {"equals": {"key": "a", "value": 1}, "notEquals": {"key": "b", "value": 2}},
        {
            "andAll": [
                {
                    "andAll": [
                        {"orAll": [{"equals": {"key": "a", "value": 1}}] * 2},
                        {"equals": {"key": "b", "value": 1}},
                    ]
                },
                {"equals": {"key": "c", "value": 1}},
            ]
        },
    ],
)
def test_invalid_filters_fail_before_any_call(flt):
    client = StubClient()
    with pytest.raises(ValueError):
        search(client).search("x", filter=flt)
    assert client.calls == []


def test_search_is_empty_without_knowledge_base_and_on_errors():
    assert kb.KnowledgeSearch(Settings.from_env({}), client=StubClient()).search("x") == []
    failing = StubClient(error=RuntimeError("ValidationException"))
    flt = kb.retrieval_filter(equals={"ticker": "RY.TO"})
    assert search(failing).search("x", filter=flt) == []
    assert failing.calls[0]["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"] == flt
