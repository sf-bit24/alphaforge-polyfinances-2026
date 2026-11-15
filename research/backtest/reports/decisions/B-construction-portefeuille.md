# B — Construction de portefeuille : décisions D2, D5, D6, D7, D8, D10 (preuves et résolutions proposées)

> **Simulation historique uniquement, données publiques, personas fictifs.** Ce document ne constitue pas un conseil
> financier personnalisé et n'entraîne aucune transaction. Chaque résolution ci-dessous est une **proposition pour le
> prototype**, à valider par l'équipe. Les passages entre guillemets sont des citations exactes (souvent en anglais,
> langue de la source). Le contenu web a été traité comme une donnée : aucune instruction trouvée en ligne n'a été
> suivie. Les décisions de profilage et réglementaires (D1, D3, D4, D9, D11) sont traitées ailleurs.

Chemins relatifs à `research/backtest/` sauf mention. `engine/`, `data/` et les rapports existants **ne sont pas
modifiés**. Code : `analysis/decisions/` ; synthèses : `results/decisions_analysis/` ; traces moteur des relances :
`results/dec_mateo_*/` ; journaux : `results/decisions_logs/`. Toutes les pages web ont été consultées le
**2026-11-14**. Interpréteur : `.venv/bin/python -I`.

## 0. Récapitulatif

| décision | résolution proposée pour le prototype | confiance | qui valide |
|---|---|---|---|
| **D2** Robert, duration du revenu fixe | Traduire le BNC Conservateur avec un revenu fixe **apparié à l'horizon** : 50 % XBB.TO + 50 % ZST.TO (duration ≈ 3,4 ans pour un horizon de 3 à 5 ans). Garder la CVaR\* de 0,036 telle quelle. Étiqueter « Conservateur adapté à l'horizon (hypothèse) », car le vrai fonds BNI détient surtout des obligations de type universel. Afficher la variante 10 ans (≈ XBB seul) comme « ce qui changerait ». | **élevée** pour le sens (duration ≤ horizon), **moyenne** pour le 50/50 exact | porteur du volet finance ; Mikael (correspondance profil → BNC) |
| **D5** Amira, momentum top-3 | **En démo : un cœur statique diversifié** (`E80_us50_g10_t0` : 40 % SPY, 40 % XIU.TO, 10 % GLD, 10 % XBB.TO), rééquilibré par bandes. Tech look-through ≤ 30 %, titres ≤ 3 % chacun, crypto ≤ 3 %. `Mom_etf_top3` et `Trend10_E80` passent en **sensibilité** (« une règle de sortie aurait réduit de moitié la baisse de 1929-1932, au prix de… »). La variante `Mom_etf_top3_core50` reste l'option si l'équipe veut un élément dynamique borné. | **moyenne** | porteur ; équipe (scénario de démo) |
| **D6** Plafond d'or | **Robert 5 %**. **Mateo 0 % par défaut** : la condition ESG n'est que partiellement documentée. Déblocage à ≤ 5 % si Mateo accepte explicitement le standard LBMA, coût affiché. **Amira 10 %**, plafond appliqué aussi à toute stratégie dynamique. Afficher le coût de chaque plafond en points de p10. | **moyenne** | porteur ; Mateo (choix ESG simulé) |
| **D7** Mateo, plancher d'actions | Spécification d'un correctif de `project()` (§D7.5) : un plancher de groupe est comblé **au prorata des poids choisis par la stratégie**, avec repli sur le cœur large (`broad_market`) et jamais sur un actif que la stratégie a exclu. On ajoute un plafond « proxys sectoriels US ≤ 10 % » (statut « limité »). Effet mesuré (USD 1926+) : secteurs 32,3 % → 0 % ; pire p10 de `risk_parity_iv36` −0,15 % → −0,48 % ; les 3 premiers du classement inter-ères tiennent alors en 0,4 pt. | **élevée** pour le diagnostic, **moyenne** pour le choix final de stratégie (classement dans le bruit) | porteur (moteur) |
| **D8** ESGV « non backtesté » | Garder ESGV comme **véhicule**. L'explication s'appuie sur la **règle d'exclusion auditable** (`US_MKT_XEN`). Formulation : « l'indice existe depuis 2018-08-13, son historique 2015-03 → 2018-08 est hypothétique, ESGV n'a aucune fenêtre complète de 10 ans ; notre historique long est un proxy "marché US sans pétrole, gaz et charbon", pas ESGV » (texte complet §D8.5). | **élevée** | porteur ; rédacteur de la doc technique |
| **D10** CNQ.TO 2022-08-22 | **Confirmé par la source primaire.** Le dividende spécial est de 1,50 $ CA par action, date de clôture des registres le 2022-08-23, ex-dividende le 2022-08-22. Dans le starter : 0,75 $ = 1,50 / 2, à cause du fractionnement 2 pour 1 de juin 2024. Le « split » 1,021 est ce même dividende, enregistré une seconde fois. `adj_close` le compte donc deux fois (+2,78 % au lieu de +0,61 % ce jour-là). Le correctif du moteur et l'erratum de `quant/resultats.md` sont justes. | **élevée** | auteur de l'analyse réglementaire (erratum fait) ; porteur des données |

### 0.1 Points de contact avec les autres sessions (contradictions signalées)

- **D6 et `risk_levels_v0.2.yaml`** (`composition.gold_max` : N0 = N1 = 0,05 ; N2 à N5 = 0,10). La proposition « Robert 5 % » **concorde** si Robert est classé N0 ou N1. Elle **contredit** v0.2 si Robert est classé N2, où v0.2 permet 10 % (le `horizon_cap` « T < 5 → N2 » rend ce cas possible). Pour Mateo, v0.2 ne traite pas l'ESG de l'or : « 0 % par défaut » est une **condition supplémentaire**, pas une contradiction de seuil. La MDD de 0,513 (or en CAD) de v0.2 est **reproduite** ici (§D6.4).
- **D2 et v0.2** (`long_duration_max` vise TLT ; aucune règle ZST contre XBB). Cette proposition **ajoute** une règle « duration du revenu fixe ≤ horizon de la poche » et ne contredit rien. Elle va dans le même sens que le constat d'une autre session, selon lequel un min-CVaR choisit surtout ZST.TO + AGG en N1-N2. Réserve : AGG ajoute un risque de change USD pour un retraité en CAD (§D2.5).
- **D5** : la proposition **rejoint** l'option d'une autre session (statique + rééquilibrage par règles, signaux seulement en tilts bornés). Elle s'écarte en revanche de la sélection « minimax du regret sur 6 runs » du croisement, qui retient `Mom_etf_top3` (raison chiffrée au §D5.4).
- **D10** : la proposition **confirme** l'erratum de l'auteur de l'analyse réglementaire par la source primaire. Seule précision : le montant **déclaré** est de 1,50 $ CA. Les 0,75 $ du starter en sont la version ajustée du fractionnement de 2024.
- **D7** : avec le correctif, le choix inter-ères de Mateo **change** (§D7.4). Cela touche la décision D3 (Mateo, Q10), traitée ailleurs : le classement entre `risk_parity_iv36`, `min_variance_60` et `mean_var_60_ra10` tient en moins de 0,4 pt de pire p10.

### 0.2 Scripts et traces de ce document

| script (`analysis/decisions/`) | sortie (`results/decisions_analysis/`) | contenu |
|---|---|---|
| `d2_duration.py` | `d2_duration.json` | durations empiriques XBB.TO / ZST.TO / AGG / TLT (régression hebdomadaire sur les taux BdC), taux 2022, duration des mélanges |
| `d5_amira.py` | `d5_amira.json` | candidats Amira sur les 6 runs (lecture de `will_vs_cap.json`, `concordance.json`), minimax restreint aux runs CAD |
| `d6_gold.py` | `d6_gold.json` (+ `results/dec_mateo_*_gold*/`) | statistiques de l'or 1975-2026 (CAD/USD), corrélations, relances Mateo avec GOLD ≤ 0 / 5 / 10 % / sans plafond |
| `d7_fill.py`, `d7b_sector_cap.py` | `d7_fill.json`, `d7b_sector_cap.json` (+ `results/dec_mateo_*_{euclid,prorata,prorata_cap10_x}/`) | remplissage euclidien contre prorata (enrobage au runtime, moteur intact), plafond sectoriel, règle inter-ères |
| `d8_d10_checks.py` | `d8_d10_checks.json` | fenêtres de 10 ans disponibles pour ESGV et son indice ; reconstitution CNQ.TO du 2022-08-22 |

```bash
cd research/backtest
for s in d2_duration d5_amira d8_d10_checks d6_gold d7_fill d7b_sector_cap; do
  .venv/bin/python -I -W ignore analysis/decisions/$s.py
done   # d6/d7/d7b relancent le moteur sans ORACLE (quelques minutes chacun)
```
Reproductibilité : la relance de `mateo_cad_esg` sans plafond d'or redonne le p10 du rapport Mateo (3,81 %, CAD). La
relance euclidienne USD 1926+ redonne aussi ses chiffres : p10 −0,15 %, 32,3 % de secteurs, 8,4 % sur `US_MKT_XEN`
(`d6_gold.json`, `d7_fill.json`).

---

## D2 — Robert : revenu fixe « 10 ans » (XBB.TO) ou « court » (ZST.TO) pour traduire le BNC Conservateur

### D2.1 La question en mots simples
Le portefeuille public « Conservateur » met 70 % en obligations. Le choix porte sur le type d'obligations qui
représente cette part pour Robert, qui aura besoin de son argent dans 3 à 5 ans. Une obligation longue perd beaucoup
de valeur quand les taux montent. Si Robert doit vendre à ce moment-là, la perte est réelle, et c'est ce qui s'est
passé en 2022.

### D2.2 Options
- (a) Revenu fixe de type indice universel canadien (≈ XBB.TO, proxy `CA_GOV_10Y`).
- (b) Revenu fixe court : 50 % XBB.TO + 50 % ZST.TO (proxy 50 % `CA_GOV_10Y` + 50 % `CA_TBILL`).
- (c) Relâcher la CVaR\* de 0,036, la limite qui lie.

### D2.3 Preuves

