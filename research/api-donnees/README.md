# research/api-donnees — API de données économiques pour la base générale (simulation seulement)

Recherche du 14 novembre 2026 sur les API de données économiques et financières publiques, gratuites ou à palier
gratuit, qui peuvent alimenter la base générale d'AlphaForge AI (agent A5, sous A6). Environ deux cents sources ont été
passées en revue; une bonne partie a été appelée en direct le jour même, depuis un poste résidentiel. **Aucune n'a été
appelée depuis une IP AWS.**

| Élément | Contenu |
| --- | --- |
| `rapport.md` | Rapport de synthèse, en français : trois régimes de licence, un tableau par famille de données de l'énoncé (accès et clé, limites, couverture, historique, fréquence, licence, point-in-time), millésimes natifs et fausses dates de publication, champs de provenance proposés, pièges 2025-2026 |
| `notes/macro_canada.md` | Banque du Canada (Valet), Statistique Canada (WDS, SDMX, calendrier, tableaux temps réel, Delta File), CKAN fédéral et provinciaux, panier de séries vérifiées |
| `notes/macro_etats_unis.md` | FRED et ALFRED, BLS, BEA, Census, Trésor, NY Fed, Philly Fed, EIA, USDA, CFTC; effets du shutdown de 2025 |
| `notes/international_agregateurs.md` | FMI, Banque mondiale, OCDE, BRI, BCE, Eurostat, autres banques centrales; DBnomics, OpenBB, pandas-datareader |
| `notes/taux_devises_matieres.md` | Courbes de taux, devises (Valet, Frankfurter, paliers commerciaux), or et matières premières |
| `notes/prix_marche_crypto.md` | Prix des actions et FNB (couverture du TSX au gratuit), opérations sur titres, cryptoactifs. Aucun appel en direct sur cet axe |
| `notes/fondamentaux_depots_fnb.md` | SEC EDGAR, SEDAR+, API de fondamentaux, avoirs et frais des FNB, identifiants, calendriers |
| `notes/nouvelles_politique.md` | API de nouvelles, flux des banques centrales et des gouvernements, sources réglementaires, jeux de sentiment |
| `notes/esg_secteurs.md` | Émissions, listes d'exclusion, scores ESG, classifications sectorielles, risque physique |

Les décisions que l'équipe en a tirées le 15 novembre 2026 (usage personnel non commercial, base générale unique, clés
gratuites à la demande dans Secrets Manager, chiffres d'ATD et de CSU sous `app/knowledge/general/societes/`, preuves
ESG factuelles) sont consignées dans le Brain, concept `architecture/sources-donnees.md`, qui garde aussi une copie du
rapport (`references/recherche-api-donnees.md`).

Les notes sont un instantané au 14 novembre 2026 : quotas, paliers gratuits et conditions changent souvent. Revérifier
une source avant de l'intégrer au code.
