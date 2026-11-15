"""Preuves ESG de la base générale dans le mandat (CONTRACTS.md, section 11.5).

Règles, déterministes et sans LLM :
- une préférence ESG existe si l'investisseur a des exclusions (filtres de valeurs) ou ``esg_required`` ; sans
  elle, aucune preuve ESG ne change le mandat (``merge.apply_amendments``, garde 5) ;
- avant l'étape 0, chaque titre de l'univers qu'un fait ESG ``sector_activity`` relie à une catégorie exclue par
  l'investisseur est exclu, avec le fait cité comme raison. La liste codée en dur de
  ``policy.from_profile_view.EXCLUSION_TICKERS`` reste un repli : la preuve remplace alors sa raison.
"""

from __future__ import annotations

from datetime import date

from alphaforge.finance.contracts import InvestorProfile, PolicySpec
from alphaforge.finance.policy.from_profile_view import excluded_categories
from alphaforge.finance.strategy.okf_facts import esg_fact

from .facts import FactBook


def esg_preference(profile: InvestorProfile) -> bool:
    return bool(profile.preferences.value_filters) or profile.preferences.esg_required


def esg_exclusions(
    profile: InvestorProfile,
    policy: PolicySpec,
    market,
    as_of: date,
    book: FactBook,
    protect: tuple[str, ...] | list[str] = (),
) -> PolicySpec:
    """Mandat où les titres liés par un fait ``sector_activity`` à une catégorie exclue sont exclus, preuve citée.

    ``market`` est un ``OkfMarketStore`` (méthode ``esg_items``). Un titre de ``protect`` (la demande précise de
    l'investisseur) n'est pas exclu ici : la demande reste évaluée et encadrée comme avant. Renvoie ``policy``
    inchangé s'il n'y a rien."""
    categories = excluded_categories(profile)
    if not categories or not hasattr(market, "esg_items"):
        return policy
    new = policy.model_copy(deep=True)
    with book.step("s0c.esg_exclusions", tool="esg_items", inputs={"categories": sorted(categories)}):
        for ticker in policy.universe:
            if ticker in protect:
                continue
            items = [
                i for i in market.esg_items(ticker, as_of) if i.kind == "sector_activity" and i.metric in categories
            ]
            if not items:
                continue
            fid = book.absorb([esg_fact(items[0], ticker, 1).model_copy(update={"trace_id": book.current})])[0]
            new.excluded[ticker] = fid
    return new if new.excluded != policy.excluded else policy