| source | date | URL | citation exacte | ce que ça prouve |
|---|---|---|---|---|
| iShares (BlackRock Canada), page produit XBB | données au 2026-11-12 | https://www.blackrock.com/ca/investors/en/products/239493/ishares-canadian-universe-bond-index-etf | « Effective Duration as of Nov 12, 2026 6.74 yrs » ; « Weighted Avg Maturity as of Nov 12, 2026 9.50 yrs » ; indice de référence « FTSE Canada Universe Bond Index » | XBB a une duration de 6,7 ans, **supérieure** à l'horizon de 3 à 5 ans de Robert |
| BMO GAM, page produit ZST | — | https://www.bmogam.com/ca-en/products/exchange-traded-fund/bmo-ultra-short-term-bond-etf-zst/ | **inaccessible** depuis notre poste (ERR_HTTP2_PROTOCOL_ERROR, délai dépassé) : aucune donnée émetteur citée | la duration de ZST est estimée empiriquement (§D2.4), à confirmer sur la fiche BMO |
| BNI, aperçu du fonds « NBI Sustainable Conservative Portfolio – Advisor Series » | 2026-05-14 (positions au 2026-03-31) | https://www.nbinvestments.ca/content/dam/bni/en/fund/regulatory/fund-facts/NBC9602-Advisor-fund-facts.pdf | « 1. NBI Sustainable Canadian Bond ETF 33.6% 2. NBI Sustainable Canadian Corporate Bond ETF 17.5% 3. NBI Sustainable Global Bond Fund 17.3% » ; « Cash, Money Market and Other Net Assets 2.5% » | le revenu fixe réel du Conservateur BNI est fait de fonds obligataires **universels, de sociétés et mondiaux**, avec très peu d'encaisse. L'option (a) est donc la plus **fidèle** au produit, et l'option (b) une **adaptation** |
| BNI, page du même fonds | positions au 2026-10-31 | https://www.nbinvestments.ca/prices-and-performance/portfolio-solutions/nbc9602.html | « Fixed Income 65.72 » ; « Cash and Cash Equivalents 1.01 » | même constat, plus récent. Réserve : l'aperçu BNI au 2026-09-30 (`publication-funds-overview.pdf`) ne liste que les Portefeuilles *durables* BNI et les Portefeuilles FNB. La correspondance avec la « brochure BNI 2025-10 » de `00-cadre.md` reste à confirmer, et la duration des fonds sous-jacents n'a pas été trouvée |
| SEC, Investor Bulletin « Interest rate risk » | s.d. (bulletin OIEA) | https://www.sec.gov/files/ib_interestraterisk.pdf | « Therefore, bonds with longer maturities generally have higher interest rate risk than similar bonds with shorter maturities. » ; « If you intend to hold a bond to maturity, the day-to-day fluctuations in the bond's price may not be as important to you. » | régulateur : le risque de taux croît avec la maturité. Il ne s'efface que si l'on **détient jusqu'à l'échéance**, or un FNB à maturité constante n'échoit jamais |
| FINRA, « Brush Up on Bonds: Interest Rate Changes and Duration » | 2024-09-19 | https://www.finra.org/investors/alerts/duration-what-interest-rate-hike-could-do-your-bond-portfolio | « For example, if a bond has a duration of 10 and interest rates increase by 1 percentage point, then that bond's price would be expected to decline by approximately 10 percent. » | règle explicable en démo : perte ≈ duration × hausse des taux |
| Fisher, L. et Weil, R. L., « Coping with the Risk of Interest-Rate Fluctuations: Returns to Bondholders from Naive and Optimal Strategies », *Journal of Business* 44(4), p. 408 et suiv., DOI 10.1086/295402 | 1971 | https://doi.org/10.1086/295402 | **texte non consulté** (JSTOR inaccessible) ; métadonnées vérifiées sur Crossref | référence fondatrice de l'**immunisation** (duration du portefeuille = horizon). Citée sans extrait, faute d'accès |
| Redington, F. M., « Review of the Principles of Life-office Valuations », *Journal of the Institute of Actuaries* 78(3), p. 286-340, DOI 10.1017/S0020268100052811 | 1952 | https://doi.org/10.1017/S0020268100052811 | **texte non consulté** ; métadonnées Crossref | origine de l'appariement actif-passif par la duration. Même réserve |

### D2.4 Nos données
- **Durations empiriques** (`d2_duration.json`). Régression hebdomadaire du prix sur la variation du taux du
  Canada, 2021-11 → 2026-11, 261 semaines, données du starter (BdC). **XBB.TO : 6,52 ans** contre le 10 ans
  (R² = 0,94), très proche des 6,74 ans d'iShares. **ZST.TO : ≈ 0** (R² ≈ 0 contre le 2 ans), sans sensibilité
  mesurable aux taux. AGG : 5,1 ans. TLT : 12,5 ans.
- **Choc de 2022** (même fichier). Le taux directeur de la BdC passe de 0,25 % à 4,25 %, le 2 ans du Canada de 0,95 %
  à 4,06 % et le 10 ans de 1,42 % à 3,30 %. Rendements totaux 2022 : XBB.TO −11,66 %, ZST.TO +1,22 %, AGG −13,02 %
  (USD), TLT −31,23 % (USD). Le +188 pb sur le 10 ans multiplié par une duration de 6,5 donne environ −12 % de prix,
  ce qui reproduit l'ordre de grandeur observé.
- **Duration du revenu fixe selon l'option** (`d2_duration.json → blend_duration`). (a) XBB seul : 6,74 ans.
  (b) 50/50 XBB/ZST : **3,38 ans**, au milieu de l'horizon de 3 à 5 ans. Le proxy long `CA_GOV_10Y` (obligation au
  pair de 10 ans) a une duration modifiée de 8,2 ans à 4 % de taux (9,0 ans à 2 %, calcul direct). Il est donc
  **plus long** que XBB, mais lissé (taux moyens mensuels, volatilité sous-estimée, `README` point 4) : les deux
  biais vont en sens contraires.
- **BNC sous les limites de Robert** (`results/croisement_analysis/bnc.json`, croisement §4, roulant 4 ans, CAD 1977+) :

| BNC (revenu fixe) | p10 réel | pire maxDD | taux de violation (CVaR surtout) |
|---|---|---|---|
| Conservateur, revenu fixe `CA_GOV_10Y` (option a) | −0,15 % | 0,152 | **26 %** |
| Conservateur, 50 % `CA_GOV_10Y` + 50 % `CA_TBILL` (option b) | **+0,74 %** | 0,101 | **0 %** |
| Prudent, option b | +0,32 % | 0,091 | 0 % |
| Pondéré, option b | +0,67 % | — | 39 % |

  En non chevauchant, l'option (b) donne p10 1,02 %. Sur la seule période réelle 2021-11 → 2026-09, le Conservateur
  avec XBB.TO dépasse la CVaR (0,0388 contre 0,036). La structure courte des tickers « XBB 30 / ZST 40 » fait
  +3,19 %/an réel, avec une maxDD de 0,068 et une CVaR de 0,022 (`reports/robert.md` §8).
- **Duration et mauvais cas** (`reports/robert.md` §6, USD 1926+, 20 % d'actions) : p10 2 ans −1,64 %, 5 ans −2,42 %,
  10 ans −2,97 %, 20 ans −3,65 % ; violations 5,2 / 10,3 / 29,9 / 52,6 %. Constat R1 du rapport : **robuste**, trois
  sources indépendantes.

### D2.5 Résolution proposée pour le prototype
- **Règle** : la duration du revenu fixe d'une poche ne dépasse pas son horizon (Robert : ≤ 4 ans, milieu de 3 à 5
  ans). C'est la logique de l'immunisation : à duration égale à l'horizon, la perte de prix due à une hausse de taux
  est compensée, en gros, par le réinvestissement à taux plus élevé.
- **Traduction du BNC Conservateur pour Robert** : 70 % de revenu fixe = 35 % XBB.TO + 35 % ZST.TO (option b), soit
  une duration ≈ 3,4 ans et une sensibilité du portefeuille ≈ 2,4 (0,70 × 3,38) contre 4,7 avec XBB seul. Afficher
  « Conservateur adapté à l'horizon (hypothèse) ». Le vrai fonds BNI détient surtout des obligations universelles :
  l'option (b) n'est pas une copie.
- **Ne pas relâcher la CVaR\*** (option c) : la violation vient de la duration, pas d'un seuil trop sévère.
- **Écart possible avec une autre session** : AGG (5,1 ans) fait partie du choix min-CVaR d'une autre session. Pour un
  retraité qui dépense en CAD, le revenu fixe en USD ajoute un risque de change. En 2022, ce change a aidé : AGG fait
  −7,1 % en CAD contre −13,0 % en USD (`quant/resultats.md`). Ce coussin ne se reproduira pas forcément.
- **Ce qui changerait la résolution** :
  - un horizon de Robert remesuré au-delà de 5 ans ;
  - la duration émetteur de ZST, si elle est nettement supérieure à 1 an ;
  - la confirmation que le produit BNI de référence est un autre fonds, à revenu fixe court ;
  - un régime de baisse des taux, où l'option (a) aurait mieux fait. Ce dernier point est un argument de rendement,
    pas de risque.
- **Confiance** : élevée sur le principe (R1 robuste, régulateurs, immunisation) ; moyenne sur la proportion exacte de
  50/50 (une seule sensibilité testée).
- **Valide** : porteur du volet finance ; Mikael pour la correspondance AMF → BNC.

---

## D5 — Amira : « momentum top-3 » ou base diversifiée ?

### D5.1 La question en mots simples
La stratégie qui a le mieux résisté dans nos tests ne garde que 3 placements à la fois, change chaque mois et sort
parfois complètement des actions (23 % des mois). Amira veut faire croître son capital et garder une diversification
réelle. Il faut décider ce qu'on lui montre : la stratégie gagnante de nos tests ou un portefeuille de base stable.

### D5.2 Options
- (a) `Mom_etf_top3` : choix du minimax du regret sur 6 runs.
- (b) `Trend10_E80` : 80 % d'actions US/CA, chaque poche passe à l'encaisse sous sa moyenne mobile de 10 mois.
- (c) `Mom_etf_top3_core50` : cœur permanent ≥ 50 % et momentum sur le reste.
- (d) Statique `E80_us50_g10_t0`, rééquilibré.
- (e) Option d'une autre session : statique + rééquilibrage par règles (bandes, glidepath), signaux seulement en
  tilts bornés. Elle recouvre (d), avec (c) comme forme « tilt borné ».

### D5.3 Preuves

