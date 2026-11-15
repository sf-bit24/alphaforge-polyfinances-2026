"""Volet finance d'AlphaForge AI (simulation seulement, jamais un conseil).

- ``contracts`` : InvestorProfile, PolicySpec, Decision/Fact/TraceEvent (Pydantic) ;
- ``portfolio`` : F2 optimiseur, F3 analyses, F4 contrôle du Judge (lit le moteur de backtest ``finance.backtest``) ;
- ``backtest`` : moteur de backtest mensuel 1926-2026 et données longues (``data/long``) ;
- ``llm`` : appels LLM enregistrés et rejouables (llm_call, ReplayModel Strands) ;
- ``observability`` : télémétrie OpenTelemetry GenAI, vérification des entrées et sorties, audit chaîné ;
- ``rules`` : paramètres canadiens sourcés (canada_2026.yaml).
"""
