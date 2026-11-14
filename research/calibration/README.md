# research/calibration : calibration empirique des niveaux de risque

> Simulation uniquement. Rien ici n'est un conseil financier. Les chiffres décrivent le passé.

Ce dossier mesure ce que chaque mélange actions / obligations / encaisse a réellement produit sur
l'historique long. Les niveaux de risque du `PolicySpec` sont ancrés sur ces données, et non sur la
seule fenêtre 2021-2026 du jeu de départ.

Le travail a été fait le 2026-11-14 sur le build de données `data_sha256 = 008f122d5da4f8f7` du
moteur `research/backtest`.

## Dépendance

Les scripts importent le moteur `research/backtest` (`engine.data`, `engine.metrics`), utilisé en
lecture seule. **Ce moteur n'est pas encore sur `master`** : il faut le clone de l'équipe finance.

## Reproduire

```bash
cd research/backtest
export CALIB_DIR=../calibration            # dossier des scripts (défaut : dossier courant)
export CALIB_OUT=../calibration/out        # sorties (défaut : $CALIB_DIR/out)
export STARTER_DIR=/chemin/vers/alphaforge_starter   # pour tails.py seulement (non versionné)
.venv/bin/python -I ../calibration/calib.py    # toutes les familles, grille de 10 %
.venv/bin/python -I ../calibration/calib2.py   # enveloppe, grille de 5 %, pires 12 mois, corrélations
.venv/bin/python -I ../calibration/calib3.py   # variante courte durée (50 % obligations / 50 % cash)
.venv/bin/python -I ../calibration/tails.py    # titres individuels, secteurs, crypto, quotidien
```

`calib3.py` a été relancé après versionnement et reproduit `out/halfcash_env.csv` à l'identique.

## Conventions

- **Rebalancement** : mensuel, sans frais. La variante annuelle s'écarte de 1,5 point au plus sur
  la baisse maximale.
- **Poche actions** : 50 % `CA_EQ` + 50 % `US_MKT`, en CAD.
- **Reste du portefeuille** : 75 % obligations / 25 % cash.
- **Familles de données** :
  - **CAD77** : 1977-2026, en CAD ;
  - **CAD71** : 1971+, en CAD, actions américaines seulement ; couvre 1973-74 ;
  - **USD46** : 1946+, en USD ;
  - **USD26** : 1926+, en USD ; scénario de stress seulement, incluant 1929-32.
- **ENV (enveloppe)** : la pire valeur de CAD77, CAD71 et USD46.
- **CVaR95-12m** : CVaR historique des rendements sur **12 mois glissants**. Les fenêtres se
  chevauchent : voir le nombre de fenêtres non chevauchantes dans `calib2.py`.

## Résultat (ENV, part d'actions e)

Toutes les valeurs sont en %.

| e | Volatilité | CVaR95-12m | Baisse maximale | Perte 2022 |
|---|---|---|---|---|
| 0 | 5,0 | 6,1 | 15,6 | 7,2 |
| 25 | 5,4 | 5,2 | 13,8 | 9,8 |
| 40 | 6,8 | 8,1 | 21,4 | 11,8 |
| 60 | 9,2 | 13,5 | 30,9 | 14,4 |
| 80 | 12,0 | 19,1 | 41,1 | 17,1 |
| 100 | 14,9 | 24,5 | 50,3 | 19,9 |

À retenir :
- **2021-2026 sous-estime la volatilité** : à 100 % actions, elle y vaut 11,5 % contre 13,2 % sur
  1977+, soit environ 13 % de moins.
- **La perte de 2022 ne sépare pas les niveaux de risque.** Les vraies queues de distribution sont
  2008, 2000-02, 1973-74 et 1929-32.

Les fichiers `out/` détaillent tous les chiffres.

**Pièges**, détaillés dans le rapport de calibration :
- biais du survivant (le siècle américain est exceptionnel) ;
- 1977-2026 a été un marché obligataire haussier ;
- la corrélation actions-obligations change de signe (+0,60 en 2022) ;
- le CAD amortit les krachs ;
- les données de fin de mois sous-estiment la baisse maximale de 0,6 à 5,3 points ;
- les probabilités à 10-15 ans reposent sur seulement 3 à 10 fenêtres indépendantes.
