from __future__ import annotations

from dataclasses import dataclass

from .models import Allocation, Asset, Decision, Persona, Portfolio, TraceEvent


@dataclass
class Brain:
    assets: list[Asset]

    def profile(self, persona: Persona) -> TraceEvent:
        return TraceEvent(
            agent="ProfilerAgent",
            action="validate_profile",
            reasoning=f"Profil {persona.name} validé sur horizon, capacité de perte et biais comportementaux.",
            evidence=[
                f"horizon={persona.horizon_years} ans",
                f"loss_aversion={persona.behavioral_scores.get('loss_aversion', 'n/a')}",
                f"overconfidence={persona.behavioral_scores.get('overconfidence', 'n/a')}",
            ],
        )

    def esg_filter(self, persona: Persona) -> tuple[list[Asset], TraceEvent]:
        eligible = [
            a
            for a in self.assets
            if not persona.constraints.esg_required or a.carbon_intensity != "high"
        ]
        return eligible, TraceEvent(
            agent="ESGAgent",
            action="filter_universe",
            reasoning="Univers filtré selon les exclusions ESG déclarées.",
            evidence=[f"{len(eligible)}/{len(self.assets)} actifs conservés"],
        )

    def govern(self, persona: Persona, request: str = "") -> TraceEvent:
        risky = any(
            word in request.lower() for word in ("all-in", "tout investir", "levier", "sans limite")
        )
        if risky or persona.constraints.max_crypto == 0 and "crypto" in request.lower():
            return TraceEvent(
                agent="GovernanceAgent",
                action="refuse_or_bound",
                reasoning="La demande dépasse les limites du profil ou contredit une contrainte explicite.",
                evidence=["anti-sycophance activée"],
            )
        return TraceEvent(
            agent="GovernanceAgent",
            action="approve_with_limits",
            reasoning="Demande compatible sous réserve du respect des bornes de portefeuille.",
            evidence=["bornes RRTTLLU appliquées"],
        )

    def recommend(self, persona: Persona, request: str = "") -> Decision:
        trace = [self.profile(persona)]
        eligible, esg_trace = self.esg_filter(persona)
        trace.append(esg_trace)
        governance = self.govern(persona, request)
        trace.append(governance)
        forbidden = "refuse" in governance.action
        if forbidden and ("all-in" in request.lower() or "tout investir" in request.lower()):
            portfolio = Portfolio(
                persona=persona.name,
                allocations=[],
                expected_return=0,
                volatility=0,
                max_drawdown_proxy=0,
                warnings=["Demande refusée : allocation concentrée incompatible avec le profil."],
                refused=True,
            )
            return Decision(
                portfolio=portfolio,
                trace=trace,
                recommendation="Non : je refuse cette allocation et propose une alternative diversifiée.",
            )
        risk_map = {"low": 0.25, "balanced": 0.55, "high": 0.75, "very_high": 0.88}
        equity_cap = min(persona.constraints.max_equity, risk_map[persona.risk_tolerance])
        cash = persona.constraints.min_cash
        bond = max(0.0, 1 - equity_cap - cash)
        selected = {a.asset_class: a for a in eligible}
        equity = selected.get("equity") or eligible[0]
        bond_asset = selected.get("bond") or selected.get("cash") or eligible[-1]
        cash_asset = selected.get("cash") or bond_asset
        allocations = [
            Allocation(
                ticker=equity.ticker,
                weight=equity_cap,
                rationale="Moteur de croissance borné par le plafond d’actions.",
            ),
            Allocation(
                ticker=bond_asset.ticker,
                weight=bond,
                rationale="Stabilité et réduction de la volatilité.",
            ),
            Allocation(
                ticker=cash_asset.ticker,
                weight=cash,
                rationale="Liquidité minimale liée au profil.",
            ),
        ]
        merged = {}
        for a in allocations:
            merged[a.ticker] = merged.get(a.ticker, 0) + a.weight
        allocations = [
            Allocation(ticker=k, weight=round(v, 4), rationale="Allocation consolidée.")
            for k, v in merged.items()
        ]
        ret = sum(
            a.weight * next(x.expected_return for x in eligible if x.ticker == a.ticker)
            for a in allocations
        )
        vol = sum(
            a.weight * next(x.volatility for x in eligible if x.ticker == a.ticker)
            for a in allocations
        )
        portfolio = Portfolio(
            persona=persona.name,
            allocations=allocations,
            expected_return=ret,
            volatility=vol,
            max_drawdown_proxy=-vol * 2.2,
            warnings=[],
        )
        return Decision(
            portfolio=portfolio,
            trace=trace,
            recommendation="Proposition diversifiée, à valider avec les objectifs et contraintes de l’investisseur.",
        )
