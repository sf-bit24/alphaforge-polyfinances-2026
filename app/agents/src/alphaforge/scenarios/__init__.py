"""Scénarios probabilistes de portefeuille (volet B) : générateurs, simulation et table précalculée.

Simulation uniquement : modèle, pas prévision ; aucun conseil financier personnalisé.

Ce paquet n'importe rien de lourd à l'import. ``schema`` et ``grid`` n'utilisent que la bibliothèque standard
(lisibles par le runtime AgentCore) ; ``data``, ``bootstrap``, ``hmm``, ``models``, ``engine`` et ``job`` demandent
le groupe de dépendances optionnel ``scenarios`` (numpy, pandas, pyarrow).
"""
