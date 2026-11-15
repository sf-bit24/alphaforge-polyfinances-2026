# Croisement Amira · Mateo · Robert × analyse réglementaire : statuts, volonté vs capacité, BNC, 2022

> **Simulation historique uniquement, à partir de données publiques.** Ce document ne constitue pas un conseil financier
> personnalisé et n'entraîne aucune transaction. Les lignes `ORACLE` (`hindsight=True`) utilisent le futur : elles sont
> **non investissables**. Les portefeuilles BNC sont des **proxys** construits avec les cibles publiques (brochure BNI
> 2025-10, citée dans `00-cadre.md`), pas les rendements des fonds. Les réponses AMF des trois personas sont **inférées**
> (marquées (I) / [inf] dans l'analyse réglementaire). Tout ce qui suit est une proposition à trancher par l'équipe.

Chemins relatifs à `research/backtest/` (sauf mention). Moteur `engine_sha256 = 4d3e707a3271717d`, données
`data_sha256 = 008f122d5da4f8f7` (Mateo : `mateo_ext_5599152341587fba`, copie `analysis/mateo/data_ext` avec
`US_MKT_XEN`), graine 42. `engine/`, `data/` et les rapports des personas **ne sont pas modifiés**. Code :
`analysis/croisement/` ; profils générés : `profiles/x_*.yaml` (`make_profiles.py`) ; traces moteur :
`results/croisement_runs/<profil>/` ; synthèses : `results/croisement_analysis/`. L'analyse réglementaire
(`/mnt/c/Users/User/Desktop/ecole/hackoton/analyse/relation-profils-actifs/`) est lue seulement.

## 0. Références (chaque chiffre cite l'une d'elles)

| tag | fichier | contenu |
|---|---|---|
| [WC] | `results/croisement_analysis/will_vs_cap.json` | sélection robuste refaite sous la limite de volonté, contrôles de reproductibilité (`will_vs_cap.py`) |
| [BNC] | `results/croisement_analysis/bnc.json` | portefeuilles BNC sous les limites de chaque persona, CAD 1977+ et tickers 2021-11 → 2026-09 (`bnc.py`) |
| [CON] | `results/croisement_analysis/concordance.json` | poids par classe (robuste, ORACLE p10-p90), détention mois par mois de `Mom_etf_top3`, couverture ESGV (`concordance.py`) |
| [H22] | `results/croisement_analysis/hist2022.json` | années où actions et obligations baissent ensemble, corrélations par décennie (`hist2022.py`) |
| [STR] | `results/croisement_analysis/stress_anchor.json` (+ `stress_mateo_series.json`) | 2022 comme ancrage de catégorie : épisodes, rangs, bandes (`stress_anchor.py`, `stress_mateo.py`) |
| [REC] | `results/croisement_analysis/reconcile.json` | réconciliation pas à pas avec `quant/` (`reconcile.py`) |
| [RUN] | `results/croisement_runs/<profil>/<horodatage>_<mode>_h<N>.json` | traces moteur des relances (liste et commandes : `analysis/croisement/jobs.txt`) |
| [R-CN] / [R-CR] | `results/robert_cad/20261114T233723Z_non_overlapping_h4.json` / `…234006Z_rolling_h4.json` | Robert, version retenue (CAD 1977+) |
| [R-UN] / [R-UR] | `results/robert_long_usd/20261114T234617Z_non_overlapping_h4.json` / `…234412Z_rolling_h4.json` | Robert, USD 1926+ |
| [M-L] / [M-G] / [M-C] | `results/mateo_usd_long_esg/20261115T000606Z_rolling_h10.json`, `results/mateo_usd_gold_esg/20261114T235948Z_rolling_h10.json`, `results/mateo_cad_esg/20261114T234928Z_rolling_h10.json` | Mateo, trois ères ESG (règle inter-ères) |
| [A-E] / [A-U] | `results/amira_etf/20261114T22{4838,5010,5046}Z_*.json` / `results/amira_etf_long_usd/20261114T22{4857,5227,5343}Z_*.json` | Amira, six runs FNB (règle minimax du regret) |
| [REG] | `analyse/relation-profils-actifs/personas-tous.csv` (lignes AMIRA, MATEO, ROBERT), `personas-lot1.md` (§ AMIRA, MATEO, ROBERT), `10-synthese.md`, `quant/metriques_*.csv`, `quant/resultats.md` | analyse réglementaire (lecture seule) |

Contrôles de reproductibilité [WC, `check_vs_original`] : les relances ne changent que le comptage des violations et la
pénalité de l'ORACLE. Les lignes ex-ante sont identiques aux traces d'origine (écart maximal 0,0 pour Robert ; ≤ 2·10⁻⁶
pour Mateo, uniquement sur les optimiseurs SLSQP). **Les traces Amira du rapport datent d'avant le correctif glidepath**
(moteur `5aa2575a94cacf75`) : les contrôles `results/croisement_runs/amira_etf*/` (moteur actuel) ne diffèrent que sur
`G_E95_to_E65` (≤ 0,0016) et donnent le même choix robuste `Mom_etf_top3` (regret maximal 1,53 pt) [WC].

## 1. Question et méthode

Pour chaque persona officiel, on part de la stratégie robuste retenue par son rapport : Robert `eq20_gold10` (CAD,
`reports/robert.md` §5.4), Mateo `risk_parity_iv36` (règle inter-ères, `reports/mateo.md` §4), Amira `Mom_etf_top3`
(minimax du regret sur six runs FNB, `reports/amira.md` §4). On la confronte aux statuts de classe et au profil AMF / BNC
de l'analyse réglementaire [REG]. Mêmes univers, mêmes stratégies, mêmes règles de sélection ; **seule** la limite de
perte change quand la volonté AMF Q10 est plus basse que la capacité dérivée (31-103CP : le plus bas des deux).

## 2. Statuts → contraintes (B1)

Aucun statut « pas maintenant » pour ces trois personas [REG]. « exclu » → poids 0 (absent de l'univers) ; « limité » →
autorisé sous une condition explicite et un plafond ; « satellite » → petite part optionnelle (0 admis) ; « cœur » →
présence permanente.

| persona · classe | statut [REG] | traduction moteur | la stratégie robuste le respecte ? [CON] |
|---|---|---|---|
| Robert · actions CA | satellite (entreprises établies) | titres CA optionnels ; aucun titre CA dans l'univers 1977+ | oui : 0 titre (les 10 % de `CA_EQ` sont un FNB, XIU.TO) |
| Robert · actions US | limité (titre médiatisé → 13.3(2.1)) | poche ≤ 1 % (TSLA) ou 2 % (NVDA, SHOP.TO) (`reports/robert.md` §7) | oui : 0 secteur, 0 titre |
| Robert · FNB actions | cœur, part secondaire | présent, plus petit que les obligations | oui : 20,4 % contre 49,7 % d'obligations et 19,9 % d'encaisse |
| Robert · FNB oblig. | cœur | présent ; duration courte ou intermédiaire (R1 du rapport) | oui |
| Robert · or | limité (volatil, sans revenu) | plafond à fixer (l'analyse n'en donne pas) | **10,1 %** sans plafond défini → à trancher |
| Robert · crypto | exclu | `exclude: crypto, speculative` | oui |
| Mateo · actions CA | limité (énergie/pipelines filtrés ESG) | `exclude: fossil_fuel` (ENB.TO, CNQ.TO) | oui pour les titres ; `CA_EQ` (≈ XIU.TO) non filtré, 16,0 % en CAD (`assets_mean`), part énergie inconnue |
| Mateo · actions US | limité (controverses titre par titre) | secteurs = proxys de titres, sous condition | **non en USD** : 32,3 % en secteurs KF (USD 1926+), 31,0 % (USD 1975+), 8,1 % (CAD) |
| Mateo · FNB actions | cœur (ESGV) | `US_MKT_XEN` (marché US hors énergie) | oui (classe) ; ESGV lui-même non backtestable sur 10 ans (§5) |
| Mateo · FNB oblig. | cœur, dé-risquage avant l'échéance | bande d'actions [40 %, 80 %] | oui : 48,8 % (CAD) à 59,4 % (USD 1926+) |
| Mateo · or | limité (filière aurifère à documenter ESG) | 0 tant que la condition n'est pas remplie, ou plafond | **10,3 %** en CAD (1,2 % en USD 1975+) sans documentation ESG → à trancher |
| Mateo · crypto | exclu | `exclude: crypto` | oui |
| Amira · actions CA | satellite (secteurs hors tech) | ≤ 3 % par titre (`reports/amira.md` §3.2) | oui : 0 titre |
| Amira · actions US | satellite (titres tech) | ≤ 3 % par titre, tech look-through ≤ 30 % | oui en tickers (BusEq retiré des candidats) ; 13,4 % de BusEq en proxys (CAD) |
| Amira · FNB actions | cœur (« diversification réelle ») | présence permanente | **non** : 0 % d'actions dans 23,3 % des mois (CAD), 27,8 % (USD) |
| Amira · FNB oblig. | satellite (stabilisateur testé sur 2022) | petite part | **non** : obligations + encaisse 38,1 % en moyenne mensuelle (CAD 1978-2026), 61,3 % (USD 1927-2026) |
| Amira · or | satellite | petite part | 10,8 % en moyenne sur les fenêtres (13,1 % mois par mois), mais ≥ 1/3 dans 36,7 % des mois (CAD) → à trancher |
| Amira · crypto | limité (après le drawdown 2022) | ≤ 3 % rééquilibré chaque mois, 1 % sinon (`reports/amira.md` §3.3) | oui : 0 % au cœur, option 3 % |

Sources des poids : `results/croisement_analysis/concordance.json` → `robert.cad_rolling_h4`, `mateo.{usd_long,usd_gold,cad}`,
`amira.etf_cad_rolling_h15` / `etf_usd_rolling_h15` (moyenne sur les fenêtres) et `amira_holdings` (mois par mois,
simulation sur une seule longue fenêtre 1978-03 → 2026-09 en CAD et 1927-10 → 2026-09 en USD, 0 mois de repli).

## 3. Volonté vs capacité (31-103CP, le plus bas des deux) (B2)

| persona | volonté (AMF Q10 [REG]) | capacité dérivée (rapport) | appliquée | qui gagne |
|---|---|---|---|---|
| Robert | « 5 % » → 2 **(I)** ; Q3 lu littéralement (< 5 ans) → AMF 1 → palier 0 % | maxDD 0,23 et CVaR5 0,036 à 4 ans (`reports/robert.md` §4) | **0,05** (CVaR 0,036 gardée) | **volonté** |
| Mateo | « 15 % » → 3 **(I)** (plafond Q10) | vol 0,10 et maxDD 0,20 à 10 ans (`reports/mateo.md` §2) | **0,15** (vol 0,10 gardée) | **volonté** |
| Amira | « > 30 % » → 5 **(I)** ; profil final 4 plafonné par **Q5** (connaissances) | maxDD 0,40 à 15 ans (`reports/amira.md` §3.1) | **0,40** (Q10 ne lie pas) ; sensibilité 0,30 = palier Q10 du profil 4 | **capacité** |

### 3.1 Effet sur la stratégie robuste (relances, mêmes univers et stratégies)

| exécution [RUN] | limite | choix robuste | p10 réel | médiane | P(perte réelle) | actions (moy.) | éligibles |
|---|---|---|---|---|---|---|---|
| Robert CAD roulant 4 ans ([R-CR]) | capacité 0,23 | `eq20_gold10` | +1,53 % | +4,16 % | 0,065 | 0,204 | 8 |
| idem (`x_robert_cad_w05/20261115T003250Z_rolling_h4.json`) | **volonté 0,05** | **`cash_100`** | **−0,98 %** | +1,42 % | **0,304** | **0** | 1 |
| idem (`x_robert_cad_amf1/20261115T003324Z_rolling_h4.json`) | AMF 1 (Q3 littéral), 0,00 | `cash_100` | −0,98 % | +1,42 % | 0,304 | 0 | 1 |
| Robert CAD non chevauchant ([R-CN] → `x_robert_cad_w05/…003032Z`) | 0,23 → 0,05 | `eq20_gold10` → `cash_100` | +2,83 % → −0,96 % | | 0,083 → 0,333 | 0,204 → 0 | 11 → 1 |
| Robert USD 1926+ roulant ([R-UR] → `x_robert_long_usd_w05/…003449Z`) | 0,23 → 0,05 | `eq20_2y` → `min_variance_60m` | −1,64 % → −2,91 % | | 0,216 → 0,371 | 0,204 → 0,033 (43 % d'encaisse) | 8 → 3 |
| Mateo, règle inter-ères ([M-L], [M-G], [M-C]) | capacité 0,20 | `risk_parity_iv36` | pire p10 −0,15 % (CAD 3,81 %) | | max 0,121 | 0,409 | 5 |
| idem (`x_mateo_*_esg_w15/…`) | **volonté 0,15** | **`min_variance_60`** | **pire p10 −0,42 % (CAD 2,06 %)** | | max 0,165 | 0,412 | **2** |
| Mateo, CAD seul (devise de Mateo) | 0,20 → 0,15 | `static_eq60_gold` → `dual_mom12_top2` | 4,15 % → 3,93 % | | | 0,605 → 0,467 | |
| Amira, minimax du regret (6 runs, contrôles moteur actuel) | capacité 0,40 | `Mom_etf_top3` | p10 minimal 0,95 %, regret max 1,53 pt | | | 0,48 (CAD) | 4 partout |
| idem (`x_amira_etf*_w30/…`) | sensibilité 0,30 | `RP_invvol_36m` (seule éligible partout) | p10 minimal −1,35 %, regret max 2,96 pt | | | 0,33 (CAD), 0,16 (USD) | 1 |

Sources : [WC] → `robert.*`, `mateo.{capacite_0.20,volonte_0.15}.agg` et `per_era`, `amira.*.table` et `per_run` ;
poids d'actions de `RP_invvol_36m` sous 0,30 lus dans les mêmes traces [RUN] (`x_amira_etf_w30/20261115T003107Z_rolling_h15.json` :
0,332 ; `x_amira_etf_long_usd_w30/20261115T003136Z_rolling_h15.json` : 0,160).

**Robert.** La volonté (5 %) gagne largement sur la capacité (23 %). Sous 0,05, la seule stratégie éligible en CAD est
l'encaisse : la part d'actions passe de 20 % à 0, le p10 réel de +1,53 % à −0,98 %/an, et la probabilité de perdre du
pouvoir d'achat sur 4 ans de 6,5 % à 30,4 % [WC]. Le portefeuille robuste `eq20_gold10` a une pire baisse de 0,097 sur
les 46 fenêtres [WC → `robert_cad|rolling|capacite_0.23`] : il passerait une limite de 10 %, mais les paliers AMF Q10 sont
5 % et 15 %. **Ambiguïté Q3** : la lecture littérale (AMF 1, limite 0) donne exactement le même résultat (encaisse) que
Q10 = 5 % [WC]. Elle ne change donc la réponse que si Q10 est remesuré plus haut. Dans ce cas, Q3 littéral ramènerait à
l'encaisse alors que Q10 = 15 % permettrait `eq20_gold10`. L'incohérence « préserver le capital (en réel) » contre
« ne tolérer que 5 % » doit être **signalée** (31-103CP), pas corrigée en silence. L'ORACLE suit la même pente : sous la
limite 0, sa part d'actions tombe à p10-p90 = 0,009-0,128, contre 0,192-1,000 sous la capacité [WC].

**Mateo.** La volonté (15 %) gagne. Sous 0,15, `risk_parity_iv36` viole la limite dans 33,0 % des fenêtres USD 1926+ et
21,4 % des fenêtres USD 1975+ (contre 7,7 % et 0 % à 0,20). Le choix inter-ères devient `min_variance_60` : la part
d'actions ne bouge pas (0,41, collée au plancher de la bande), mais le p10 CAD baisse de 1,75 pt (3,81 % → 2,06 %) [WC].
**Tension** : même le plancher de la bande (`static_eq40`) viole 0,15 dans 37,4 % des fenêtres USD 1926+ et 28,6 % des
fenêtres USD 1975+ (0 % en CAD) [WC → `breach_by_era`]. Une volonté de 15 % est donc incompatible avec la bande
d'actions [40 %, 80 %] dérivée pour Mateo, sauf à ne juger que l'ère CAD.

**Amira.** Q10 « > 30 % » ne lie pas : la capacité 0,40 s'applique et rien ne change. En sensibilité, si l'équipe lit le
profil final AMF 4 comme « perte tolérable de 30 % », `Mom_etf_top3` devient inéligible en CAD (pire baisse 0,304, à
0,4 pt de la limite, d'où 31-37 % de fenêtres en violation) et la règle minimax dégénère vers `RP_invvol_36m`, avec 16 à
36 % d'actions, ce qui n'a pas de sens pour un profil de croissance [WC]. Ce résultat est un effet de seuil, pas une
recommandation.

## 4. Portefeuilles BNC publics sous les limites de chaque persona (B4)

Proxys : revenu fixe → `CA_GOV_10Y`, actions canadiennes → `CA_EQ`, actions mondiales → `US_MKT` (pas d'indice mondial
hors États-Unis dans les données, hypothèse déclarée). CAD 1977+, rééquilibrage annuel, 10 pb. BNC robuste = meilleur p10
réel parmi les BNC qui respectent la tolérance de violation du persona (Robert 10 %, Mateo 25 %, Amira 10 %).
Les fenêtres sont identiques à celles de la stratégie robuste du persona (`same_windows = true`) [BNC].

**p10 réel / pire maxDD / taux de violation, roulant** [BNC] (traces `x_bnc_*/…_rolling_h{4,10,15}.json`) :

| BNC | Robert, capacité (H 4) | Robert, oblig. courtes¹ | Robert, volonté 0,05 | Mateo, capacité (H 10) | Mateo, volonté 0,15 | Amira, capacité (H 15) | Amira, 0,30 |
|---|---|---|---|---|---|---|---|
| Prudent 80/6/14 | −1,47 % / 0,154 / 15 % | +0,32 % / 0,091 / 0 % | 48 % | 2,97 % / 0,154 / 0 % | 10 % | 2,78 % / 0 % | 0 % |
| Conservateur 70/9/21 | −0,15 % / 0,152 / **26 %** (CVaR) | **+0,74 % / 0,101 / 0 %** | 65 % | 2,68 % / 0,152 / 0 % | 10 % | 3,57 % / 0 % | 0 % |
| Pondéré 55/13,5/31,5 | +1,07 % / 0,157 / 43 % | +0,67 % / 39 % | 76 % | 3,57 % / 0,157 / 10 % | **3,57 % / 20 %** | 4,11 % / 0 % | 0 % |
| Équilibré 40/18/42 | +0,62 % / 0,193 / 63 % | 57 % | 85 % | **3,63 % / 0,193 / 17,5 %** | 77,5 % | **4,27 % / 0 %** | **4,27 % / 0 %** |
| Croissance 20/24/56 | 74 % | 74 % | 100 % | 82,5 % | 87,5 % | 3,95 % / 0,304 / 0 % | 34 % |
| Actions 0/30/70 | 89 % | 89 % | 100 % | 95 % | 95 % | 34 % | 60 % |
| **BNC robuste** | **aucun** | **Conservateur** | **aucun (encaisse)** | **Équilibré** | **Pondéré** | **Équilibré** | **Équilibré** |
| stratégie robuste du persona, mêmes fenêtres | `eq20_gold10` 1,53 % | | | `risk_parity_iv36` 3,81 % | | `Mom_etf_top3` 5,16 % | |

¹ Sensibilité : revenu fixe = 50 % `CA_GOV_10Y` + 50 % `CA_TBILL` (`x_bnc_robert_cap_court`). Les violations de Robert
viennent surtout de la **CVaR mensuelle** (0,036) ; la baisse maximale ne lie que pour Croissance et Actions : Conservateur dépasse la CVaR dans 26 % des fenêtres,
mais sa pire baisse (0,152) reste sous 0,23 [BNC → `breach_types`].

Non chevauchant [BNC] : Robert capacité → Prudent (seul éligible, p10 −1,56 %) ; oblig. courtes → Conservateur (p10 1,02 %) ;
Mateo capacité → Équilibré (5,68 %), volonté → Pondéré (5,28 % ; Équilibré dépasse une limite dans les 4 décennies, la maxDD de 0,15 dans 3) ;
Amira capacité → **Croissance** (7,23 %, 3 fenêtres), 0,30 → Équilibré (6,20 %).

Contraintes dures hors limites de perte [BNC → `constraints`] : la bande d'actions de Mateo [40 %, 80 %] exclut Prudent
(20 %), Conservateur (30 %) et Actions (100 %). Le plafond tech look-through d'Amira (30 %) est dépassé par Actions à
2026-09 (0,70 × 0,4355 = 0,305) mais pas par Croissance (0,244).

**Période réelle XBB.TO / XIU.TO / SPY, 2021-11 → 2026-09, 59 mois** [BNC → `tickers_2021_11_2026_09`] : réel annualisé
Prudent −0,09 %, Conservateur +1,33 %, Pondéré +3,46 %, Équilibré +5,57 %, Croissance +8,39 %, Actions +11,19 % ; pire
baisse 0,131 à 0,160. **Aucun BNC ne respecte la CVaR de Robert** (Prudent 0,0363, Conservateur 0,0388 contre 0,036),
alors que sa stratégie retenue en tickers fait 0,0273 (`reports/robert.md` §8). Croissance et Actions dépassent la vol de
Mateo (0,1066 et 0,1221 contre 0,10). Une seule trajectoire, plus courte que les horizons de Mateo et d'Amira.

| persona | BNC assigné [REG] | BNC le plus robuste ici | verdict |
|---|---|---|---|
| Robert | Conservateur | aucun avec un revenu fixe de type 10 ans (CVaR) ; **Conservateur** si le revenu fixe est court ; aucun sous la volonté 0,05 | **concordance conditionnelle** : vrai seulement avec un revenu fixe court et la limite de capacité |
| Mateo | Équilibré (Pondéré si la date est rigide) | Équilibré sous la capacité ; **Pondéré** sous la volonté 0,15 | **concordance partielle** : c'est la parenthèse « Pondéré » qui sort quand la règle du plus bas s'applique |
| Amira | Croissance | Croissance en non chevauchant (3 fenêtres) ; **Équilibré** en roulant (4,27 % contre 3,95 %) et sous 0,30 | **concordance partielle**, un cran plus prudent dans 3 exécutions sur 4 |

Les trois stratégies robustes battent le meilleur BNC éligible sur les mêmes fenêtres : 1,53 % contre aucun BNC éligible
(Robert), 3,81 % contre 3,63 % (Mateo), 5,16 % contre 4,27 % (Amira) [BNC → `persona_robust_same_windows`]. L'or y
contribue : il est absent des BNC.

## 5. Tableau de concordance persona × classe (B3)

Poids robuste = moyenne sur les fenêtres roulantes de la version retenue. Plage ORACLE = p10-p90 du poids de la classe
dans l'ORACLE des mêmes fenêtres (`hindsight=True`). Robert : [R-CR], 46 fenêtres ; Mateo : [M-C] (CAD, 40), [M-L]
(USD 1926+, 91) ; Amira : [A-E] roulant 15 ans (CAD, 35), [A-U] (USD, 86). Source : [CON].

| persona · classe | statut [REG] | poids robuste | ORACLE p10-p90 | verdict | explication |
|---|---|---|---|---|---|
| Robert · actions CA | satellite | 0 (titres) | non testable (aucun titre CA en 1977+) | cohérent (non testé) | satellite = 0 admis ; sur 2021-2026, l'ORACLE en tickers met 29 % sur RY.TO (une seule fenêtre, `reports/robert.md` §8) |
| Robert · actions US | limité | 0 ; poche médiatisée ≤ 1-2 % | secteurs défensifs 0-83 % | cohérent | l'ORACLE aime les secteurs défensifs a posteriori (proxy « entreprises établies »), pas le titre médiatisé ; plafond dérivé par CVaR |
| Robert · FNB actions | cœur, part secondaire | 20,4 % | 0-71 % (actions totales 19-100 %) | cohérent | sous la volonté 0,05 : **0 %** → contradiction avec « cœur » (§3) |
| Robert · FNB oblig. | cœur | 49,7 % + 19,9 % d'encaisse | 0-58 % (encaisse 0-28 %) | cohérent | jamais optimales a posteriori de façon stable, mais nécessaires au pire cas ; sous 0,05 : 100 % encaisse |
| Robert · or | limité | **10,1 %** | 0-47 % (> 5 % dans 46 % des fenêtres) | **à trancher** | « peu utile à court horizon » [REG] contre p10 de −0,47 % à 0 % d'or et +1,53 % à 10 % (`reports/robert.md` §6), résultat marqué fragile (R6) |
| Robert · crypto | exclu | 0 | hors univers | cohérent | |
| Mateo · actions CA | limité (filtre ESG) | 0 (titres fossiles exclus) | hors univers | cohérent | mais `CA_EQ` / XIU.TO non filtré (16,0 % en CAD, [CON] → `mateo.cad.assets_mean`) : part énergie inconnue |
| Mateo · actions US | limité (controverses) | 8,1 % (CAD) ; **32,3 % (USD 1926+)** | 0-80 % (CAD) ; 40-80 % (USD) | **contradiction (artefact)** | `project()` remplit le plancher d'actions de 40 % à parts égales entre les 11 secteurs (`reports/mateo.md` §4) : « limité » devient le premier bloc d'actions en USD. En tickers (ESGV / XIU.TO), 0 titre |
| Mateo · FNB actions | cœur (ESGV) | 32,8 % (CAD) ; 8,4 % (USD) | 0-40 % (CAD) ; 0-0 % (USD) | **à trancher** | ESGV : 97 mois (2018-10 → 2026-10), **0 fenêtre complète de 10 ans** ; corrélation mensuelle avec SPY 0,9932, écart +0,05 pt/an (2018-10 → 2026-09, USD) [CON → `mateo_esgv`] : le label ESG n'est pas testable |
| Mateo · FNB oblig. | cœur | 48,8 % (CAD) ; 59,4 % (USD) | 0-46 % (CAD) ; 0-60 % (USD) | cohérent | le pire cas en a besoin ; l'ORACLE n'en veut pas toujours |
| Mateo · or | limité (filière ESG) | **10,3 % (CAD)** ; 1,2 % (USD 1975+) | 0-60 % (CAD) | **à trancher** | condition « filière documentée » non remplie dans nos données ; 9,9 % de GLD en tickers (`reports/mateo.md` §9) |
| Mateo · crypto | exclu | 0 | hors univers | cohérent | |
| Amira · actions CA | satellite (hors tech) | 0 (titres) ; `CA_EQ` 16,7 % | — | cohérent (non testé) | aucun titre CA dans l'univers FNB |
| Amira · actions US | satellite (titres tech) | BusEq 13,4 % (CAD), 16,6 % (USD) | 0-27 % (CAD) ; 0-26 % (USD) | cohérent | en tickers, BusEq est retiré des candidats ; titres ≤ 3 % chacun |
| Amira · FNB actions | cœur (« diversification réelle ») | 34,8 % (CAD) ; 22,1 % (USD) | 19-100 % (CAD) ; 0-100 % (USD) | **contradiction (structure)** | `Mom_etf_top3` ne tient que 3 actifs (n effectif médian 3,13) et **0 % d'actions dans 23,3 % des mois (CAD), 27,8 % (USD)** ; il couvre ≥ 2 classes dans 89,5 % des mois et ≥ 3 dans 67,4 % [CON → `amira_holdings`] : diversifié entre classes, pas un cœur permanent |
| Amira · FNB oblig. | satellite | 30,9 % + 10,2 % d'encaisse (CAD) ; 40,9 % + 20,4 % (USD) | 0-25 % (CAD) ; 0-70 % (USD) | **contradiction** | ce n'est pas une « petite part » ; en 2022, le stabilisateur a été l'encaisse (37,1 % en moyenne) et pas les obligations (2,9 %) [CON] |
| Amira · or | satellite | 10,8 % (moyenne) | 0-68 % | **à trancher** | ≥ 1/3 du portefeuille dans 36,7 % des mois [CON] ; déjà signalé (`reports/amira.md` §6) |
| Amira · crypto | limité | 0 ; option 3 % (mensuel) / 1 % (annuel) | non testable avant 2014 | cohérent | BTC −61,8 % en 2022 (moteur, [REC]) : la « démonstration du drawdown 2022 » exigée est disponible |

**Bilan** : Robert 5 cohérents, 1 à trancher, 0 contradiction (sous la capacité ; 2 contradictions sous la volonté 0,05 :
FNB actions et FNB oblig. « cœur » tombent à 0). Mateo 3 / 2 / 1. Amira 3 / 1 / 2.

Alternatives pour Amira, mêmes runs [WC → `amira.controle_0.40_moteur_actuel.per_run`] : `Trend10_E80` (p10 minimal 1,84 %,
regret maximal 2,18 pt, mais 0 % d'actions dans 14,6 % des mois en CAD et 27,0 % en USD [CON]) ; `Mom_etf_top3_core50`
(jamais sous 50 % de cœur, ≥ 3 classes dans 100 % des mois, p10 CAD roulant 5,28 %, mais 16,7 % de violations en USD non
chevauchant, donc exclue du minimax) ; statique `E80_us50_g10_t0` (p10 CAD roulant 4,70 %, toujours 72-85 % d'actions).

## 6. Le constat 2022 de l'analyse (« défensive ≈ offensive ») dans l'histoire longue

Leur constat [REG `10-synthese.md` §4.4] : en 2022, Conservateur −11,2 %, Équilibré −10,9 %, Actions −10,7 %. On le
reproduit exactement en mensuel avec les tickers (−11,21 / −10,90 / −10,69 %, rééquilibrage mensuel), et la corrélation
mensuelle XBB.TO-SPY de 2022 vaut 0,684 [H22].

**Fréquence des années où actions et obligations baissent ensemble** (années civiles complètes) [H22] :

| ère | paire | années | années où les deux baissent | lesquelles |
|---|---|---|---|---|
| USD 1927-2025 | US_MKT / UST_10Y | 99 | **4 (4,0 %)** | 1941 (−10,6 % / −1,8 %), 1969 (−11,0 % / −5,4 %), 1994 (−0,2 % / −7,1 %), **2022 (−19,9 % / −16,4 %)** |
| USD 1927-2025 | US_MKT / UST_5Y | 99 | 5 | |
| CAD 1977-2025 | CA_EQ / CA_GOV_10Y | 49 | **1 (2,0 %)** : 2022 (−5,7 % / −10,2 %) | |
| CAD 1977-2025 | US_MKT en CAD / CA_GOV_10Y | 49 | 2 | |

**BNC sur proxys, CAD 1977-2025** [H22 → `bnc_cad_1977`] : sur les 11 années où Actions perd, Conservateur est **positif
dans 10** (par exemple 2008 : +0,45 % contre −25,2 % ; 2002 : +0,15 % contre −19,1 %). 2022 est la seule année où les deux
perdent (−10,5 % contre −11,8 %). Le constat 2022 est donc **rare à l'échelle annuelle** (1 année sur 49 en CAD).

**Corrélation mensuelle actions / obligations par décennie** [H22 → `decade_corr_*`] :

| décennie | USD (US_MKT / UST_10Y) | part des fenêtres de 36 mois à corrélation > 0 | CAD (CA_EQ / CA_GOV_10Y) | part > 0 |
|---|---|---|---|---|
| 1930s | +0,13 | 0,35 | — | — |
| 1940s | +0,12 | 0,88 | — | — |
| 1950s | −0,08 | 0,38 | — | — |
| 1960s | +0,16 | 0,73 | — | — |
| 1970s | **+0,33** | 0,98 | +0,14 (1977-79) | 1,00 |
| 1980s | +0,26 | 0,98 | +0,31 | 0,99 |
| 1990s | +0,31 | 1,00 | **+0,40** | 1,00 |
| 2000s | −0,25 | 0,08 | −0,07 | 0,44 |
| 2010s | **−0,49** | 0,00 | −0,18 | 0,15 |
| 2020s (→ 2026-09) | +0,28 | 0,62 | +0,04 | 0,54 |

**Lecture.** La perte conjointe sur une année civile est rare, mais une corrélation actions-obligations **positive**
a été la norme de 1970 à 1999 : 97,5 à 100 % des fenêtres de 36 mois. La protection des obligations dans les krachs est
un phénomène des années 2000-2010. 2022 marque un retour à un régime ancien, pas une anomalie. La phrase « ce qui
changerait la réponse » doit donc dire : *si l'inflation et les taux montent, les obligations agrégées ne protègent
pas* ; c'est ce qu'ont fait les années 1970-1990. Réserve : les obligations synthétiques construites sur des taux moyens
mensuels (avant 1962 et `CA_GOV_10Y`) ont une volatilité sous-estimée.

### 6.1 Le stress 2022 comme ancrage de la catégorie de risque (demande du 2026-11-15)

Le document `brain/product/questionnaire-profil.md` (origin/master, commit a65a0b3, lignes ≈ 159-178, lu seulement)
définit la catégorie comme « la bande la plus élevée dont la perte au stress 2022 tient dans L ». On teste cette règle sur
les 6 BNC et nos 3 stratégies robustes, simulées sur **une seule longue fenêtre** avec le moteur (`run_window`, mêmes
paramètres que les profils) [STR].

**Pertes (fraction positive), CAD 1977-2026** [STR → `CAD`] :

| portefeuille | 2022 civil | 1980-82 | 1987 | 2000-02 | 2007-09 | 2020 | 2022 creux | pire épisode | p90 maxDD 4 / 10 / 15 ans | CVaR95 12 mois |
|---|---|---|---|---|---|---|---|---|---|---|
| Prudent | 10,6 % | 10,6 % | 7,4 % | 2,5 % | 3,7 % | 0 % | 15,0 % | 15,0 % (2022) | 11,8 / 12,2 / 14,0 % | 6,2 % |
| Conservateur | 10,8 % | 10,9 % | 9,5 % | 3,3 % | 6,1 % | 0,6 % | 15,3 % | 15,3 % (2022) | 11,0 / 11,5 / 13,6 % | 5,6 % |
| Pondéré | 11,0 % | 11,2 % | 13,0 % | 10,3 % | 11,8 % | 4,1 % | 15,8 % | 15,8 % (2022) | 13,0 / 13,3 / 14,7 % | 6,9 % |
| Équilibré | 11,3 % | 11,5 % | 17,6 % | 19,1 % | 18,2 % | 7,7 % | 16,3 % | 19,1 % (2000-02) | 17,9 / 19,1 / 19,1 % | 9,9 % |
| Croissance | 11,6 % | 13,7 % | 23,5 % | 29,9 % | 26,7 % | 12,4 % | 16,8 % | 29,9 % (2000-02) | 25,7 / 30,2 / 30,2 % | 14,9 % |
| Actions | 11,9 % | 19,5 % | 28,9 % | 39,7 % | 36,3 % | 17,2 % | 17,4 % | 39,7 % (2000-02) | 34,6 / 40,2 / 40,2 % | 20,7 % |
| Robert `eq20_gold10` | 6,2 % | 6,7 % | 5,9 % | 1,9 % | 4,0 % | 0 % | 9,9 % | 9,9 % (2022) | 7,3 / 7,5 / 8,8 % | 3,2 % |
| Mateo `risk_parity_iv36` (1980+) | 6,5 % | 8,8 % | 11,2 % | 4,5 % | 5,5 % | 2,1 % | 10,8 % | 11,2 % (1987) | 10,8 / 11,2 / 11,2 % | 4,7 % |
| Amira `Mom_etf_top3` (1978+) | 11,4 % | 13,6 % | **28,5 %** | 19,6 % | **2,6 %** | 7,0 % | 14,9 % | 28,5 % (1987) | 19,6 / 30,4 / 30,4 % | 17,3 % |

En USD 1926+ (revenu fixe `UST_10Y`, toutes les actions `US_MKT`) [STR → `USD`] : 2022 civil de 17,1 % (Prudent) à 19,9 %
(Actions) ; 1929-32 de 18,1 % à **83,7 %** ; 1973-74 de 10,3 % à 46,5 % ; 2007-09 de 7,6 % à 50,3 %.

**2022 est-il discriminant ?** [STR → `CAD_rank_tests`, `USD_rank_tests`]

- **En rang, oui** : entre les 6 BNC, le rang de la perte 2022 est le même que celui de 2000-02, 2007-09, 1987 et du
  p90 de la maxDD (ρ de Spearman = 0,94 à 1,00 en CAD et en USD). Seul 1994 s'inverse (ρ = −1). Entre les 9
  portefeuilles en CAD, ρ(2022, 2007-09) tombe à 0,60 : le momentum d'Amira perd en 2022 autant que Croissance
  (11,4 % contre 11,6 %), mais seulement 2,6 % en 2007-09, contre 26,7 %.
- **En niveau, non** : l'écart entre Prudent et Actions vaut **1,3 pt en CAD** (10,6 % → 11,9 %) et 2,8 pt en USD.
  Pour le pire épisode, il vaut **24,7 pt en CAD** (15,0 % → 39,7 %) ; pour le p90 de la maxDD à 10 ans, 28,7 pt
  (11,5 % → 40,2 %).
  Le rapport Actions / Prudent vaut 1,1 en 2022, contre 15,9 en 2000-02 et 9,8 en 2007-09 (CAD).
  Or la règle du document compare un **niveau** à L : dès que L ≥ 11,9 %, toutes les bandes passent.

**Bande obtenue par chaque persona selon l'ancrage** (CAD 1977+, bande la plus haute dont la perte ≤ L) [STR → `CAD_bands`] :

| L | stress 2022 civil | pire épisode CAD 1977+ | p90 maxDD à l'horizon de la poche |
|---|---|---|---|
| Robert, capacité 0,23 | **Actions** | Équilibré | Équilibré (4 ans) |
| Robert, volonté 0,05 | aucune (encaisse) | aucune | aucune |
| Mateo, capacité 0,20 | **Actions** | Équilibré | Équilibré (10 ans) |
| Mateo, volonté 0,15 | **Actions** | Prudent (limite : 2022 creux 0,1498) | **Pondéré** (10 ans) |
| Amira, capacité 0,40 | Actions | Actions (0,397) | **Croissance** (15 ans) |
| Amira, 0,30 | Actions | Croissance | Équilibré (15 ans) |

En USD 1926+, le pire épisode (1929-32) ramène Amira (0,40) à Conservateur, et le stress 2022 en USD exclut tous les BNC
pour Mateo à 0,15 (Prudent 17,1 % > 15 %) [STR → `USD_bands`]. 1929-32 est un scénario informatif (déjà le cas dans
`risk_levels_v0.2.yaml`, `stress_informational`), pas un budget pour un investisseur en CAD.

**Ancrage alternatif proposé (chiffré)** : la **perte maximale au creux sur un jeu d'épisodes CAD 1977+** (1980-82, 1987,
1994, 2000-02, 2007-09, 2020, 2022), comparée à L, puis le **p90 de la maxDD à l'horizon de la poche** comme contrôle.
2022 reste dans le jeu, car c'est l'épisode qui lie pour Prudent, Conservateur et Pondéré (15,0 / 15,3 / 15,8 %), mais il
ne décide plus seul. L'écart entre les bandes passe de 1,3 pt à 24,7 pt. Les bandes obtenues (Mateo Équilibré à la
capacité et Pondéré à la volonté, Amira Croissance) recoupent les choix BNC du §4. Cela concorde avec la calibration de
l'équipe (`origin/docs/portfolio-construction:research/calibration/README.md` : « la perte de 2022 ne sépare pas les
niveaux »), dont nous n'avons pas recalculé les chiffres.

## 7. Réconciliation des chiffres 2021-2026 (B5)

Leur méthode (`quant/stats_classes.py` : calendrier TSX ∪ US de 1 282 jours, report du dernier prix, `adj_close` ×
usdcad avec 37 jours de change reportés) est ré-implémentée dans `analysis/croisement/reconcile.py` et **reproduit leurs
chiffres à l'identique** (étape 2 = étape 1 pour tous les actifs) [REC]. On fait ensuite varier un facteur à la fois.

| actif | utilisé par | CAGR : leur → fin 2026-09 → départ 2021-11-30 → **moteur 58 mois** (59 mois) | vol : quotidienne → **mensuelle** | maxDD : leur → fin 2026-09 → **mensuel** | 2022 : leur / **moteur** |
|---|---|---|---|---|---|
| XIU.TO | Robert, Mateo, Amira | 13,66 → 13,05 → 14,25 → **14,25** (13,76) | 12,92 → **12,36** | 16,36 → 16,36 → **14,28** | −6,35 / **−6,35** |
| SPY | Robert, Amira | 14,47 → 14,91 → 15,25 → **15,24** (15,51) | 16,50 → **13,46** | 22,25 → 22,25 → **18,67** | −12,59 / **−12,59** |
| ESGV | Mateo | 12,86 → 13,46 → 13,92 → **13,92** (14,14) | 17,85 → **14,84** | 26,86 → 26,86 → **22,79** | −18,85 / **−18,85** |
| XBB.TO | Robert, Mateo, Amira | 0,71 → 0,40 → 0,26 → **0,26** (0,41) | 6,57 → **6,25** | 15,48 → 15,48 → **13,01** | −11,66 / **−11,66** |
| ZST.TO | Robert, Amira | 3,41 → 3,45 → 3,48 → **3,48** (3,43) | 0,55 → **0,62** | 0,43 → 0,43 → **0,41** | +1,22 / **+1,22** |
| AGG | Mateo, Amira | 2,24 → 1,89 → 1,45 → **1,45** (2,13) | 7,31 → **5,95** | 12,75 → 12,75 → **10,14** | −7,08 / **−7,08** |
| TLT | Amira (candidat) | −5,94 → −6,79 → −7,75 → **−7,75** (−6,51) | 15,88 → **13,00** | 39,73 → 39,73 → **37,15** | −26,54 / **−26,54** |
| GLD | Robert, Mateo, Amira | 18,21 → 20,30 → 21,40 → **21,39** (21,60) | 18,22 → **16,56** | 26,00 → **23,67** → **21,02** | +6,01 / **+6,01** |
| BTC-USD | Amira (option 3 %) | 4,76 → 8,22 → 10,58 → **10,58** (9,46) | 50,29 → **53,73** | 73,66 → 73,66 → **69,27** | −61,70 / **−61,82** |
| CNQ.TO | contrôle | 28,68 → 28,26 → 28,47 → **27,89** (27,18) | 30,37 → **28,51** | 33,11 → 33,11 → **20,62** | **+52,92 / +49,69** |

(en %, CAD ; source [REC] → `assets.<ticker>.steps`.) Portefeuilles BNC de leur tableau : Conservateur 4,73 / 6,78 /
15,16 / −11,21 % chez eux, contre 4,60 / 7,38 / 13,43 / −11,21 % au moteur mensuel ; Équilibré 8,82 / 9,42 / 16,45 /
−10,90 contre 9,02 / 9,26 / 14,51 / −10,90 ; Actions 14,35 / 14,47 / 18,70 / −10,69 contre 15,06 / 12,34 / 16,00 /
−10,69 [REC → `mixes`].

Explication des écarts :
1. **Date de fin** (2026-11-12 contre 2026-09-30) : c'est l'essentiel de l'écart pour GLD (CAGR 18,21 → 20,30 % ; maxDD
   0,260 → 0,237, le creux du 2026-10-30 est hors fenêtre) et pour BTC (4,76 → 8,22 %).
2. **Mois de départ** (2021-11-12 contre 2021-11-30) : 14,25 % au lieu de 13,05 % pour XIU.TO. Le moteur à 59 mois part de
   fin octobre 2021 (yfinance).
3. **Fréquence** : la vol mensuelle × √12 est plus basse que la vol quotidienne × √252 (SPY 16,50 → 13,46 %), et la
   maxDD mensuelle ne voit pas les creux intra-mois (SPY 0,2225 → 0,1867). Seule exception : BTC, dont la vol mensuelle
   est plus haute (53,73 % contre 50,29 %).
4. **Change** : même source BdC ; en fin de mois, le moteur et leur série donnent le même rendement (étape 5 = étape 6
   à 0,01 pt près pour tous les actifs, sauf la crypto et CNQ.TO). Les rendements 2022 sont identiques pour tous les FNB.
5. **Crypto 7/7** : en août 2022, BTC fait −12,16 % au moteur (fin de mois civile, 31 juillet = dimanche) et −13,89 % sur
   leur calendrier de bourse (29 juillet) ; d'où 2022 −61,82 % contre −61,70 %.
6. **CNQ.TO** : le 2022-08-22, `adj_close` fait +2,78 % et `close` +0,60 %. L'ajustement « split 1,021 » compte deux fois
   le dividende spécial. Le moteur corrige le mois d'août 2022 (+3,97 % contre +6,21 % dans le starter brut), d'où
   2022 +49,69 % contre +52,92 %, et −0,57 pt/an de CAGR à période égale (28,47 → 27,89 %). **Leur note de
   `quant/resultats.md` (« aucune correction appliquée ») est à corriger** : l'écart d'environ 2,2 pts n'est pas un « saut
   aberrant » au sens de leur test (top 3 des variations quotidiennes), c'est un double comptage. CNQ.TO n'est dans aucune
   des trois stratégies robustes, mais il est dans le panier « Actions canadiennes » de leur `10-synthese.md`.

## 8. Synthèse transversale sur 6 personas (Robert, Mateo, Amira + p12 Julien, p14 Tyler, p35 Denise)

Sources : ce rapport et les parties B de `reports/p12-julien.md` (§9), `reports/p14-tyler.md` (§10) et `reports/p35-denise.md` (§8, §11).

**Volonté contre capacité (9 poches).** La volonté gagne dans **4** poches : p12 accumulation (0,30 contre 0,305, de
peu), p35 B (0,15 contre 0,39), Robert (0,05 contre 0,23) et Mateo (0,15 contre 0,20). La capacité gagne dans **4** :
p12 décaissement (0,252), p14 études (0,20), p35 A (0) et Amira (0,40). Il y a **1** égalité (p14 retraite, 0,30).
**Toutes les volontés sont inférées** (Q10 (I) / [inf] dans les 6 fiches). Quand la volonté gagne, l'effet est fort :
la part d'actions de p35 B passe de 60 % à environ 35-40 %, celle de Robert de 20 % à 0 %, et Mateo perd 1,75 pt de p10
en CAD. Quand la capacité gagne, elle rapproche le profil de l'horizon : décaissement de p12 et études de p14.

**BNC assigné contre BNC robuste (9 poches).** Concordance complète dans 2 poches : p12 décaissement (critère
d'épuisement) et p14 retraite. Concordance partielle ou conditionnelle dans 5 : p14 études, p35 B, Robert, Mateo, Amira.
Discordance dans 2 : p12 accumulation (Croissance → Équilibré / Pondéré) et p35 A (Prudent → Liquidités). **Régularité** :
le BNC robuste n'est jamais plus risqué que le BNC assigné. Il est égal ou plus prudent d'un à deux crans. La cause est
toujours la même : une limite de perte qui porte sur le pire cas (p10 et violations) plutôt que sur l'étiquette de
tolérance.

**Concordance des classes.** p12 : 7 cohérents / 4 à trancher / 1 mixte / 0 contradiction. p14 : 15 / 2 / 1. p35 : 11 / 1 / 0.
Robert : 5 / 1 / 0. Mateo : 3 / 2 / 1. Amira : 3 / 1 / 2. Total : **44 cohérents, 11 à trancher, 1 mixte, 4 contradictions**
sur 60 cases. Types de contradictions :
- **critère** : maxDD pondéré par le temps contre épuisement en décaissement (p12, contradiction de méthode, hors décompte) ;
- **sélection in-sample** qui pousse une classe au plafond : énergie en retraite (p14) ;
- **artefact de construction** : le plancher d'actions de Mateo est réparti à parts égales sur les secteurs ;
- **vocabulaire statique contre stratégie dynamique** : Amira, « cœur » et « satellite » ne décrivent pas un momentum à
  3 actifs ;
- **volonté contre statut** : Robert à 0,05 rend « cœur » impossible.

**L'or est « à trancher » dans 4 personas sur 6** (p12 dans ses deux poches, Robert, Mateo, Amira ; p35 et p14 cohérents) : la
sélection le retient autour de 10 %, alors que les statuts disent « limité » ou « satellite » sans plafond chiffré.

## 9. Décisions à trancher par l'équipe (options et argument chiffré)

1. **Robert : confirmer ou remesurer Q10 (5 %, inféré).**
   - (a) Q10 = 5 % → encaisse seule : p10 −0,98 %, P(perte réelle sur 4 ans) 30,4 %, incohérence signalée au client.
   - (b) Remesurer : avec 15 % (palier AMF 3), la capacité 0,23 redevient la limite et `eq20_gold10` revient (p10
     +1,53 %, P 6,5 %, pire baisse 0,097) [WC].
   - (c) Deux poches : liquidités pour les premières années de retraite, et le reste sous la capacité.
   - **Q3 littéral** ne compte que si l'option (b) est retenue : il ramènerait alors à l'encaisse.
2. **Robert : traduction du BNC Conservateur.**
   - (a) Revenu fixe de type 10 ans (≈ XBB.TO) : la CVaR est dépassée dans 26 % des fenêtres, et aucun BNC n'est
     admissible.
   - (b) Revenu fixe court (moitié encaisse) : Conservateur est admissible, p10 +0,74 %, 0 violation [BNC].
   - (c) Relâcher la CVaR\* de 0,036 (la limite qui lie).
3. **Mateo : Q10 15 % contre bande [40 %, 80 %].**
   - (a) Garder 15 % et la règle inter-ères : `min_variance_60`, p10 CAD 2,06 % (−1,75 pt). Le plancher `static_eq40`
     viole déjà la limite dans 37,4 % des fenêtres USD 1926+.
   - (b) Garder 15 % mais ne juger que l'ère CAD : `dual_mom12_top2` (3,93 %) ; BNC Pondéré.
   - (c) Abaisser le plancher de la bande.
   - (d) Remesurer Q10 (30 %) : la capacité 0,20 s'applique, avec `risk_parity_iv36` et BNC Équilibré.
4. **Amira : le profil AMF 4 (plafonné par Q5) implique-t-il une perte de 30 % ?**
   - (a) Non : Q10 « > 30 % » ne lie pas, la limite reste 0,40 et `Mom_etf_top3` est retenu.
   - (b) Oui : `Mom_etf_top3` sort pour 0,4 pt de baisse (0,304 contre 0,30), et le minimax ne garde que
     `RP_invvol_36m` (16-36 % d'actions). Il faudrait alors changer de règle (par exemple meilleur p10 en CAD seul :
     `Trend10_E80` ou un mélange statique E70) [WC].
5. **Amira : la structure de `Mom_etf_top3` est-elle compatible avec « cœur FNB actions » et « diversification réelle » ?**
   Le momentum a 0 % d'actions dans 23,3 % des mois, et 38 % d'obligations et d'encaisse en moyenne alors que le statut
   est « satellite » [CON].
   - (a) Garder et requalifier les statuts pour une stratégie dynamique (plages de poids plutôt que cœur / satellite).
   - (b) `Mom_etf_top3_core50` : cœur permanent, p10 CAD 5,28 %, mais 16,7 % de violations en USD non chevauchant.
   - (c) Statique `E80_us50_g10_t0` : p10 CAD 4,70 %, cœur toujours présent.
   - (d) `Trend10_E80` : p10 minimal 1,84 %, regret 2,18 pt.
6. **Plafond d'or (Robert et Mateo « limité », Amira « satellite »).**
   - (a) 10 % (choix robustes).
   - (b) 5 % : pour Robert, le p10 CAD passe de 1,53 % à 0,80 % (`reports/robert.md` §6).
   - (c) 0 % pour Mateo tant que la filière aurifère n'est pas documentée (condition ESG de son statut).
   - (d) Pour Amira, plafonner l'or dans le momentum : il en détient ≥ 1/3 dans 36,7 % des mois.
7. **Mateo : plancher d'actions réparti sur les secteurs.**
   - (a) Accepter : en tickers, il n'y a de toute façon aucun titre.
   - (b) Restreindre la parité de risque aux FNB larges, ou plafonner les secteurs. En USD, 32,3 % du portefeuille est en
     proxys sectoriels, alors que le statut « actions US » est « limité ».
8. **Mateo : ESGV en cœur.**
   - (a) Garder ESGV avec la mention « ESG non backtesté » : 0 fenêtre de 10 ans, corrélation 0,9932 avec SPY.
   - (b) Utiliser la règle d'exclusion auditable (`US_MKT_XEN`, coût médian de −0,03 à +0,02 pt/an pour la parité de
     risque, `reports/mateo.md` §5) comme référence d'explication, et ESGV comme simple véhicule.
9. **Ancrage de la catégorie de risque (`questionnaire-profil.md`).**
   - (a) Garder le stress 2022 : l'écart entre BNC n'est que de 1,3 pt en CAD, et la bande Actions sort pour Robert,
     Mateo et Amira à la capacité [STR].
   - (b) Prendre le pire épisode CAD 1977+ (1980-82, 1987, 1994, 2000-02, 2007-09, 2020, 2022) : écart de 24,7 pt ;
     Robert et Mateo Équilibré à la capacité, Mateo Prudent à la volonté (limite 0,1498).
   - (c) Prendre le p90 de la maxDD à l'horizon de la poche : Mateo Pondéré à la volonté, Amira Croissance.
   - (d) Prendre l'enveloppe USD 1926+ avec 1929-32 : Amira Conservateur, trop sévère pour un investisseur en CAD.
   - **Proposition** : (b) avec (c) comme contrôle, et 2022 gardé comme l'un des épisodes.
10. **Analyse réglementaire : corriger la note CNQ.TO** (« aucune correction appliquée ») : 2022 +49,69 % et non
    +52,92 %, août 2022 +3,97 % et non +6,21 % [REC].
11. **Questionnaire en démo** : les 6 volontés sont inférées et décident 4 poches sur 9. Faire poser Q10 et Q11
    explicitement (Robert et Mateo d'abord), et afficher l'effet en dollars de chaque réponse.

## 10. Limites

- **Proxys** : `US_MKT` remplace les actions mondiales des BNC ; `CA_GOV_10Y` (taux moyens mensuels, volatilité
  sous-estimée) remplace le revenu fixe universel, et XBB.TO n'a qu'une corrélation de 0,5843 avec lui (README). Les
  secteurs KF tiennent lieu de titres. ESGV n'a pas d'historique ESG avant 2018.
- **Simulation sur une longue fenêtre** (§5, §6.1) : la phase du rééquilibrage annuel diffère de celle des runs par
  fenêtre. Les p90 de maxDD de §6.1 sont donc calculés sur un seul chemin, découpé en fenêtres au pas de 12 mois.
- **Données mensuelles** : les creux intra-mois disparaissent (SPY 0,2225 → 0,1867 en 2021-2026, [REC]).
- **Petits N** : 3 fenêtres de 15 ans en CAD non chevauchant pour Amira, 4 décennies pour Mateo et 12 fenêtres de 4 ans
  pour Robert. Les fenêtres roulantes se chevauchent.
- **Volontés inférées** : aucune réponse AMF n'est un fait du profil (marques (I) / [inf] dans [REG]).
- **Le seuil de 25 % de violations (Mateo) et de 10 % (Robert, Amira)** est une convention des rapports. Les relances la
  gardent telle quelle.
- **Biais du survivant, pas de frais de gestion ni d'impôts.** Les BNC sont des proxys de cibles, pas des fonds.
- La calibration `origin/docs/portfolio-construction` et `risk_levels_v0.2.yaml` ne sont citées que comme contexte.
  Leurs chiffres ne sont pas recalculés ici.

## 11. Les quatre questions

- **Quelles données ?**
  - Rendements mensuels 1926-2026 de la couche partagée `data/processed` (Ken French, FRED, Shiller, Banque du Canada,
    datahub, yfinance, starter), et `analysis/mateo/data_ext` pour `US_MKT_XEN` ;
  - starter quotidien, pour la réconciliation ;
  - analyse réglementaire en lecture seule [REG] ;
  - cibles BNC publiques (brochure 2025-10, par `00-cadre.md`).
- **Pourquoi ce choix ?**
  - La règle 31-103CP impose le plus bas de la volonté et de la capacité. On relance donc la sélection robuste de chaque
    rapport avec cette seule limite modifiée, et rien d'autre ne change (contrôles [WC]).
  - Les BNC sont testés sous les mêmes limites et sur les mêmes fenêtres que la stratégie robuste, ce qui rend la
    comparaison directe.
  - Le constat 2022 est situé dans 99 années USD et 49 années CAD.
- **Quelles limites ?** Celles du §10 : proxys, données mensuelles, petits N, volontés inférées, conventions de
  sélection, biais du survivant.
- **Qu'est-ce qui changerait la réponse ?**
  - **Robert** : une réponse Q10 de 15 % au lieu de 5 % (retour de `eq20_gold10`) ; un revenu fixe court pour le BNC.
  - **Mateo** : une réponse Q10 de 30 % (retour de la parité de risque et de l'Équilibré) ; une bande d'actions plus basse.
  - **Amira** : une lecture « profil 4 = 30 % » (le momentum sort, pour 0,4 pt) ; des statuts redéfinis pour une
    stratégie dynamique.
  - **Tous** : un ancrage de catégorie fondé sur plusieurs épisodes au lieu de 2022 ; un régime d'inflation où la
    corrélation actions-obligations reste positive, comme en 1970-1999.

## 12. Reproduire

```bash
cd research/backtest
.venv/bin/python -I analysis/croisement/make_profiles.py            # profiles/x_*.yaml
grep -v '^#' analysis/croisement/jobs.txt | xargs -n1 -P8 .venv/bin/python -I analysis/croisement/run_job.py
.venv/bin/python -I -W ignore analysis/croisement/stress_mateo.py   # séries Mateo (data_ext), avant stress_anchor
for s in will_vs_cap bnc concordance hist2022 stress_anchor reconcile; do
  .venv/bin/python -I -W ignore analysis/croisement/$s.py
done
```
Les scripts lisent la trace la plus récente de chaque profil dans `results/croisement_runs/`. Les horodatages changent à
chaque relance. Les runs Mateo avec ORACLE prennent de 5 à 13 minutes chacun (`results/croisement_logs/`).
