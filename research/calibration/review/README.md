# Revue et réconciliation de la table de risque (v0.2)

Ce dossier contient les scripts qui produisent et vérifient `policy/risk_levels.yaml` v0.2.

Cette version réconcilie deux propositions :
- **la proposition théorique**, qui fournit l'architecture profil → R : capacité calculée à partir
  de faits, tolérance pondérée par la confiance, règle en dollars, seaux par objectif, statuts et
  biais ;
- **la calibration empirique** (`../out/`), qui fournit les budgets de chaque niveau : l'enveloppe
  historique ENV à la borne haute d'actions du niveau, arrondie au-dessus.

| Script | Rôle |
|---|---|
| `v02.py` | recalcule les budgets à partir de `../out/calib_grid5.csv` et `../out/halfcash_env.csv` |
| `expand.py` | développe le YAML en objets `Limit` et les valide contre `contracts/policy.py` (6 niveaux × 15 limites), puis contrôle les portefeuilles de référence |
| `persona_v02.py` | applique la table à Amira, Mateo et Robert (entrées HYPOTHESE) |
| `check.py`, `s2.py`, `eng.py` | contrôles de cohérence : CVaR mensuelle sur l'historique long vs fenêtre récente ; CVaR 12 mois (60/40 → 13,0 %, 100 % US_MKT → 23,4 %) |

À lancer depuis la racine du dépôt, avec un environnement qui contient `pydantic`, `pyyaml` et
`pandas` :

```bash
python -I research/calibration/review/expand.py
# Variables optionnelles : RISK_YAML, CALIB_OUT, REVIEW_DIR, AF_REPO, BACKTEST_DIR
```

Dépendances : `contracts/policy.py` (PolicySpec 0.2.0-draft) et `research/backtest`. **Ni l'un ni
l'autre n'est encore sur `master`.**

## Décisions humaines encore ouvertes

Le détail est dans l'en-tête de `policy/risk_levels.yaml` et dans `research/calibration/docs/README.md`.

1. **Marge de 4 points pour l'écart quotidien sur la perte planifiée.** Elle fait passer Mateo de
   N3 à N2 et Robert de N1 à N0.
2. **Coupures du score R et a priori de tolérance à 25** : ordinaux, non calibrés.
3. **Seuil d'horizon** : probabilité de perte nominale ≤ 10 %.
4. **Crypto** : seulement à partir de N4, avec φ = 0,04.
5. **Hypothèses de construction** : plafonds par FNB et par classe, or, TLT, surcharges tech de QQQ
   et XIU.
6. **Objectif de l'optimiseur** : `min_risk` se place au bas de la bande d'actions. Envisager
   `max_utility`.
7. **Mesure `STRESS_2022`** : à ajouter ou non à `RiskMeasure`.
