"""Validation hors échantillon des générateurs de scénarios (volet C).

Walk-forward : chaque modèle est ajusté par ``models.fit(pool, model_id, fitted_through=T)`` sur les seuls mois
<= T ; sa distribution prédictive sur T+1 .. T+12·H est notée contre le résultat réalisé (couverture des
intervalles, PIT/KS, CRPS, Brier), et comparée à deux repères (historique empirique naïf, « 2022 seulement »).
Point d'entrée : ``python -m alphaforge.scenarios.validation``. Rapport : ``VALIDATION.md``.

Dépendances : numpy et pandas (groupe ``scenarios``), aucune autre.
"""
