"""Integration avec F2 (research/finance/portfolio, lecture seule) : le mandat emis est optimisable.

~1 s par mandat sur le starter (fenetre limitee par ESGV, 2018-10 -> 2026-09) : pas marque slow.
"""

from __future__ import annotations

from datetime import date

import pytest

portfolio = pytest.importorskip("alphaforge.finance.portfolio")

from alphaforge.finance.policy import compile_profile  # noqa: E402

from ._personas import AS_OF, amira, robert  # noqa: E402


@pytest.mark.parametrize("make", [amira, robert])
def test_optimizer_optimal(make):
    res = compile_profile(make(), AS_OF)
    out = portfolio.optimizer.optimize(res.policy, as_of=date(2026, 9, 30))
    assert out.status == "optimal", (out.infeasible_rules, out.message)
    eq = sum(
        w
        for a, w in out.weights.items()
        if a in ("XIU.TO", "SPY", "QQQ", "ESGV")
        or a in [x for x in res.policy.universe if x not in ("XBB.TO", "ZST.TO", "AGG", "TLT", "GLD")]
    )
    assert eq <= res.e_cap + 1e-6
