"""Volet finance d'AlphaForge AI (simulation seulement, jamais un conseil).

- ``contracts`` : InvestorProfile, PolicySpec, Decision/Fact/TraceEvent (Pydantic) ;
- ``portfolio`` : F2 optimiseur, F3 analyses, F4 contrôle du Judge (lit l'engine de research/backtest) ;
- ``llm`` : appels LLM enregistrés et rejouables (llm_call, ReplayModel Strands) ;
- ``observability`` : télémétrie OpenTelemetry GenAI, vérification des entrées et sorties, audit chaîné ;
- ``rules`` : paramètres canadiens sourcés (canada_2026.yaml).
"""