| source | date | URL | citation exacte | ce que ça prouve |
|---|---|---|---|---|
| Énoncé officiel FR, persona Amira (p. 5) | 2026 | `source/Datathon2026/Datathon2026/Datathon - Case Officiel 2026 FR.pdf` | « Souhaite maintenir une certaine diversification et éviter de miser exclusivement sur les technologies. » ; « Il doit tenir compte de son profil offensif sans interpréter « risque élevé » comme « tout est acceptable ». Garder une diversification cohérente avec ses préférences demeure important. » | le test porte sur la **diversification et les limites de risque**, pas sur la meilleure stratégie de rotation |
| Énoncé officiel FR (p. 18) | 2026 | idem | « Le défi ne demande pas de prédire les rendements futurs à partir des performances passées. » | choisir sur le meilleur p10 historique d'une rotation est fragile vis-à-vis de l'esprit du défi |
| Faber, M. T., « A Quantitative Approach to Tactical Asset Allocation », *Journal of Wealth Management* 9(4), p. 69-79, DOI 10.3905/jwm.2007.674809 ; version mise à jour en février 2013 (PDF de l'auteur, SSRN 962461 bloqué) | 2007 / 2013 | https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf | « The timing model also uses equal weightings and treats each asset class independently – it is either long the asset class or in cash with its 20% allocation of the funds. » ; « The timing system achieves these superior results while underperforming the index in roughly half of all years since 1901. » | le modèle de référence est un **cœur à poids égaux sur 5 classes, filtré classe par classe** (proche de `Trend10_E80`), pas un top-3. Le top-3 sur 13 actifs y est présenté comme une extension « Aggressive ». Conflit d'intérêts : l'auteur est gérant (Cambria) |
| Faber, idem, « Practical considerations and taxes » | 2013 | idem | « Taxes, on the other hand, are a very real consideration. » ; « The system has a turnover of almost 70%. » | les impôts et la rotation sont un coût réel hors compte enregistré. Notre `Mom_etf_top3` tourne 2,5 fois plus vite (1,79 par an, §D5.4) |
| Moskowitz, T. J., Ooi, Y. H. et Pedersen, L. H., « Time series momentum », *Journal of Financial Economics* 104(2), p. 228-250, DOI 10.1016/j.jfineco.2011.11.003 (résumé sur la page AQR) | 2012 | https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum | « Specifically, we find strong positive predictability from a security's own past returns for a set of 58 diverse futures and forward contracts that include country equity indices, currencies, commodities and sovereign bonds over more than 25 years of data. » | la preuve porte sur **58 contrats à terme, long-short**, très diversifiés. Elle ne se transfère pas telle quelle à une rotation long-only sur 7 FNB qui garde 3 actifs. Conflit : AQR gère des fonds de ce type |
| Hurst, B., Ooi, Y. H. et Pedersen, L. H., « A Century of Evidence on Trend-Following Investing », *Journal of Portfolio Management* 44(1), p. 15-29, DOI 10.3905/jpm.2017.44.1.015 (résumé sur la page AQR) | 2017 | https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing | « Using historical data from a number of sources, we construct a time series momentum strategy back to 1880 and find that the strategy was consistently profitable over the next 110 years. » ; « We consider the effect of increased assets in the strategy as well as the increased correlations across markets since the credit crisis. » | la règle de tendance est un effet **robuste et documenté sur longue période**, ce qui appuie l'usage de `Trend10` comme sensibilité ou tilt. Mêmes auteurs (AQR) que la source précédente, même conflit |
| Asness, C. S., Moskowitz, T. J. et Pedersen, L. H., « Value and Momentum Everywhere », *Journal of Finance* 68(3), p. 929-985, DOI 10.1111/jofi.12021 (résumé sur la page AQR) | 2013 | https://www.aqr.com/Insights/Research/Journal-Article/Value-and-Momentum-Everywhere | « We find consistent value and momentum return premia across eight diverse markets and asset classes, and a strong common factor structure among their returns. » | le momentum **relatif** (cross-sectional) est une prime générale. Le résumé l'étudie avec la valeur et sur des portefeuilles larges, pas sur 3 actifs |

### D5.4 Nos données (6 runs FNB, limite de baisse 0,40, moteur actuel ; `d5_amira.json`)

| stratégie | p10 réel par run CAD (E1 / E2 / E3) | p10 minimal sur 6 runs | regret max sur 6 runs | regret max sur les 3 runs **CAD** | pire maxDD | 0 % d'actions (mois, CAD) | ≥ 3 classes (mois, CAD) | or ≥ 1/3 (mois, CAD) | rotation/an (CAD) |
|---|---|---|---|---|---|---|---|---|---|
| `Mom_etf_top3` | 6,19 / 5,16 / 5,68 % | 0,95 % | **1,53** (retenu) | 1,42 | 0,304 | **23,3 %** | 67,4 % | **36,7 %** | 1,79 |
| `Trend10_E80` | 5,43 / 5,32 / 5,24 % | 1,84 % | 2,18 | 2,18 | 0,344 | 14,6 % | 85,4 % | 0 % | 1,18 |
| `Mom_etf_top3_core50` | 6,57 / 5,28 / 5,76 % | 1,62 % | 1,05, **mais inéligible** en USD 1926+ non chevauchant (maxDD 0,558, 16,7 % de violations) | 1,05 | 0,558 | 0 % | 100 % | 0 % | 0,95 |
| `E80_us50_g10_t0` (statique) | 6,76 / 4,70 / 5,82 % | 4,70 % (CAD) | non évaluable : aucun équivalent en USD 1926+ (pas d'or ni d'actions CA avant 1975) | **0,85** | 0,290 (CAD) | 0 % | **100 %** | 0 % | **0,04** |
| `E90_us50_g10_t0` (statique) | 6,99 / 4,58 / 5,95 % | — | — | **0,74** (1er) | 0,339 | 0 % | 100 % | 0 % | — |
| statiques USD 70-80 % actions (`E80_us100_g0_t0`…) | — | — | **inéligibles** : maxDD 0,66 à 0,74 en 1929-1932 | — | 0,728 | — | — | — | — |

Lecture :
1. `Mom_etf_top3` gagne la règle sur 6 runs **parce que** toute politique statique d'au moins 70 % d'actions dépasse
   la limite de 0,40 dans la fenêtre USD qui contient 1929-1932 (maxDD de 0,66 à 0,85). Or l'équipe range ailleurs
   1929-1932 comme « scénario informatif, pas un budget pour un investisseur en CAD » (croisement §6.1,
   `risk_levels_v0.2.yaml`, `stress_informational`). Avec la **même règle restreinte aux 3 runs CAD**, devise d'Amira,
   le minimax choisit un **statique diversifié** (`E90_us50_g10_t0` 0,74 pt, `E80_us50_g10_t0` 0,85 pt). Le momentum
   descend à 1,42 pt et `Trend10_E80` à 2,18 pt.
2. **Structure.** Le momentum couvre ≥ 3 classes dans 67 % des mois seulement. Il n'a aucune action dans 23 % des
   mois et au moins un tiers d'or dans 37 % des mois. Le statique couvre toujours ≥ 3 classes, avec 72 à 85 %
   d'actions. Il colle mieux à « faire croître son capital » et à « diversification cohérente ».
3. **En faveur du momentum.** Il a une meilleure résistance en 2007-2009 : perte de 2,6 % contre 26,7 % pour BNC
   Croissance (croisement §6.1). Il fait aussi mieux en 2022 grâce à l'encaisse (37,1 % en moyenne). La période réelle
   en tickers le confirme : +11,09 %/an réel, maxDD 10,8 %, contre +10,31 % et 13,0 % pour le statique
   (`reports/amira.md` §6). Ces avantages sont réels, mais ils tiennent à peu d'épisodes.

### D5.5 Résolution proposée pour le prototype
- **Quoi montrer en démo pour Amira**, dans l'ordre :
  1. La demande fictive « tout tech/crypto » : rendement brut le plus haut sur la fenêtre, mais maxDD 50,8 %, au-delà
     du budget de 40 %.
  2. Le **cœur statique diversifié** `E80_us50_g10_t0` : 40 % SPY, 40 % XIU.TO, 10 % GLD, 10 % XBB.TO, rééquilibré
     par bandes. Tech look-through ≤ 30 %, satellites tech ≤ 3 % par titre, crypto ≤ 3 %.
  3. Une carte « ce qui changerait » : une règle de sortie (tendance ou momentum) aurait réduit de moitié la pire
     baisse de type 1929. Elle aurait aussi passé 23 % des mois sans actions, tourné le portefeuille 1,8 fois par an
     (impôts hors CELI/REER) et coûté de la croissance médiane en USD.
- **Si l'équipe veut un élément dynamique** : `Mom_etf_top3_core50`, un tilt borné qui ne descend jamais sous 50 % de
  cœur, avec un or plafonné à 10 % (§D6). Il faut afficher son inéligibilité en USD 1926+ (maxDD 0,558).
- **Ce qui changerait la résolution** :
  - l'équipe décide que 1929-1932 est une contrainte **dure** pour Amira : la règle sur 6 runs reste alors valable
    et le momentum revient ;
  - une limite de 0,30 pour Amira (D4, traitée ailleurs) ;
  - un compte enregistré confirmé, ce qui neutralise l'argument fiscal.
- **Confiance** : moyenne. Les écarts de p10 entre candidats sont de 1 à 2 pt sur des fenêtres qui se chevauchent
  (3 fenêtres CAD indépendantes de 15 ans).
- **Valide** : porteur ; équipe pour le scénario de la vidéo.

---

## D6 — Plafond d'or : 10 %, 5 % ou 0 % (Mateo) ?

### D6.1 La question en mots simples
L'or a beaucoup aidé nos portefeuilles simulés, surtout depuis 2021. Mais il peut perdre la moitié de sa valeur et
mettre 20 ans à s'en remettre. Il ne verse aucun revenu, et pour Mateo, son extraction pose des questions
environnementales et sociales. Il faut fixer la part maximale pour chacun.

### D6.2 Options
- (a) 10 % : choix des stratégies robustes.
- (b) 5 %.
- (c) Mateo 0 % tant que l'ESG de l'or n'est pas documenté.
- (d) Plafonner l'or aussi dans le momentum d'Amira.

### D6.3 Preuves

| source | date | URL | citation exacte | ce que ça prouve |
|---|---|---|---|---|
| Erb, C. B. et Harvey, C. R., « The Golden Dilemma », *Financial Analysts Journal* 69(4), p. 10-42, DOI 10.2469/faj.v69.n4.1 (résumé NBER w18706) | 2013 | https://www.nber.org/papers/w18706 | « Over practical investment horizons, gold is an unreliable inflation hedge. » ; « In the past, when the real price of gold was above average, subsequent real gold returns have been below average consistent with mean reversion. » | académique et indépendant : l'or n'est **pas une couverture fiable à l'horizon d'un épargnant**. Une valorisation réelle élevée a précédé de faibles rendements |
| World Gold Council, « Gold as a strategic asset: 2026 edition », section Portfolio impact | 2026-02-04 | https://www.gold.org/goldhub/research/relevance-of-gold-as-a-strategic-asset/portfolio-impact | « It shows that a hypothetical average USD portfolio would have achieved higher risk-adjusted returns and lower drawdowns if 2.5%, 5%, 7.5% or 10% were allocated to gold » | l'organisme promoteur situe lui-même l'or **entre 2,5 et 10 %** dans un portefeuille moyen. **Conflit d'intérêts** : le WGC est financé par l'industrie aurifère et détient le promoteur de GLD (ligne suivante). Ses chiffres sont en USD, sur 20 ans, et hypothétiques |
| World Gold Council, idem, section ESG credentials | 2026-02-04 | https://www.gold.org/goldhub/research/relevance-of-gold-as-a-strategic-asset/portfolio-impact-esg-credentials | « While gold mining is, by definition, an extractive industry, responsible gold miners follow stringent frameworks to mitigate environmental impact and reduce risks. » | même avec son biais, le promoteur admet que l'or vient d'une **industrie extractive**. L'ESG de l'or n'est pas neutre pour Mateo |
| SPDR Gold Trust (GLD), formulaire 10-K, exercice clos le 2025-09-30, déposé le 2025-11-25 | 2025-11-25 | https://www.sec.gov/Archives/edgar/data/1222333/000143774925036305/gld20250930_10k.htm | « All LBMA Good Delivery refiners are required to implement the LBMA's Responsible Sourcing Guidance, which comprises the Guidance, and obtain annual independent assurance on their publicly available compliance reporting. » ; « The Sponsor is an indirect wholly owned subsidiary of the World Gold Council… » | GLD détient des **lingots** (pas de mines). Leur filière est encadrée au niveau des **affineurs** LBMA, avec une assurance annuelle indépendante. Le document confirme aussi le lien de capital entre WGC et GLD. Autre extrait : « The Trust does not generate any income » |
| GLD 10-K, idem, tableau de l'offre mondiale (source Gold Focus 2025) | 2025-11-25 | idem | « Mine Production 3,483 3,575 3,645 3,640 3,661 Recycling 1,293 1,136 1,136 1,234 1,368 » (tonnes, 2020-2024) | environ 27 % de l'offre 2024 est **recyclée** : l'origine « mine » d'un lingot n'est pas traçable par l'investisseur |
| LBMA, page Responsible Sourcing | consultée le 2026-11-14 (RGG v10 en consultation publique) | https://www.lbma.org.uk/responsible-sourcing | « Pursuant to the RSP, all metal sourced from the LBMA Good Delivery (GDL) Refiners is subject to an assurance process to establish that it is responsibly sourced. The Programme follows the five-step due diligence framework set out in the OECD Guidance and requires GDL refiners to demonstrate their efforts to combat money laundering, terrorist financing and human rights abuses, and respect the environment globally. » | il existe un standard documenté, aligné sur l'OCDE, couvrant les droits humains et l'environnement. **Limite** : c'est une **autorégulation** de l'association de marché, au niveau affineur, sans note par mine. Aucune source critique indépendante n'a été consultée ici |
| FTSE Russell, Ground Rules « FTSE Global Choice Index Series » v5.0, annexe A | 2026-08 | https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-choice-index-series-ground-rules.pdf | les catégories exclues sont « Non-Renewable Energy », « Vice Products » et « Weapons » (tableau 2) : **aucune catégorie « or » ou « mines d'or »** | l'indice ESG choisi pour le cœur de Mateo n'exclut pas l'extraction aurifère par produit, seulement par controverse de conduite. Exclure l'or-lingot serait **plus strict** que son propre cœur ESG |

### D6.4 Nos données
- **Risque propre de l'or** (`d6_gold.json`, 1975-2026) :
  - en CAD, perte maximale nominale de **51,3 %** (1980-09 → 1999-06), **326 mois** pour revenir au pic ; c'est la
    valeur de v0.2. Perte réelle maximale de 78,2 %.
  - en USD, perte nominale de 62,1 % et perte réelle de 83,1 % ; le pic réel de janvier 1980 n'est regagné qu'après
    541 mois.
  - rendement réel par décennie en CAD : +0,4 % (1975-84), −1,1 % (1985-94), −2,0 % (1995-2004), +8,3 % (2005-14),
    +7,8 % (2015-24).
  - deux décennies sur cinq négatives, puis deux très fortes. C'est le schéma de régime décrit par Erb et Harvey.
- **Corrélation avec les actions** (même fichier, mensuelle) :
  - 1977-2026 : or / `US_MKT` −0,02 en USD et −0,09 en CAD.
  - période des tickers (60 mois) : GLD/SPY +0,17 en USD contre +0,02 en CAD, et GLD/XIU.TO +0,33 contre +0,14.
  - **la décorrélation « ≈ 0 » de 2021-2026 vient en partie du change**, comme le notait `quant/resultats.md`. Sur
    50 ans, elle est proche de 0 dans les deux devises.
- **Robert** (`reports/robert.md` §6, CAD 1977+, 20 % d'actions) :

  | part d'or | 0 % | 5 % | 10 % | 15 % |
  |---|---|---|---|---|
  | p10 réel | −0,47 % | **+0,80 %** | +1,53 % | +1,62 % |
  | violations | 0 % | **0 %** | 4,3 % | 6,5 % |

  Le gain de 5 à 10 % (+0,73 pt) s'accompagne des premières violations. Le résultat est marqué **fragile (R6)** : il
  tient à 4 fenêtres où l'ORACLE met 34 à 59 % d'or.
- **Mateo, relances avec GLD/GOLD plafonné** (`d6_gold.json → part_b`, `risk_parity_iv36`, roulant 10 ans) :

  | plafond d'or | 0 % | 5 % | 10 % | sans plafond |
  |---|---|---|---|---|
  | p10 réel CAD 1977+ (or moyen) | 3,09 % (0) | 3,45 % (4,8 %) | 3,68 % (8,7 %) | **3,81 %** (10,3 %) |
  | p10 réel USD 1975+ (or moyen) | 2,38 % (0) | 2,54 % (1,1 %) | 2,54 % | 2,54 % (1,2 %) |
  | violations (les deux ères) | 0 % | 0 % | 0 % | 0 % |

  Le **pire p10 inter-ères (−0,15 %, USD 1926+ sans or) ne bouge pas** : le plafond d'or ne change pas le choix
  inter-ères de Mateo. Il coûte jusqu'à 0,72 pt de p10 en CAD.
- **Amira** : `Mom_etf_top3` détient au moins un tiers d'or dans 36,7 % des mois (CAD). En fin de fenêtre réelle, il
  détenait 1/3 SPY, 1/3 XIU.TO et 1/3 GLD (`reports/amira.md` §6).

### D6.5 Résolution proposée pour le prototype
- **Robert : plafond de 5 %** (statut « limité »).
  - L'horizon de 3 à 5 ans est très court face à une perte de 51 % de l'or en CAD qui a duré 27 ans.
  - À 5 %, aucune violation, contre 4,3 % à 10 %.
  - Le gain de 10 % est fragile (R6), et la source indépendante (Erb et Harvey) le juge peu fiable.
  - À afficher : « ce plafond coûte 0,73 pt de p10 historique par rapport à 10 % ». **Contradiction avec v0.2 si
    Robert est classé N2** (v0.2 y permet 10 %).
- **Mateo : 0 % par défaut, déblocage à ≤ 5 % sur choix explicite.**
  - Le statut « limité (filière aurifère à documenter ESG) » n'est que **partiellement** levé. La documentation
    existe (LBMA RGG, OCDE, assurance annuelle des affineurs, 10-K de GLD), mais elle relève de l'autorégulation au
    niveau affineur et ne trace pas la mine.
  - En démo, c'est un bon exemple du test « intégrer autre chose que le rendement ». Le système montre
    « or 0 % : −0,72 pt de p10 en CAD », puis « si vous acceptez le standard LBMA : ≤ 5 %, −0,36 pt », sans changer
    la règle inter-ères.
  - Mention honnête : « l'indice ESG de votre cœur (FTSE Choice) n'exclut pas l'extraction d'or ; la règle 0 % est
    donc plus stricte que lui ».
- **Amira : plafond de 10 %** (statut « satellite », concordant avec v0.2 N4-N5), **appliqué aussi** à toute stratégie
  dynamique. Le cœur statique de D5 en a déjà exactement 10 %.
- **Ce qui changerait la résolution** :
  - Robert classé N2 avec une volonté de perte de 15 % : 10 % redeviendrait défendable ;
  - une donnée ESG indépendante sur la filière (traçabilité à la mine, rapports d'ONG) ;
  - une période de taux réels en forte hausse, contexte historique défavorable à l'or. C'est une observation, pas
    une prévision.
- **Confiance** : moyenne. Les chiffres sont solides, mais le choix d'un seuil reste une convention, et le gain de
  l'or tient à peu d'épisodes.
- **Valide** : porteur (seuils) ; préférence ESG simulée de Mateo (déblocage).

---

## D7 — Mateo : comment combler le plancher d'actions de 40 % ?

### D7.1 La question en mots simples
La stratégie de Mateo voulait peu d'actions, mais son profil impose au moins 40 %. Pour combler l'écart, le moteur
répartit le manque **à parts égales** sur tous les placements en actions permis, y compris 11 secteurs que la
stratégie avait volontairement écartés. Résultat : 32 % du portefeuille simulé (USD) part dans des proxys sectoriels.
Les secteurs ont pourtant le statut « limité », et le portefeuille réellement affiché (ESGV, XIU.TO) n'en contient
aucun.

### D7.2 Options
- (a) Accepter : en tickers, il n'y a de toute façon aucun titre.
- (b) Pondérer le remplissage par la capitalisation.
- (c) Reporter le manque sur le cœur large.
- (d) Remplir au prorata de la cible de la stratégie, avec repli sur le cœur.
- (e) Plafonner les secteurs.

### D7.3 Preuves

| source | date | URL | citation exacte | ce que ça prouve |
|---|---|---|---|---|
| Sharpe, W. F., « The Arithmetic of Active Management », *Financial Analysts Journal* 47(1), p. 7-9 (reproduction sur le site de l'auteur) | 1991 | https://web.stanford.edu/~wfsharpe/art/active/active.htm | « A passive investor always holds every security from the market, with each represented in the same manner as in the market. » ; « (1) before costs, the return on the average actively managed dollar will equal the return on the average passively managed dollar » | la pondération par capitalisation est la **référence neutre**. Tout écart (comme des secteurs à parts égales) est un **pari actif**, qui doit être justifié et expliqué |
| FTSE Russell, Ground Rules Global Choice v5.0, règle 6.4 | 2026-08 | https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-choice-index-series-ground-rules.pdf | « The FTSE Global Choice Index Series is weighted by free float adjusted market capitalisation. » | la pratique de l'indice ESG de Mateo est la **capitalisation**, pas les poids égaux par secteur |
| Vanguard, prospectus simplifié ESGV (497K) | 2026-06-30 | https://www.sec.gov/Archives/edgar/data/52848/000005284826000631/f45533d1.htm | « …the FTSE US All Cap Choice Index (the "Target Index"), a market capitalization-weighted index made up of large-, mid-, and small-cap stocks of companies located in the United States… » | même constat pour le véhicule. Le portefeuille en tickers est pondéré par capitalisation, alors que la simulation longue ne l'était pas : **l'explication ne serait pas fidèle** au portefeuille affiché |
| Énoncé officiel FR (p. 17) | 2026 | `source/.../Datathon - Case Officiel 2026 FR.pdf` | « Les explications doivent rester synthétiques, vérifiables et fidèles aux sources et aux actions observables, sans inventer de justification… » | une poche sectorielle créée par la projection, puis présentée comme « parité de risque ESG », serait une justification **non fidèle** à ce que la stratégie a décidé |
| DeMiguel, V., Garlappi, L. et Uppal, R., « Optimal Versus Naive Diversification: How Inefficient is the 1/N Portfolio Strategy? », *Review of Financial Studies* 22(5), p. 1915-1953, DOI 10.1093/rfs/hhm075 | 2009 | https://doi.org/10.1093/rfs/hhm075 | **texte non consulté** (accès OUP refusé, 403) ; métadonnées Crossref | référence classique : le 1/N est dur à battre **entre actifs choisis**. Elle ne justifie pas un 1/N **imposé par la projection** à des actifs que la stratégie avait exclus. Citée sans extrait |

### D7.4 Nos données (`d7_fill.json`, `d7b_sector_cap.json`, roulant 10 ans, ESG, sans ORACLE)
- **Pourquoi des parts égales.** `project()` minimise ‖w − w₀‖². Sur un plancher Σ_{i∈G} w_i ≥ 0,40, le gradient est
  le même pour chaque membre du groupe. La solution ajoute donc le **même montant** à chaque action admissible : en
  USD 1926+, +0,029 à chacun des 11 secteurs (hors énergie) et au cœur. Or `risk_parity_iv36` exclut explicitement
  ces 11 secteurs dans ses paramètres (`profiles/mateo_usd_long_esg.yaml`).
- **Pari actif induit**, à 2026-09 (`d7_fill.json → active_share`). La poche d'actions remplie fait 40,3 %. Son
  **active share contre la capitalisation hors énergie vaut 0,31**. BusEq passe de 44,9 % (capitalisation) à 16,6 %,
  les services publics de 2,5 % à 7,7 % et les télécoms de 1,5 % à 7,5 %.
- **Relances :**

| ère · stratégie | règle | p10 réel | médiane | pire maxDD | violations | proxys sectoriels | cœur `US_MKT_XEN` |
|---|---|---|---|---|---|---|---|
| USD 1926+ · `risk_parity_iv36` | euclidienne (actuelle) | −0,15 % | 3,66 % | 0,404 | 7,7 % | **32,3 %** | 8,4 % |
| | prorata | −0,48 % | 3,86 % | 0,410 | 7,7 % | **0 %** | 40,6 % |
| USD 1975+ · `risk_parity_iv36` | euclidienne | 2,54 % | 5,06 % | 0,162 | 0 % | 31,0 % | 10,1 % |
| | prorata | **3,02 %** | 5,18 % | 0,160 | 0 % | 1,5 % | 39,5 % |
| CAD 1977+ · `risk_parity_iv36` | euclidienne | 3,81 % | 6,02 % | 0,118 | 0 % | 8,1 % | 16,7 % |
| | prorata | **3,86 %** | 5,82 % | 0,119 | 0 % | 0 % | 20,9 % |
| USD 1926+ · `min_variance_60` | les deux règles | −0,42 % | 3,38 % | 0,464 | 6,6 % | **39,9 %** (choisi par l'optimiseur) | 1,0 % |
| | prorata + secteurs ≤ 10 % | −0,65 % | — | 0,492 | 7,7 % | 10,0 % | 30,9 % |

- **Règle inter-ères** (violations ≤ 25 % dans chaque ère, maximiser le pire p10 ; `d7b_sector_cap.json → inter_era`) :

  | variante | 1er | 2e | 3e |
  |---|---|---|---|
  | euclidienne | `risk_parity_iv36` −0,15 % | `min_variance_60` −0,42 % | `mean_var_60_ra10` −0,44 % |
  | prorata | `min_variance_60` −0,42 % | `mean_var_60_ra10` −0,44 % | `risk_parity_iv36` −0,48 % |
  | prorata + secteurs ≤ 10 % | `mean_var_60_ra10` −0,10 % | `risk_parity_iv36` −0,48 % | `min_variance_60` −0,65 % |

  Le choix de la parité de risque reposait en partie sur l'artefact. Les trois premiers tiennent ensuite en
  **0,4 pt**, sur 91 fenêtres qui se chevauchent : le classement est dans le bruit. Avec le correctif, toutes les
  stratégies ont ≤ 10 % de secteurs et les actions vont au cœur ESG.
- **En tickers**, rien ne change : ESGV et XIU.TO, 0 titre. Le correctif rend la simulation longue **cohérente** avec
  le portefeuille affiché.

### D7.5 Résolution proposée : spécification du correctif (le moteur n'est pas modifié ici)
1. **Projection pondérée au lieu d'euclidienne** dans `ConstraintSet.project(w0)`, quand `w0` n'est pas admissible :
   minimiser Σ_i (w_i − w0_i)² / s_i sous les mêmes contraintes, avec s_i = max(w0_i, ε_i). On prend ε_i = 10⁻³
   pour les actifs tagués `broad_market` et ε_i = 10⁻⁶ pour les autres.
   - Effet : un plancher de groupe est comblé **au prorata des poids que la stratégie a choisis**. Si la cible n'a
     aucun actif du groupe, il est comblé sur le **cœur large**.
   - Un actif mis à 0 par la stratégie ne reçoit en pratique rien (≤ 10⁻³ de la correction).
   - Un plafond est réduit au prorata.
   - Repli : si le SLSQP pondéré échoue, garder l'actuel `project()` (euclidien, puis LP). Prototype exact :
     `analysis/decisions/d7_fill.py::project_prorata`.
2. **Plafond de groupe pour le statut « limité »** dans les profils Mateo :
   `{name: sector_proxies_cap, classes: [sector_us], max: 0.10}`. Il empêche aussi les optimiseurs (min-var,
   moyenne-variance) de remettre 39 à 43 % dans des proxys sectoriels par choix d'optimisation.
3. **Trace** : écrire dans chaque décision la part de la correction de projection (‖w − w0‖₁), et le **groupe** qui
   l'a provoquée (« plancher actions 40 % : +30,0 pt sur `US_MKT_XEN` »). L'explication peut ainsi dire « la stratégie
   voulait 10 % d'actions, le profil en impose 40 % ».
4. **Tests** à ajouter :
   - un actif exclu par la stratégie reste ≤ 10⁻³ après projection sur un plancher ;
   - le prorata est respecté : les rapports entre actifs du groupe sont conservés à 10⁻⁶ près ;
   - le cas euclidien actuel est retrouvé quand tous les s_i sont égaux.
5. **Pour le choix de Mateo** (décision D3, traitée ailleurs) : au-delà des violations, ne pas départager des
   stratégies dont le pire p10 diffère de moins de 0,5 pt. Retenir alors la plus simple et la plus proche de la
   capitalisation, ici `risk_parity_iv36` corrigée (0 % de secteurs).

- **Ce qui changerait la résolution** : une demande explicite de **pari sectoriel** (par exemple, Mateo veut
  surpondérer la santé) ; il faudrait alors un statut « satellite » et un plafond affiché. Ou des FNB sectoriels
  documentés dans l'univers des tickers.
- **Confiance** : élevée pour le diagnostic et la règle (mécanisme démontré, effet chiffré, conforme à la pratique
  indicielle) ; moyenne pour le choix de stratégie qui en découle.
- **Valide** : porteur (moteur), avant tout changement de `engine/`.

---

## D8 — ESGV « non backtesté » : que peut-on affirmer honnêtement ?

### D8.1 La question en mots simples
ESGV est le FNB « ESG » de Mateo, mais il n'existe que depuis 2018 : on ne peut pas le tester sur 10 ans. Notre
historique long utilise un substitut, le marché américain sans pétrole, gaz ni charbon. Il faut savoir s'il existe un
historique plus long fiable et comment le dire sans tromper.

### D8.2 Options
- (a) Garder ESGV en cœur avec la mention « ESG non backtesté ».
- (b) Utiliser la règle d'exclusion auditable `US_MKT_XEN` comme référence d'explication, et ESGV comme simple
  véhicule.
- (c) Utiliser l'historique « back-testé » de l'indice FTSE.

### D8.3 Preuves

| source | date | URL | citation exacte | ce que ça prouve |
|---|---|---|---|---|
| Vanguard, prospectus simplifié ESGV (497K), tableau des rendements | 2026-06-30 | https://www.sec.gov/Archives/edgar/data/52848/000005284826000631/f45533d1.htm | « Fund Inception Date Vanguard ESG U.S. Stock ETF Shares 09/18/2018 » ; « The Target Index excludes the stocks of companies that the index provider determines engage in, have a specified level of involvement in, and/or derive threshold amounts of revenue from certain activities or business segments related to the following: adult entertainment, alcohol, tobacco, cannabis, gambling, chemical and biological weapons, cluster munitions, anti-personnel mines, nuclear weapons, conventional military weapons, civilian firearms, nuclear power, and coal, oil, or gas. » | lancement de l'ETF le **2018-09-18**. ESGV exclut **bien plus que les fossiles** : vice, armes, nucléaire, plus les controverses et la diversité (phrase suivante du prospectus) |
| Vanguard, prospectus simplifié ESGV d'origine | 2018-09-18 | https://www.sec.gov/Archives/edgar/data/52848/000093247118007115/sp4393092018.htm | « The index methodology also excludes the stocks of companies that do not meet the labor, human rights, environmental, and anti-corruption standards as defined by the United Nations Global Compact Principles, as well as companies that do not meet certain diversity criteria. » | le filtre « controverses », qui correspond à la demande de Mateo, existe **depuis le lancement** |
| FTSE Russell, fiche « FTSE US All Cap Choice Index » | données au 2026-10-30 | https://research.ftserussell.com/Analytics/FactSheets/Home/DownloadSingleIssue?issueName=FGCUSAC&isManual=False | « Index Launch 13 August 2018 » ; « Base Date 20 March 2015 » ; « Returns shown before the index launch date reflect hypothetical historical performance. » ; « back-tested data may reflect the application of the index or rate methodology with the benefit of hindsight » | l'historique publié par FTSE ne remonte qu'à **2015-03**, dont 41 mois **hypothétiques**, que le fournisseur lui-même dit exposés au biais d'anticipation. **Valeur probante faible**, et trop court pour 10 ans |
| FTSE Russell, idem, rendements annuels et composition | données au 2026-10-30 | idem | 2022 : « FTSE USA All Cap Choice … -24.0 » contre « FTSE Global Equity Index Series wi USA All Cap … -19.2 » ; « Technology 185 47.02 » contre « 214 40.09 » (% de poids) ; « Energy 4 0.06 » contre « 68 4.08 » | l'exclusion se paie dans un choc énergie et taux (−4,8 pt en 2022). Elle surpondère la tech (47 % contre 40 % en ICB), ce qui pèse sur le plafond tech de 30 % de Mateo : 0,6 × 0,47 ≈ 28 % |
| FTSE Russell, Ground Rules v5.0, note 10 et règle 6.1 | 2026-08 | https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-choice-index-series-ground-rules.pdf | « Conduct-Related Exclusions utilise data sourced from Sustainalytics' Global Standards Screening (GSS) dataset. » ; « The FTSE Global Choice Index Series is reviewed quarterly in March, June, September, and December. » | méthodologie publiée et datée. Les controverses reposent sur un **fournisseur tiers** (Sustainalytics), révisé chaque trimestre : on ne peut pas les reconstituer avant 2015, ni de façon point-in-time |
| Énoncé officiel FR (p. 6 et 13) | 2026 | `source/.../Datathon - Case Officiel 2026 FR.pdf` | « Souhaite éviter les entreprises liées à des controverses environnementales ou sociales importantes. » ; « Pour chaque source utilisée, elles expliquent sa pertinence, son origine, sa date, ses traitements et ses limites, ainsi que les conditions d'accès et de réutilisation applicables. » | la demande de Mateo porte sur les **controverses**, que seul ESGV (pas notre proxy) filtre. La limite doit être dite explicitement |

### D8.4 Nos données (`d8_d10_checks.json`, `results/croisement_analysis/concordance.json → mateo_esgv`)
- ESGV dans nos données : 96 mois (2018-10 → 2026-09), **0 fenêtre complète de 10 ans**. L'indice depuis son
  lancement n'en a aucune non plus.
- Avec l'historique hypothétique de FTSE (2015-04 → 2026-10) : seulement **2 fenêtres** roulantes de 10 ans
  (2015-04..2025-03 et 2016-04..2026-03). La première contient 41 mois back-testés (34 %).
- ESGV contre SPY (USD, 2018-10 → 2026-09) : corrélation mensuelle **0,9932**, écart de **+0,05 pt/an**. En 2022 :
  ESGV −24,04 %, SPY −18,18 %, `US_MKT` −19,92 %.
- Indice Choice contre indice parent (fiche FTSE) : écart moyen de **+1,11 pt/an** sur 2019-2025 (années réelles) ;
  de −4,8 pt (2022) à +4,7 pt (2020).
- Notre proxy `US_MKT_XEN` (exclusion fossile seule) : coût médian de l'exclusion −0,03 à +0,02 pt/an pour la parité
  de risque, et 10e centile de −0,23 pt (`reports/mateo.md` §5), mesuré sur 1926-2026.

### D8.5 Résolution proposée pour le prototype
- **Option (b)**. L'explication chiffrée sur longue période cite `US_MKT_XEN` : règle « marché US sans le secteur
  pétrole-gaz-charbon », testable sur 1926-2026 et auditable. ESGV est le **véhicule** affiché en tickers.
- **Ne pas utiliser** l'historique hypothétique de FTSE comme preuve, seulement comme contexte daté.
- **Formulation proposée** (à afficher telle quelle) :
  > « ESGV (Vanguard, lancé le 18 septembre 2018) suit l'indice FTSE US All Cap Choice, lancé le 13 août 2018. Les
  > rendements de cet indice avant son lancement (depuis mars 2015) sont hypothétiques selon FTSE Russell. Il n'existe
  > donc aucun historique réel de 10 ans d'ESGV. Notre historique long (1926-2026) n'est pas celui d'ESGV : c'est une
  > règle simple, le marché américain sans pétrole, gaz ni charbon, qui ne reproduit ni les filtres de controverses
  > (Pacte mondial de l'ONU, données Sustainalytics), ni les exclusions d'armes, de tabac, d'alcool, de jeu ou de
  > nucléaire, ni le critère de diversité. Sur 2018-2026, ESGV a évolué presque comme le S&P 500 (corrélation
  > mensuelle 0,99), mais a perdu 5,9 points de plus en 2022 (USD). »
- **Ce qui changerait la résolution** : l'accès aux constituants historiques datés de l'indice Choice ou des listes
  d'exclusion FTSE (licence), qui permettrait un vrai test point-in-time depuis 2015 ; ou un FNB ESG plus ancien à
  méthodologie stable, à documenter.
- **Confiance** : élevée (sources primaires de l'émetteur et de l'indiciel).
- **Valide** : porteur ; rédacteur de la doc technique (section « sources et limites »).

---

## D10 — CNQ.TO, 2022-08-22 : dividende spécial compté deux fois ?

### D10.1 La question en mots simples
Le 22 août 2022, les données de départ montrent à la fois un dividende et un « fractionnement » de 1,021 pour Canadian
Natural. Si c'est le même événement enregistré deux fois, le rendement 2022 de l'action est gonflé d'environ 3 points.
Il faut le vérifier à la source.

### D10.2 Options
- (a) Garder `adj_close` tel quel (+52,92 % en 2022).
- (b) Corriger le jour du 2022-08-22, comme le fait le moteur (+49,69 %).

### D10.3 Preuves

| source | date | URL | citation exacte | ce que ça prouve |
|---|---|---|---|---|
| Canadian Natural Resources, communiqué « Canadian Natural Resources Limited Announces Special Dividend », pièce 99.1 du 6-K (SEC EDGAR) | 2022-08-04 | https://www.sec.gov/Archives/edgar/data/1017413/000101741322000049/a08042022specialdividend.htm | « …the Board of Directors has declared a special cash dividend on its common shares of C$1.50 (one dollar and fifty cents) per common share. The dividend will be payable on August 31, 2022 to shareholders of record at the close of business on August 23, 2022. » | **dividende spécial en espèces de 1,50 $ CA**, date de clôture des registres le 23 août. Avec le règlement T+2 de 2022, l'ex-dividende tombe le **lundi 22 août**. Il s'agit d'un dividende, **pas d'un fractionnement** |
| Canadian Natural Resources, communiqué « Announces Further Details Regarding Share Split », pièce 99.1 du 6-K | 2024-05-03 | https://www.sec.gov/Archives/edgar/data/1017413/000101741324000022/a05032024sharesplit.htm | « The common shares will commence trading on a split-adjusted basis on June 11, 2024 (the ex-distribution trading date)… » | le seul vrai fractionnement de la période est un **2 pour 1** au 2024-06-11. Les 0,75 $ du starter valent 1,50 $ / 2 |
| Énoncé officiel FR (p. 14) | 2026 | `source/.../Datathon - Case Officiel 2026 FR.pdf` | « Comparabilité : tenir compte, si pertinent, des dividendes, fractionnements, biais de sélection, données manquantes et conversions CAD/USD. » | l'énoncé demande explicitement ce contrôle |
| TSX / SEDAR+ | — | — | non consultés (pas d'accès automatisé). Le dépôt EDGAR de l'émetteur, intercoté NYSE, est une source primaire équivalente | — |

### D10.4 Nos données (`d8_d10_checks.json → d10_cnq`, starter)
- Starter : `corporate_actions.csv` contient, au 2022-08-22, « dividend 0.75 » **et** « split 1.021 », plus le
  « split 2.0 » du 2024-06-11. Dividende du starter = 1,50 / 2 : **vrai**.
- **Prix tels qu'échangés en 2022**, reconstitués (close × 2 × 1,021 avant l'événement, close × 2 après) :
  72,39 $ (2022-08-19), puis 71,33 $ (2022-08-22). Rendement de prix seul : −1,46 %.
- **Rendement total vrai** : (71,33 + 1,50) / 72,39 − 1 = **+0,61 %**. `close` du starter : +0,60 %, déjà « total »
  puisque le faux split a absorbé le dividende. `adj_close` du starter : **+2,78 %**. **Double comptage : 2,17 pt**.
- 1,50 / 72,39 = 2,07 %, très proche de 1 − 1/1,021 = 2,06 % : le « split » 1,021 **est** le dividende spécial.
- Effet annuel : 2022 +49,69 % (corrigé) contre +52,92 % (brut). Août 2022 : +3,97 % contre +6,21 %. CAGR −0,57
  pt/an à période égale (croisement §7, `data/SOURCES.md`, `data_version.json → qa.cnq_fix_2022_08_22`). La formule
  du moteur, (close + dividende) / (close_{t−1} × 1,021) − 1 = 0,006078, coïncide avec la reconstitution ci-dessus.

### D10.5 Résolution proposée pour le prototype
- **Option (b), confirmée.** Garder `fix_cnq_special_dividend()` et le flag `corrected_double_counted_special_dividend`.
- Phrase pour la doc « données » : « Le 22 août 2022 (date ex-dividende), Canadian Natural a versé un dividende
  spécial de 1,50 $ CA par action (communiqué du 4 août 2022, SEC EDGAR 6-K). Yahoo Finance, source du jeu de départ,
  l'a enregistré à la fois comme dividende (0,75 $ après le fractionnement 2 pour 1 de 2024) et comme
  "fractionnement" de 1,021. La clôture ajustée le compte donc deux fois (+2,78 % au lieu de +0,61 % ce jour-là). Nous
  corrigeons ce jour : rendement 2022 de +49,7 % au lieu de +52,9 %. »
- L'erratum de `quant/resultats.md` (fait par son auteur) est **exact**. Seule précision : le montant déclaré est de
  1,50 $ CA par action pré-fractionnement.
- **Contrôle à généraliser** (proposition) : signaler tout « split » de ratio < 1,1 qui coïncide avec un dividende à
  la même date. C'est la signature de ce défaut de Yahoo.
- **Ce qui changerait la résolution** : rien de raisonnable. Une seule réserve : les prix de 2022 sont reconstitués à
  partir des données ajustées, sans relevé TSX consulté.
- **Confiance** : élevée.
- **Valide** : auteur de l'analyse réglementaire (fait) ; porteur des données.

---

## Sources (toutes consultées le 2026-11-14)

1. Canadian Natural Resources Ltd, « Canadian Natural Resources Limited Announces Special Dividend », 6-K pièce 99.1, 2022-08-04. https://www.sec.gov/Archives/edgar/data/1017413/000101741322000049/a08042022specialdividend.htm
2. Canadian Natural Resources Ltd, « …Announces Further Details Regarding Share Split », 6-K pièce 99.1, 2024-05-03. https://www.sec.gov/Archives/edgar/data/1017413/000101741324000022/a05032024sharesplit.htm
3. Vanguard World Fund, prospectus simplifié (497K) de Vanguard ESG U.S. Stock ETF, 2026-06-30. https://www.sec.gov/Archives/edgar/data/52848/000005284826000631/f45533d1.htm
4. Vanguard World Fund, prospectus simplifié (497K) de ESG U.S. Stock ETF, 2018-09-18. https://www.sec.gov/Archives/edgar/data/52848/000093247118007115/sp4393092018.htm
5. FTSE Russell (LSEG), fiche « FTSE US All Cap Choice Index », données au 2026-10-30. https://research.ftserussell.com/Analytics/FactSheets/Home/DownloadSingleIssue?issueName=FGCUSAC&isManual=False
6. FTSE Russell (LSEG), « FTSE Global Choice Index Series – Ground Rules » v5.0, août 2026. https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-choice-index-series-ground-rules.pdf
7. BlackRock Canada (iShares), page produit XBB, données au 2026-11-12. https://www.blackrock.com/ca/investors/en/products/239493/ishares-canadian-universe-bond-index-etf
8. BMO GAM, page produit ZST — **inaccessible** (non citée). https://www.bmogam.com/ca-en/products/exchange-traded-fund/bmo-ultra-short-term-bond-etf-zst/
9. Banque Nationale Investissements, aperçu du fonds « NBI Sustainable Conservative Portfolio – Advisor Series », 2026-05-14. https://www.nbinvestments.ca/content/dam/bni/en/fund/regulatory/fund-facts/NBC9602-Advisor-fund-facts.pdf ; page du fonds (positions au 2026-10-31) https://www.nbinvestments.ca/prices-and-performance/portfolio-solutions/nbc9602.html ; aperçu des fonds au 2026-09-30 https://www.nbinvestments.ca/content/dam/bni/publication/publication-funds-overview.pdf
10. U.S. SEC, Office of Investor Education and Advocacy, Investor Bulletin « Interest rate risk — When Interest Rates Go Up, Prices of Fixed-Rate Bonds Fall » (s.d.). https://www.sec.gov/files/ib_interestraterisk.pdf
11. FINRA, « Brush Up on Bonds: Interest Rate Changes and Duration », 2024-09-19. https://www.finra.org/investors/alerts/duration-what-interest-rate-hike-could-do-your-bond-portfolio
12. Fisher, L. et Weil, R. L. (1971), *Journal of Business* 44(4), 408 et suiv., DOI 10.1086/295402 — métadonnées seulement (Crossref).
13. Redington, F. M. (1952), *Journal of the Institute of Actuaries* 78(3), 286-340, DOI 10.1017/S0020268100052811 — métadonnées seulement (Crossref).
14. Faber, M. T. (2007, mise à jour 2013), « A Quantitative Approach to Tactical Asset Allocation », *Journal of Wealth Management* 9(4), 69-79, DOI 10.3905/jwm.2007.674809. PDF de l'auteur : https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf (SSRN 962461 bloqué).
15. Moskowitz, T. J., Ooi, Y. H. et Pedersen, L. H. (2012), « Time series momentum », *Journal of Financial Economics* 104(2), 228-250, DOI 10.1016/j.jfineco.2011.11.003. Résumé : https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum
16. Hurst, B., Ooi, Y. H. et Pedersen, L. H. (2017), « A Century of Evidence on Trend-Following Investing », *Journal of Portfolio Management* 44(1), 15-29, DOI 10.3905/jpm.2017.44.1.015. Résumé : https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing
17. Asness, C. S., Moskowitz, T. J. et Pedersen, L. H. (2013), « Value and Momentum Everywhere », *Journal of Finance* 68(3), 929-985, DOI 10.1111/jofi.12021. Résumé : https://www.aqr.com/Insights/Research/Journal-Article/Value-and-Momentum-Everywhere
18. Erb, C. B. et Harvey, C. R. (2013), « The Golden Dilemma », *Financial Analysts Journal* 69(4), 10-42, DOI 10.2469/faj.v69.n4.1. Résumé NBER w18706 : https://www.nber.org/papers/w18706
19. World Gold Council, « Gold as a strategic asset: 2026 edition », 2026-02-04 (sections Portfolio impact et ESG credentials). https://www.gold.org/goldhub/research/relevance-of-gold-as-a-strategic-asset — **conflit d'intérêts** : organisme de l'industrie, propriétaire du promoteur de GLD.
20. SPDR Gold Trust, formulaire 10-K (exercice clos le 2025-09-30), déposé le 2025-11-25. https://www.sec.gov/Archives/edgar/data/1222333/000143774925036305/gld20250930_10k.htm
21. LBMA, page « Responsible Sourcing » (RGG v9 en vigueur, v10 en consultation). https://www.lbma.org.uk/responsible-sourcing — **autorégulation** de l'industrie.
22. Sharpe, W. F. (1991), « The Arithmetic of Active Management », *Financial Analysts Journal* 47(1), 7-9. https://web.stanford.edu/~wfsharpe/art/active/active.htm
23. DeMiguel, V., Garlappi, L. et Uppal, R. (2009), *Review of Financial Studies* 22(5), 1915-1953, DOI 10.1093/rfs/hhm075 — métadonnées seulement (Crossref ; OUP 403).
24. PolyFinances, « Datathon 2026 – Énoncé du défi AlphaForge AI » (FR), p. 5, 6, 13, 14, 17, 18. Fichier local `source/Datathon2026/Datathon2026/Datathon - Case Officiel 2026 FR.pdf`.

Sources locales (lecture seule) :
- `reports/{robert,amira,mateo}.md` et `reports/croisement-amira-mateo-robert.md` ;
- `results/croisement_analysis/{bnc,concordance,will_vs_cap,hist2022,stress_anchor,reconcile}.json` ;
- `data/SOURCES.md` ;
- `analyse/relation-profils-actifs/{00-cadre,10-synthese}.md` et `quant/resultats.md` ;
- `github_repo/.claude/risk-table/review/risk_levels_v0.2.yaml`.

Inaccessibles ou non consultés : SSRN (bloqué), JSTOR, OUP, page BMO de ZST, TSX et SEDAR+, et moteurs de recherche
(CAPTCHA ; navigation directe par URL d'émetteur, EDGAR full-text search et Crossref à la place).

## Limites de ce document
- **Une seule sensibilité par décision.** Le 50/50 de D2 et le plafond de 10 % de D7 n'ont pas été optimisés, et
  c'est voulu : ce sont des conventions explicables.
- **Fenêtres qui se chevauchent et petits N** : 3 fenêtres indépendantes de 15 ans en CAD pour Amira, 4 décennies
  pour Mateo. Les écarts de moins de 0,5 pt de p10 ne sont pas significatifs.
- **Proxys.** `CA_GOV_10Y` est lissé, et `US_MKT_XEN` n'est pas ESGV. L'or avant 1975 n'est pas utilisé.
- **Pas d'impôts ni de frais de gestion** dans les backtests (10 pb de transaction seulement). L'argument fiscal de
  D5 est qualitatif.
- **Biais des sources.** WGC, LBMA, AQR et Cambria sont parties intéressées (signalé ligne à ligne). Aucune source ONG
  ou critique indépendante n'a été consultée sur la filière aurifère.
- La correspondance « Portefeuilles BNI (brochure 2025-10) » ↔ « NBI Sustainable Portfolios » est une **hypothèse** :
  les compositions concordent (≈ 65 % d'obligations), mais le document de 00-cadre n'a pas été relu ici.

---

## Réconciliation avec le rapport A (`reports/decisions/A-profil-reglementaire.md`, §D4, §D1, §D3, §D9)

Le rapport A fixe pour Amira une **perte tolérée par défaut de 0,30** (D4). La valeur 0,40 n'est accessible qu'après
confirmation d'un scénario de 40 000 $ sur 100 000 $ et levée du plafond Q5. Or la résolution D5 ci-dessus a été
choisie sous 0,40. Contrôle ci-dessous : mêmes univers, stratégies et fenêtres, seule la limite de baisse change. Script
`analysis/decisions/d5b_amira_w30.py`, sortie `results/decisions_analysis/d5b_amira_w30.json`. Les traces moteur, déjà
produites par le croisement, sont relues directement :
- 0,30 : `results/croisement_runs/x_amira_etf_w30/20261115T{002944Z_non_overlapping_h15,003107Z_rolling_h15,003117Z_rolling_h20}.json`
  et `results/croisement_runs/x_amira_etf_long_usd_w30/20261115T{002949Z_non_overlapping_h15,003136Z_rolling_h15,003208Z_rolling_h20}.json` ;
- 0,40 : `results/croisement_runs/amira_etf/20261115T{003503Z…,003531Z…,003537Z…}.json`
  et `results/croisement_runs/amira_etf_long_usd/20261115T{003507Z…,003602Z…,003615Z…}.json`.

La règle est celle du rapport Amira : une stratégie est éligible dans un run si au plus 10 % de ses fenêtres violent la
limite ; on retient ensuite le plus petit regret maximal de p10. Plafonds inchangés :
- tech look-through ≤ 30 %, secteurs ≤ 30 % (contraintes du profil) ;
- or ≤ 10 % : toutes les statiques ont 0 ou 10 % ;
- titre ≤ 3 % et crypto ≤ 3 % : ils ne lient pas, l'univers FNB n'a ni titre ni crypto.

### R1. `E80_us50_g10_t0` respecte-t-il 0,30 ?
- **CAD 1977+, oui, de justesse.** Pire baisse **0,290** sur les trois runs (non chevauchant 15 ans, roulant 15 ans,
  roulant 20 ans). Taux de violation **0 %** dans les trois, donc éligible. La marge n'est que de **1,0 pt**, et nos
  données mensuelles sous-estiment les creux : SPY 2021-2026 donne 0,2225 en quotidien contre 0,1867 en mensuel
  (croisement §7). Le rapport A (§D4) note la même fragilité pour `Mom_etf_top3` (0,304).
- **USD 1926+ : non évaluable.** `E80_us50_g10_t0` n'existe pas dans cet univers, qui n'a ni `CA_EQ` ni or avant
  1975. Ses analogues USD sont **inéligibles** sous 0,30 :
  - `E80_us100_g0_t0` : pire baisse 0,728, violations 50 % en non chevauchant et 54,7 % / 67,9 % en roulant 15 / 20 ans ;
  - `E70_us100_g0_t0` : pire baisse 0,662, violations 50 % / 46,5 % / 60,5 %.

### R2. Quel cœur statique diversifié respecte 0,30 ?

**Règle sur 6 runs (CAD + USD)** : **aucune** stratégie statique n'est éligible partout, aussi bien sous 0,30 que sous
0,40. Sous 0,30, la seule stratégie éligible sur les 6 runs est `RP_invvol_36m` (regret 2,96 pt, 16 à 36 % d'actions,
croisement §3.1). Ce n'est pas un cœur de croissance.

**Même règle sur les 3 runs CAD** (devise d'Amira ; c'est aussi l'ère que demande l'ancrage D9 du rapport A) :

| rang sous 0,30 (tout confondu) | regret max | pire baisse |
|---|---|---|
| 1. `Mom_etf_top3_core50` | 0,40 pt | 0,263 |
| 2. **`E70_us50_g10_t0`** (1re statique) | **0,50 pt** | **0,238** |
| 3. `E80_us50_g10_t0` | 0,62 pt | 0,290 |

Il y a 9 statiques éligibles sur les 3 runs CAD sous 0,30, et 25 sous 0,40. Sous 0,30, `Mom_etf_top3` est
**inéligible** en CAD : 33,3 / 31,4 / 36,7 % de violations, pire baisse 0,304. `Trend10_E80` reste éligible en CAD
(0,190), mais pas en USD 1926+ (0,344, 15 à 17 % de violations).

`Mom_etf_top3_core50` arrive premier sous 0,30 en CAD. Il reste inéligible en USD 1926+ (0,558). C'est l'option
« tilt borné » de §D5.5, et elle ne change pas.

**Proposition pour la branche par défaut** : `E70_us50_g10_t0`, avec 70 % d'actions, ce qui reste dans la bande N4
« Croissance » de v0.2 [0,60 ; 0,80]. Elle est première parmi les statiques et laisse une marge de 6,2 pt sous 0,30.
`E80_us50_g10_t0` passe aussi, mais avec 1 pt de marge seulement.

### R3. Les deux branches côte à côte (démo Amira)

| | **défaut : limite 0,30** (rapport A, D4) | **confirmée : limite 0,40** (scénario 40 000 $ + quiz Q5) |
|---|---|---|
| condition | aucune : borne basse de « plus de 30 % », profil AMF 4 | Amira confirme une baisse de 40 000 $ sur 100 000 $ et réussit le quiz Q5 |
| cœur statique | `E70_us50_g10_t0` : 35 % SPY, 35 % XIU.TO, 10 % GLD, 20 % XBB.TO | `E80_us50_g10_t0` : 40 % SPY, 40 % XIU.TO, 10 % GLD, 10 % XBB.TO |
| ce qui change d'une branche à l'autre | — | +10 pt d'actions (5 SPY + 5 XIU.TO), −10 pt de XBB.TO |
| actions / or / obligations | 70 % / 10 % / 20 % | 80 % / 10 % / 10 % |
| tech look-through au 2026-09 | ≥ 15,2 % (0,35 × 0,4355 ; XIU.TO compté à 0) | ≥ 17,4 % (0,40 × 0,4355) |
| p10 réel, CAD (non chev. 15 ans / roul. 15 ans / roul. 20 ans) | 6,48 / 4,82 / 5,65 % | 6,76 / 4,70 / 5,82 % |
| médiane réelle (mêmes runs) | 6,53 / 6,84 / 7,02 % | 6,94 / 7,17 / 7,29 % |
| pire baisse, CAD 1977+ ; violations | 0,238 ; 0 % | 0,290 ; 0 % |
| rang minimax CAD (statiques) | 1er (0,50 pt) | 2e (0,85 pt), derrière `E90_us50_g10_t0` (0,75 pt, pire baisse 0,339 > 0,30) |
| USD 1926+ (scénario informatif) | aucun statique éligible ; 1929-1932 : 0,66 à 0,73 pour 70 à 80 % d'actions | idem ; la règle sur 6 runs retient `Mom_etf_top3` (1,53 pt) |
| satellites (inchangés) | titres tech ≤ 3 % chacun, tant que SPY × BusEq + panier ≤ 30 % ; crypto ≤ 3 % | idem |
| à afficher | « 30 000 $ sur 100 000 $ : votre limite actuelle. Le portefeuille garde 70 % d'actions sur deux marchés. » | « Vous avez confirmé 40 000 $ : +10 pt d'actions, au prix d'une pire baisse historique de 29 % au lieu de 24 % (CAD, mensuel). » |

Pour `E80_us50_g10_t0` au lieu de `E90_us50_g10_t0` dans la branche 0,40 : l'écart de regret (0,10 pt) est dans le
bruit. E80 garde 4 classes et reste sous 0,30. Le passage d'une branche à l'autre se résume alors à un seul déplacement
explicable, de 10 pt de XBB.TO vers les actions.

Arrondi : le regret de 0,74 pt donné en §D5.4 vient des scores arrondis de `will_vs_cap.json`. Relu dans les traces, il
vaut 0,75 pt (`d5b_amira_w30.json`). Le classement ne change pas.

### R4. Autres écarts entre A et B
1. **Robert, D2 et D6, supposent la capacité** : maxDD 0,23 et CVaR5 0,036 à 4 ans.
   - A (§D1) met Q10 en « manquant » et donne un résultat **provisoire sous l'a priori N1 de v0.2** : bande d'actions
     [0,10 ; 0,25], mdd 0,140, cvar_m 0,027, `gold_max` 0,05.
   - Conséquences sous N1 : le BNC **Conservateur (30 % d'actions) sort de la bande N1**. Le BNC compatible est
     **Prudent** (20 %) : avec revenu fixe court, p10 +0,32 %, pire baisse 0,091, 0 % de violations, mais mesuré sous les
     limites de **capacité** (croisement §4, `bnc.json`).
   - La règle D2 (duration ≤ horizon) s'applique telle quelle, mais à Prudent. Le plafond d'or de 5 % (D6)
     **concorde** avec N1 : la contradiction signalée en §0.1 ne vaut que pour N2.
   - **Non recalculé** : la conformité aux seuils N1 (mdd 0,140, cvar_m 0,027, plus strict que 0,036). C'est à relancer
     si l'équipe retient N1 comme limite du moteur.
2. **Robert, branche « 15 000 $ » de A** : elle affiche `eq20_gold10` (pire baisse ≈ 9 700 $). Avec le plafond d'or
   de 5 % (D6), le portefeuille affiché devient `gold05` : pire baisse **0,1043** (≈ 10 400 $), p10 +0,80 % au lieu de
   +1,53 %, 0 % de violations au lieu de 4,3 % (`results/robert_sens_cad_gold/20261114T223144Z_rolling_h4.json`).
   Précision de formulation : avec 15 %, la limite appliquée est min(0,15 ; 0,23) = **0,15** (et non « la capacité 0,23
   redevient la limite »). Elle ne lie pas, puisque les pires baisses sont de 0,097 et 0,104.
3. **Mateo (A §D3)** : si Q10 = 15 % est confirmé, la bande [40 %, 80 %] cède. Les chiffres de D6 et D7 ont été
   calculés sous la capacité 0,20 et la bande actuelle, et **ne sont pas recalculés** pour cette branche. Point
   d'attention : le choix sous 0,15, `min_variance_60`, met **39,9 %** en proxys sectoriels par optimisation en
   USD 1926+ (`d7b_sector_cap.json`). Le plafond sectoriel de 10 % proposé en D7 compte donc encore plus dans cette
   branche.
4. **Ère de mesure (A §D9)** : A ancre sur la pire perte d'une histoire longue **dans la devise de l'investisseur**.
   C'est cohérent avec la proposition D5 (règle restreinte aux runs CAD pour Amira). Pour Mateo, A demande la même ère
   pour la catégorie et pour le choix. Or la règle inter-ères de Mateo (D7) inclut USD 1926+. Si l'équipe retient CAD :
   `risk_parity_iv36` corrigée fait p10 3,86 % (`d7_fill.json`).
5. **Seuils de sélection proches de la limite** : A (§D4) demande que la règle ne dépende pas d'un écart de 0,4 pt
   (`Mom_etf_top3` 0,304 contre 0,30). La branche par défaut ci-dessus applique ce principe, avec une marge de 6,2 pt
   au lieu de 1 pt.
