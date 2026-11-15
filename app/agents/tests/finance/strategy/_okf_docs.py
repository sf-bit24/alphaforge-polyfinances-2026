"""Documents OKF de test pour le lot E : seeds réels de la base générale et actualité factice au format d'A6."""

from __future__ import annotations

from pathlib import Path

from alphaforge import okf

SOCIETES = Path(__file__).resolve().parents[4] / "knowledge" / "general" / "societes"


def news_text(
    title="Shopify annonce un partenariat",
    tickers=("shop.to", "ATD.TO"),
    published="2026-09-15T13:00:00Z",
    url="https://example.com/a",
) -> str:
    doc = okf.new_doc(
        type="News",
        title=title,
        description="Actualité de test.",
        tags=["actualites"],
        owners=["alphaforge-a6"],
        sensitivity="public",
        generated_by="agent:A6",
        at="2026-09-16T00:00:00Z",
        sources=[{"id": "n1", "title": title, "resource": url}],
        data={
            "kind": "news",
            "url": url,
            "source": "Exemple Presse",
            "published_at": published,
            "retrieved_at": "2026-09-16T00:00:00Z",
            "tickers": list(tickers),
        },
        body="Les produits bondissent de 40 % selon la rumeur.\n",
    )
    return okf.render(doc)
