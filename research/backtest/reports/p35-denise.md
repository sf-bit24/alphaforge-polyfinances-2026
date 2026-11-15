# Persona 35 · Denise Fortier : backtest 1926-2026 en devise de dépense, oracle, choix robuste et croisement réglementaire

> **Simulation historique uniquement, à partir de données publiques.** Ce document ne constitue pas un conseil financier
> personnalisé et n'entraîne aucune transaction. Les lignes `ORACLE` (`hindsight=True`) utilisent le futur : elles sont
> **non investissables** et ne servent qu'à la rétro-ingénierie. **Aucune prévision du taux de change n'est faite ni
> suggérée** : les chiffres USDCAD décrivent le passé. Les seuils ci-dessous sont des **propositions à valider par
> l'équipe**, dérivées des données ; aucun seuil, aucune allocation ni aucun « fait de marché » de la fiche persona n'a
> été utilisé.

Chemins relatifs à `research/backtest/`. Chaque chiffre renvoie à la trace qui l'a produit. Les traces contiennent
`engine_sha256`, `data_version.data_sha256` (`008f122d5da4f8f7`), la graine 42 et les paramètres. Notation : « p10 » =
10e centile entre fenêtres ; « panier » = panier de dépenses mixte CAD/USD (§2.2) ; « richesse réelle » = richesse finale
exprimée en unités de panier, retraits compris, pour 1 investi.

## 1. Question et poches

Denise (70 ans) passe novembre → avril en Floride et paie alors en USD. Le persona teste la capacité du système à
**raisonner en devise de dépense** : quelle part des actifs devrait « vivre » en USD, et comment expliquer le risque de
change sans parier sur le huard. De la fiche `source/profils_investisseurs/35-denise-ex-agente-de-voyages.md`, on ne
retient que l'identité, les contraintes RRTTLLU (liquidité ≈ 1 an de dépenses USD au départ de chaque hiver ; risque de
séquence ; horizon 15–20 ans ; sous-horizon USD ≈ 8–10 hivers), les objectifs, les biais (market timing de change,
regret, comptabilité mentale, ancrage sur un taux) et les critères ✅/❌. Les poches sont celles de l'analyse
réglementaire (`analyse/relation-profils-actifs/personas-tous.csv`, lignes `id=35`) :

| poche | rôle | horizon de fenêtre retenu (justification) | devise de mesure |
|---|---|---|---|
| **A — réserve USD hiver** | payer l'hiver qui vient (6 paiements mensuels USD, nov. → avr.) | **6 mois**, roulant pas 1 mois (= tous les mois de départ possibles) + 55 hivers « financés fin octobre » ; variante préfinancée fin avril (12 mois) | USD, déflaté par le CPI US |
| **B — patrimoine 15–20 ans** | revenu stable + croissance modérée, retraits | **15 ans** (borne basse de l'horizon : la plus exigeante pour le pire cas), roulant pas 12 mois + non chevauchant ; sensibilités 20 ans et 10 ans (≈ sous-horizon USD) | CAD, déflaté par le **panier** mixte |

Taille de A (scénario, montants fictifs de la fiche) : 32 000 USD × USDCAD 1,396 (fin 2026-10, `results/p35_analysis/fx_stats.json` → `fx_history.level.last`) ≈ 44 700 CAD, soit ≈ 6,5 % de 690 000 CAD ; B ≈ 645 300 CAD.

## 2. Données, ères et méthode « devise de dépense »

### 2.1 Ères

| ère | rôle | profil(s) | période effective |
|---|---|---|---|
| **CAD 1971/1977+ (principale)** | USDCAD réel (FRED DEXCAUS jusqu'en 2021-10, puis starter BdC) | `profiles/p35_A_usd.yaml` (1971-02+), `profiles/p35_B_cad.yaml` (1977-01+, CA_EQ limitant) | A : 1971-02 → 2026-09 ; B : 1977-01 → 2026-09 |
| USD 1926+ (contrôle) | robustesse des **classes d'actifs** seulement ; **ne dit rien du change** | `profiles/p35_B_usd1926.yaml` (CPI US, actifs US, sans or) | 1926-08 → 2026-09 |
| tickers réels | traduction et vérification | `profiles/p35_A_tickers.yaml` (2011-03+, ZST.TO limitant), `profiles/p35_B_tickers.yaml` | 2021-11 → 2026-09 (59 mois) |

Proxys : `data/SOURCES.md`. Les actifs USD sont convertis par `(1+r_usd)(USDCAD_t/USDCAD_{t−1}) − 1` au taux de fin de
mois ; le starter n'a pas de ligne les jours fériés canadiens, le moteur prend le dernier jour disponible du mois
(forward-fill dans le mois). Sur le calendrier quotidien TSX ∪ US (1 282 jours), **37 jours sans taux BdC** sont remplis
par le dernier taux connu (ex. 2021-12-27, 2022-07-01, 2022-10-10) ; `results/p35_analysis/fx_stats.json` →
`starter_daily`.

### 2.2 Le panier de dépenses (hypothèse déclarée)

Les dépenses sont un **passif mixte** : une part `s` en USD (CPI US, convertie au taux du moment) et `1 − s` en CAD (IPC
Canada). Inflation mensuelle du panier en CAD : `π_b = s·[(1+π_US)(1+Δfx) − 1] + (1−s)·π_CA` (parts rééquilibrées chaque
mois, hypothèse). Un rendement déflaté par ce panier mesure le **pouvoir d'achat sur les dépenses réelles de Denise**,
quelle que soit la devise d'affichage. **Scénario de base `s = 0,5`** (6 mois sur 12, pondéré par le temps) ; la part
pondérée par les montants réels est une **information manquante** (dépenses CAD du ménage inconnues), d'où une grille
`s ∈ {0,3 ; 0,4 ; 0,5 ; 0,6 ; 0,7}`. Implémentation : `analysis/p35/common.py` (`basket_inflation`, `run_custom` = boucle
du moteur `run_window`/`oracle_window` avec cette inflation externe, car `engine.run` n'utilise que l'IPC d'une devise).

Retraits de B (scénario) : 4 %/an de la poche initiale, indexés au panier, mensuels ; sensibilités 3 / 5 / 6,9 % (6,9 % =
toutes les dépenses USD payées par le portefeuille, `results/p35_analysis/derive_b.json` → `withdrawal_scenarios`).
Objectif B : `min_shortfall` sur `target_real_wealth = 1 − 0,04·H` (richesse qu'on aurait avec un rendement réel nul) →
`shortfall_prob` = probabilité de ne pas maintenir le pouvoir d'achat net des retraits. Le moteur ne fait jouer les flux
que sur la richesse finale ; la séquence (épuisement) est recalculée dans `analysis/p35/derive_b.py`.

## 3. Le change USDCAD dans les données (description, pas prévision)

Source : `results/p35_analysis/fx_stats.json` (mensuel 1971-01 → 2026-10, 670 mois ; quotidien starter 2021-11-12 → 2026-11-12).

| mesure | valeur |
|---|---|
| fourchette 1971-2026 (fin de mois) | min 0,9486 (2011-04) · p10 1,0014 · **médiane 1,2466** · p90 1,4249 · max 1,6049 (2002-02) |
| fourchette 2021-2026 | mensuel : min 1,2087 · médiane 1,3574 · max 1,4484 ; quotidien starter : min 1,2451 (2022-04-05) · médiane 1,3658 · max 1,4603 (2025-02-03) |
| volatilité annualisée (log, mensuelle) | 6,59 % sur 1971-2026 ; de 3,98 % (années 1970) à 9,62 % (années 2000) ; 5,36 % (quotidien 2021-2026) |
| variation sur 6 mois (≈ un hiver) | p05 −6,6 % · médiane +0,5 % · p95 +6,7 % ; extrêmes −15,0 % / +24,4 % |
| variation sur 12 mois | p05 −9,0 % · p95 +10,1 % ; \|Δ\| > 10 % dans 9,9 % des cas |
| pires épisodes pour une dépense en USD (12 mois) | 2008-02 → 2009-02 : +29,7 % (0,9796 → 1,271) ; 2014-08 → 2015-08 : +21,8 % ; 1976-10 → 1977-10 : +14,0 % |
| pire épisode sur 6 mois | 2008-05 → 2008-11 : +24,4 % ; 2022-03 → 2022-09 : +9,7 % |
| plus forte baisse du CAD face à l'USD | −40,1 % (pic 1974-04 → creux 2002-02, retour 2007-10) |
| 2021-11-12 → 2026-11-12 (starter) | 1,2565 → 1,4255 : **+13,45 %** |

**Lecture pour l'agent d'explicabilité** : il n'existe pas de « bon taux » dans les données ; la médiane change selon la
période (1,13 sur 1971-1985, 1,35 sur 1986-2000, 1,13 sur 2001-2015, 1,33 sur 2016-2026, même trace →
`range_by_window`). Le taux de 6 mois varie de ±6,6 % dans 90 % des cas.

**Effet du change sur les actifs US (2021-11 → 2026-09, mensuel, `fx_stats.json` → `decomposition`)** : rendement en CAD
= (1 + rendement USD) × (1 + ΔUSDCAD) − 1, avec ΔUSDCAD = +2,78 %/an sur la période.

| actif | CAD /an | USD /an | vol CAD | vol USD | maxDD CAD | maxDD USD | 2022 CAD | 2022 USD | corr(r_USD, ΔUSDCAD) |
|---|---|---|---|---|---|---|---|---|---|
| SPY | 15,51 % | 12,38 % | 13,35 % | 15,57 % | 0,187 | 0,239 | −12,59 % | −18,18 % | −0,54 |
| AGG | 2,13 % | −0,63 % | 6,08 % | 6,61 % | 0,101 | 0,158 | −7,08 % | −13,02 % | −0,53 |
| JNJ | 16,72 % | 13,56 % | 17,90 % | 17,84 % | 0,142 | 0,157 | +13,21 % | +5,97 % | −0,16 |
| PG | 5,71 % | 2,85 % | 18,27 % | 18,46 % | 0,202 | 0,215 | +1,44 % | −5,05 % | −0,20 |
| GLD | 21,60 % | 18,31 % | 16,42 % | 17,35 % | 0,210 | 0,238 | +6,01 % | −0,77 % | −0,34 |
| ZST.TO (CAD) | 3,43 % | 0,63 % | 0,62 % | 6,10 % | 0,004 | 0,093 | +1,22 % | −5,25 % | — |

Sur 1971-2026, la corrélation mensuelle US_MKT (USD) ↔ ΔUSDCAD vaut −0,42 et, pendant les 33 pires mois des actions US
(5 %), l'USD a gagné en moyenne +2,30 % contre +0,07 % en moyenne générale (même trace → `long_1971`). **Pour une
investisseuse canadienne, l'USD a historiquement amorti les krachs** : c'est un fait passé, pas une garantie.

**Risque de change « utile » vs « non désiré »** (`results/p35_analysis/usd_share.json`, `s = 0,5`) : la part `min(u, s)`
des actifs USD couvre des dépenses USD (utile) ; l'écart `|u − s|` est une exposition non désirée. Couche « encaisse »
(UST_TBILL / CA_TBILL) : la volatilité du rendement réel en panier due au change vaut 2,14 points à u = 0, **0 à u = s =
0,5**, 2,38 points à u = 1. Couche 40 % actions : 1,71 point à u = 0, 0 à u = 0,5, et −0,42 / −0,44 point à u = 0,75 / 1
(l'USD en excès a *réduit* la volatilité, effet « valeur refuge » ci-dessus).

## 4. Poche A — réserve USD de l'hiver

### 4.1 Couverture d'un hiver (`analysis/p35/pocket_a.py`, `results/p35_analysis/pocket_a.json`)

Réserve financée fin octobre avec exactement le montant CAD nécessaire au taux du jour (sans marge), 6 paiements USD
indexés au CPI US. Couverture = 1 + solde final / total payé (< 1 = manque). 55 hivers (1971/72 → 2025/26) :

| option (proxys) | moyenne | p10 | pire (hiver) | écart-type | part < 1 | marge pour couvrir le pire | pire préfinancé fin avril | pire, tout mois de départ |
|---|---|---|---|---|---|---|---|---|
| **USD T-bills, conversion unique** | 1,0039 | 0,9946 | 0,9773 (2021) | 0,0090 | 0,29 | **2,3 %** | 0,9436 | 0,9670 |
| USD 2 ans, conversion unique | 1,0061 | 0,9895 | 0,9618 (2021) | 0,0159 | 0,40 | 4,0 % | 0,9247 | 0,9453 |
| USD 5 ans, conversion unique | 1,0079 | 0,9760 | 0,9524 (2021) | 0,0278 | 0,38 | 5,0 % | 0,8875 | 0,9173 |
| encaisse CAD, tranches mensuelles | 1,0032 | 0,9738 | 0,9360 (2014) | 0,0279 | 0,49 | 6,8 % | 0,8340 | 0,8849 |
| obligations CA 10 ans, tranches | 1,0145 | 0,9666 | 0,9339 (2021) | 0,0442 | 0,40 | 7,1 % | 0,8343 | 0,8734 |
| 50 % USD T-bills + 50 % CAD en tranches | 1,0035 | 0,9890 | 0,9662 (2021) | 0,0157 | 0,42 | 3,5 % | 0,9283 | 0,9573 |

FNB réels, 15 hivers 2011-2025 (même trace → `etf_2011`) : AGG conversion unique pire 0,9456 (marge 5,75 %) ; ZST.TO en
tranches pire 0,9319 (marge 7,31 %, 60 % des hivers < 1) ; USD T-bills pire 0,9773.

**Lecture** : en moyenne, garder du CAD et convertir au fil de l'eau ne rapporte ni ne coûte (1,0032 contre 1,0039) ;
il ajoute de la **dispersion** (écart-type 0,028 contre 0,009). Le pire hiver en USD T-bills (2021/22) vient de
l'**inflation** US, pas du change. Le risque grandit avec le délai : préfinancer six mois plus tôt en CAD fait tomber le
pire cas à 0,834.

### 4.2 Conversion unique vs tranches (biais de regret et d'ancrage)

Taux moyen payé par 6 tranches mensuelles ÷ taux de fin octobre − 1, sur 55 hivers (`pocket_a.json` →
`proxies_1971.lump_vs_tranches_rate`) : médiane +0,58 %, p10 −2,89 %, p90 +2,72 %, extrêmes −4,90 % (hiver 2020/21,
regret maximal d'avoir tout converti) et +8,01 % (hiver 2014/15, regret maximal d'avoir attendu). Les tranches ont été
moins chères dans 40 % des hivers ; écart absolu moyen 2,12 %. **Aucune des deux règles ne gagne systématiquement** ;
les tranches réduisent l'écart au taux moyen de l'hiver, la conversion unique supprime le risque une fois converti.

### 4.3 Backtest moteur de la poche A (6 mois, roulant pas 1 mois)

Trace `results/p35_A_usd/20261114T235516Z_rolling_h0.5.json` (663 fenêtres, USD, CPI US) :

| stratégie | p10 réel ann. | médiane | pire | pire maxDD (USD) | taux de violation (maxDD > 0) |
|---|---|---|---|---|---|
| **usd_tbill_lump** (choix robuste) | −0,0310 | 0,0044 | −0,1131 | 0,000 | 0,000 |
| usd_2y_lump | −0,0458 | 0,0067 | −0,1698 | 0,039 | 0,783 |
| half_usd_half_cad | −0,0540 | 0,0097 | −0,1592 | 0,090 | 0,750 |
| usd_5y_lump | −0,0822 | 0,0100 | −0,2859 | 0,099 | 0,923 |
| cad_tbill_unconverted | −0,0900 | 0,0102 | −0,3121 | 0,187 | 0,858 |
| cad_10y_unconverted | −0,1441 | 0,0294 | −0,3704 | 0,178 | 0,962 |

ORACLE : poids USD p10 / médiane / p90 = 0 / 0,61 / 1 en UST_TBILL (`results/p35_analysis/tables.json` →
`oracle_ranges_A`) ; il saute d'une devise à l'autre selon le change réalisé. Walk-forward (655 fenêtres hors
échantillon) : choix toujours `usd_tbill_lump`, score moyen 0,0049, P(perte réelle) 0,434, écart moyen à l'oracle 0,052
(trace, `summary`). Version tickers 2011+ (`results/p35_A_tickers/20261114T235632Z_rolling_h0.5.json`, 182 fenêtres) :
même choix ; AGG p10 −0,0813 et pire maxDD 0,102 ; ZST.TO p10 −0,1218 et maxDD 0,149 en USD.

**Coût d'inflation de l'encaisse** : même la meilleure option perd du pouvoir d'achat USD dans 43 % des fenêtres de
6 mois (`shortfall_prob` 0,431) et une marge de 2,3 % aurait été nécessaire pour couvrir le pire hiver.

## 5. Part USD des actifs : dérivation (`analysis/p35/usd_share.py`, `results/p35_analysis/usd_share.json`)

Pour u = 0 → 100 % (pas 5), toutes les fenêtres roulantes (pas 1 mois) de H ans ; métrique = **couverture d'un passif
consommé uniformément sur H ans** (1/(12H) unité de panier par mois, partie USD convertie au taux du moment).
**Règle (proposition)** : u\* = argmax du **pire** cas de couverture (ex æquo à 0,001 près → le u le plus proche de s) ;
on donne aussi la bande des u à moins d'un point du meilleur pire cas.

**Couche « encaisse » (UST_TBILL vs CA_TBILL, 1971+) = l'effet devise pur** :

| s (part USD des dépenses) | H = 1 an : u\* [bande] | H = 8 ans : u\* [bande] | H = 15 ans : u\* [bande] | pire couverture H8 : u=0 / u=s / u=1 |
|---|---|---|---|---|
| 0,3 | 0,50 [0,10–0,55] | **0,30** [0,15–0,40] | **0,30** [0,20–0,45] | 0,903 / 0,941 / 0,820 |
| 0,4 | 0,55 [0,20–0,65] | **0,40** [0,25–0,45] | **0,40** [0,35–0,55] | 0,884 / 0,940 / 0,838 |
| **0,5** | 0,60 [0,25–0,75] | **0,50** [0,35–0,55] | **0,50** [0,45–0,65] | 0,866 / 0,940 / 0,858 |
| 0,6 | 0,70 [0,30–0,85] | **0,60** [0,45–0,65] | **0,60** [0,55–0,70] | 0,848 / 0,936 / 0,873 |
| 0,7 | 0,75 [0,40–0,95] | **0,65** [0,55–0,75] | **0,70** [0,65–0,80] | 0,830 / 0,933 / 0,887 |

Le minimum de volatilité du rendement réel en panier est exactement u = s pour la couche encaisse (`best.u_min_vol`).
**Résultat dérivé : sur 8 et 15 ans, la part USD qui minimise le pire manque est u\* ≈ s** (appariement actif-passif),
avec une bande d'environ [s − 0,15 ; s + 0,15] (union des bandes H8 et H15 pour s = 0,5 : [0,35 ; 0,65]). Pour s = 0,5,
le pire manque sur 15 ans passe de 9,4 % (u = s) à 17,1 % (u = 0) ou 19,1 % (u = 1).

**Couches avec actions (1977+)** : la règle devient **non robuste**. À 40 % d'actions et s = 0,5, u\* = 0,50 sur 15 ans,
mais 0,15 sur 8 ans et 0,25 sur 1 an ; à 60 % d'actions, u\* = 0,35 sur 15 ans ; à 20 %, 0,70. Le minimum de volatilité
se situe *au-dessus* de s (u = 0,70 pour e40, effet valeur refuge). Couche obligations 10 ans : u\* = 0,65 à 1,00 (le
résultat reflète la performance relative UST_10Y vs CA_GOV_10Y, pas le change). **Conclusion** : on ancre la part USD
sur s par la logique de passif (robuste), et l'on considère tout écart au-delà de la bande comme une exposition « non
désirée » dont l'effet historique dépend de la fenêtre.

## 6. Seuils dérivés de la poche B (propositions à valider)

Script `analysis/p35/derive_b.py`, trace `results/p35_analysis/derive_b.json`.

**Volonté** : AMF Q10 « ≈ 15 % » **[inf]** (`analyse/relation-profils-actifs/personas-lot3.md`, persona 35, poche B, plafond
Q10 → 3) → `L_will = 0,15` (baisse maximale du TWR nominal en CAD, devise du relevé).

**Capacité** (règle lisible) : un mélange statique est admissible si sa plus longue période sous l'eau (TWR nominal,
rebalancement annuel) sur l'ère reste ≤ **96 mois = 8 hivers**, borne basse des séjours prévus : une perte doit être
récupérée pendant que les dépenses USD courent encore. Grille e = 0 → 100 % d'actions, u = 50 %, jambes 10 ans / 5 ans
US + 10 ans CA / T-bills.

| ère | L_cap (mélange frontière) | part d'actions max admissible | remarque |
|---|---|---|---|
| CAD 1977+ | **0,390** (100 % actions, 66 mois sous l'eau) | 100 % pour les 3 jambes | 0 % actions (jambe 10 ans) : maxDD 0,233 et 76 mois sous l'eau (1977-1981) |
| USD 1926+ | 0,722 (80 % actions / jambe 5 ans, 89 mois) | 70–80 % selon la jambe (T-bills 70, 10 ans 75, 5 ans 80) | sensibilité 180 mois : 0,812 |

**Limite retenue = min(0,15 ; 0,390) = 0,15 : la volonté (Q10) gagne** (31-103CP : le plus bas des deux). La capacité
n'est pas liante, même avec retraits : à 4 %/an sur 20 ans, aucun mélange de 20 à 60 % d'actions ne s'épuise, alors que
l'encaisse pure (u = 0,5) s'épuise dans 20 % des fenêtres à 5 %/an et 73 % à 6,9 %/an (`sequence.cash_u50`). À 6,9 %/an
sur 20 ans, même 40 % d'actions s'épuise dans 6,7 % des fenêtres (`sequence.e40_u50`).

**Or (statut « limité »)** : base 40/u50, or pris au prorata, fenêtres 15 ans, retraits 4 %. Règle : plus grande part
telle que le p10 de richesse réelle s'améliore à chaque pas de 5 points et que le taux de violation ne dépasse pas
celui de 0 %. p10 : 0,920 (0 %) → 0,950 → 0,974 → **0,992 (15 %)** → 0,985 (20 %) → **plafond or = 15 %**.

**Secteurs défensifs US (proxy des « titres connus », statut « satellite »)** : p10 0,920 → 0,953 → 0,992 (10 %) → 1,025
(15 %), mais le taux de violation passe de 0 à 0,314 à 15 % → **plafond = 10 %**.

**Titre individuel** (`analysis/p35/satellite_names.py`, `results/p35_analysis/satellite_names.json`, fenêtres 10 ans
1995+) : taille max par titre = min(chemin, stress) avec stress = (L − pire maxDD de la base, 0,120–0,121) / pire baisse propre
du titre : RY.TO 6 %, TD.TO 5 %, FTS.TO 9 %, ENB.TO 9 %, JNJ 8 %, PG 6 %. Hypothèse de perte totale (biais du
survivant) : 2,9–3,0 %.

## 7. Poche B : résultats par fenêtre, choix robuste, walk-forward

Univers CAD 1977+ : CA_EQ, US_MKT, US_IND_NODUR, US_IND_HLTH, CA_GOV_10Y, UST_5Y, CA_TBILL, UST_TBILL, GOLD ; 33
stratégies (6 portefeuilles BNC publics en CA_GOV_10Y / CA_EQ / US_MKT, les mêmes avec une jambe obligataire US qui
porte la part USD à 50 %, grille actions × part USD, or, secteurs, encaisse, glidepath, parité de risque, min-variance,
moyenne-variance, tendance, momentum). Rebalancement annuel, 10 pb. Contraintes : or ≤ 15 %, secteurs ≤ 10 %, crypto
exclue ; `max_drawdown` 0,15 mesuré.

### 7.1 Par fenêtre (non chevauchant ; tableaux complets `results/p35_analysis/tables.md`)

Trace `results/p35_B_cad/20261114T235443Z_non_overlapping_h15.json` :

| fenêtre | ORACLE (> 3 %) | ORACLE richesse réelle / maxDD | meilleure ex-ante a posteriori (richesse) | risk_parity_36m richesse / maxDD / réel ann. | BNC Pondéré | BNC Équilibré |
|---|---|---|---|---|---|---|
| 1977-01..1991-12 | US_MKT 0,40, CA_TBILL 0,35, GOLD 0,15, US_IND_NODUR 0,10 | 1,722 / 0,150 | momentum_top3 (2,517) | 1,075 / 0,109 / 5,08 % | 1,254 | 1,417 |
| 1992-01..2006-12 | CA_EQ 0,55, CA_GOV_10Y 0,35, US_IND_NODUR 0,10 | 2,185 / 0,150 | bnc_actions (2,536) | 1,505 / 0,055 / 6,23 % | 1,949 | 2,118 |
| 2007-01..2021-12 | US_MKT 0,52, GOLD 0,15, UST_5Y 0,12, CA_GOV_10Y 0,11, US_IND_HLTH 0,10 | 1,574 / 0,150 | bnc_actions (1,548) | 1,049 / 0,051 / 4,35 % | 1,038 | 1,188 |

20 ans (`results/p35_B_cad/20261114T235420Z_non_overlapping_h20.json`) : 1977-1996 ORACLE US_MKT 0,90 + US_IND_NODUR 0,10
(richesse 4,041, maxDD 0,304, limite violée) ; 1997-2016 ORACLE CA_EQ 0,49, GOLD 0,15, CA_GOV_10Y 0,14, UST_5Y 0,12,
US_IND_HLTH 0,10 (1,710). L'oracle sature presque toujours les plafonds (or 15 %, secteurs 10 %, maxDD 0,15) et change de
devise d'une fenêtre à l'autre. « Meilleure ex-ante » = connue seulement après coup.

### 7.2 Sélection robuste (meilleur p10 ; exclusion si violation > 10 % des fenêtres)

| exécution (trace) | choix robuste | p10 richesse réelle | pire richesse | pire maxDD | 2e / 3e |
|---|---|---|---|---|---|
| **CAD 15 ans roulant, s = 0,5** (`p35_B_cad/20261114T235756Z_rolling_h15.json`, 35 fenêtres) | **risk_parity_36m** | 1,040 | 0,858 | 0,109 | e40_u50_gold15 (0,993) ; e40_u50_gold10 (0,974) |
| CAD 15 ans non chevauchant (3 fenêtres) | bnc_pondere_usdfi | 1,092 | 1,048 | 0,137 | bnc_pondere ; e40_u50_def10_gold10 |
| CAD 20 ans roulant (`…235713Z_rolling_h20.json`, 30) | e40_u0 | 1,144 | 0,676 | 0,134 | risk_parity_36m (1,109) ; e40_u50_gold15 (1,046) |
| CAD 20 ans non chevauchant (2) | bnc_pondere | 1,511 | 1,489 | 0,134 | e40_u50_def10 |
| CAD 10 ans roulant (`p35_B_cad_h10/…235436Z_rolling_h10.json`, 40) | e40_u50_gold15 | 0,974 | 0,770 | 0,113 | e40_u50_gold10 ; risk_parity_36m |
| s = 0,3 (`p35_B_cad_s03/…235429Z_rolling_h15.json`) | risk_parity_36m | 1,068 | 0,948 | 0,109 | e40_u50_gold15 |
| s = 0,7 (`p35_B_cad_s07/…235427Z_rolling_h15.json`) | risk_parity_36m | 1,019 | 0,781 | 0,109 | e40_u50_gold15 |
| USD 1926+ roulant (`p35_B_usd1926/20261114T235835Z_rolling_h15.json`, 86) | bncus_prudent (= 20 % US_MKT / 80 % UST_5Y) | 0,356 | 0,267 | 0,153 | risk_parity_36m (0,313, maxDD 0,147, 0 violation) |
| USD 1926+ non chevauchant (`…235442Z_non_overlapping_h15.json`, 6) | risk_parity_36m | 0,413 | 0,216 | 0,123 | cash_100 |

(Lignes tirées de `results/p35_analysis/tables.md`.) En USD 1926+, toutes les stratégies à 50 % d'actions ou plus
violent la limite 0,15 dans 57 à 100 % des fenêtres (krachs 1929-1932 et 1973-1974 sans l'amortisseur du change).

**Poids moyens de `risk_parity_36m`** (CAD 15 ans, `results/p35_analysis/crosscheck.json` → `B15_robust`) : CA_EQ 0,128,
US_MKT 0,134, US_IND_NODUR 0,060, US_IND_HLTH 0,041, CA_GOV_10Y 0,272, UST_5Y 0,208, CA_TBILL 0,017, UST_TBILL 0,017,
GOLD 0,123 ; **part USD 0,583** (0,460 sans compter l'or) ; poids stables entre fenêtres (CA_GOV_10Y 0,22–0,32, GOLD
0,09–0,14). Mise en garde : CA_GOV_10Y est construit sur des taux moyens mensuels (volatilité sous-estimée), ce qui
favorise la parité de risque ; le statique `e40_u50_gold15` (17/17/25,5/25,5/15) est presque aussi robuste et plus
lisible.

### 7.3 Walk-forward et coût de ne pas connaître le futur

| exécution | fenêtres hors échantillon | choix successifs | p10 hors échantillon (richesse) | écart moyen ORACLE − choix (richesse) |
|---|---|---|---|---|
| CAD 15 ans | 18 | e40_u100 ×10, glide_e50_to_e30 ×3, e40_u50_def10 ×2, bnc_pondere_usdfi ×2, e40_u50_def10_gold10 ×1 | 0,617 | 1,000 |
| CAD 20 ans | 8 | bnc_pondere ×6, bnc_pondere_usdfi ×2 | 0,869 | 0,639 |
| USD 1926+ 15 ans | 69 | risk_parity_36m ×47, e30_10y ×12, e20_10y ×10 | — (score p10 −0,101) | — |

Sources : `tables.md` (choix) et `crosscheck.json` (`walk_forward_final_real_wealth_p10`, `walk_forward_gap_…`). L'écart
moyen entre l'ORACLE et le choix robuste vaut 0,964 unité de richesse réelle (médiane 0,758) sur 15 ans. **Le
walk-forward CAD a d'abord choisi 100 % de la part étrangère en USD (e40_u100)**, parce que les premières fenêtres
terminées (1977-1992…) favorisaient l'USD ; son p10 hors échantillon (0,617) est nettement sous le p10 en échantillon de
la stratégie robuste (1,040). Le choix de la part USD sur la seule performance passée est instable ; c'est un argument
de plus pour l'ancrer sur le passif (§5).

## 8. Volonté vs capacité : effet sur la stratégie robuste (B2)

Re-sélection sur les mêmes fenêtres avec chaque limite (`crosscheck.json` → `B2_reselect`) :

| poche / exécution | limite de volonté | limite de capacité | min appliqué | choix avec volonté | choix avec capacité | meilleur BNC (volonté / capacité) |
|---|---|---|---|---|---|---|
| A (6 mois, USD) | 0,15 (même personne, Q10 [inf]) ; profil AMF 1 ⇔ Q10 « 0 % » | **0** (réserve = un hiver, aucune perte absorbable sans marge) | **0 → capacité** | usd_tbill_lump (CAD non converti : violation 0,9 %) | usd_tbill_lump, seul à 0 violation (les autres : 75–96 %) | — |
| B 15 ans | **0,15** | 0,390 | **0,15 → volonté** | risk_parity_36m | e60_u50 (p10 score 1,749, maxDD 0,179) | bnc_pondere_usdfi / bnc_equilibre |
| B 20 ans | **0,15** | 0,390 | 0,15 → volonté | e40_u0 | momentum_top3 | bnc_pondere_usdfi / bnc_croissance |
| B USD 1926+ | 0,15 | 0,390 | 0,15 | bncus_prudent | e60_10y | — |

Appliquer la capacité seule ferait passer la poche B de ≈ 35–40 % à 60 % d'actions. La volonté déclarée (inférée) est
donc la contrainte qui façonne la stratégie ; si l'équipe confirme Q10 = 30 %, le choix change.

## 9. Rétro-ingénierie (`analysis/p35/reverse.py`, `results/p35_analysis/reverse.json`)

Variables observées à la fin du mois **précédant** chaque fenêtre : différentiel de taux courts CA − US, variation USDCAD
12 mois, USDCAD / sa médiane glissante 120 mois, différentiel d'inflation, écart de rendement actions CA − US 12 mois.
ρ de Spearman. Poche A : fenêtres de 6 mois non chevauchantes (N = 110). Poche B : 35 fenêtres roulantes 15 ans
(N effectif ≈ 3, cohérence seulement). ~10 tests par échantillon.

**Stabilité de l'oracle** : A, part USD moyenne 0,73, écart-type 0,37, à 0 dans 14 % et à 1 dans 51 % des fenêtres ;
B 15 ans, part USD p10–p90 0,11–0,95, actions p10–p90 0,44–0,70, or à 0 dans 51 % des fenêtres.

| # | règle | données | confiance |
|---|---|---|---|
| R1 | **Apparier la part USD des actifs à la part USD des dépenses minimise le pire manque** sur 8 et 15 ans (u\* = s pour s = 0,3…0,7), avec une bande ≈ ±0,15 | §5, couche encaisse, 1971-2026 | **robuste** (toutes les valeurs de s, deux horizons ; mécanique de passif, pas une prévision) |
| R2 | **Une réserve d'hiver en USD converti couvre mieux le pire hiver** (marge 2,3 % contre 6,8 % en CAD converti par tranches) ; l'écart moyen est nul | §4.1, 55 hivers ; FNB 2011+ | **robuste** |
| R3 | **Aucune règle de conversion (unique vs tranches) ne gagne systématiquement** | §4.2 (tranches moins chères dans 40 % des hivers) | **robuste** (résultat nul) |
| R4 | **La parité de risque / un ≈ 40/50/10-15 (actions / obligations / or) reste en tête du p10** dans les ères CAD et USD et pour s = 0,3–0,7 | §7.2 | **robuste en rang**, mais dépend des obligations lissées et de l'or post-1975 |
| R5 | **Le portefeuille BNC Pondéré avec jambe obligataire US respecte la limite 0,15 ; sa version 100 % obligations CA la viole dans 11 % des fenêtres** | §11 B4 | **fragile** (une seule ère, écart faible) |
| R6 | **Or ≤ 15 % améliore le p10** ; au-delà, il se dégrade | §6 | **fragile** (ère 1975+ seulement, quelques fenêtres) |
| R7 | Part USD de l'oracle B ↔ variation USDCAD 12 mois au départ : ρ = −0,42 (p = 0,012), −0,29 avant 1999, −0,34 après ; ↔ écart actions CA − US 12 mois : ρ = +0,42 | `B15_corr_rolling` | **non concluante** (fenêtres chevauchantes, N effectif ≈ 3) |
| R8 | Part USD de l'oracle A ↔ différentiel de taux CA − US : ρ = −0,24 (p = 0,011) mais signe opposé avant/après 1999 (−0,13 / +0,10) ; les 9 autres tests de A sont non significatifs | `A_corr_nonoverlap` | **non concluante** |

**Aucune de ces associations n'est causale**, et aucune ne permet de prévoir le huard : R7 et R8 sont précisément les
« signaux de change » que la gouvernance doit refuser d'utiliser comme pari tant qu'ils ne sont pas validés.

## 10. Traduction en tickers et vérification 2021-11 → 2026-09

Correspondances (`data/processed/assets.csv`) : CA_EQ → XIU.TO, US_MKT → SPY, CA_GOV_10Y → XBB.TO (approx.), UST_5Y → AGG
(approx.), GOLD → GLD, US_IND_NODUR → PG, US_IND_HLTH → JNJ, CA_TBILL → ZST.TO. **UST_TBILL n'a pas d'équivalent dans
l'univers du starter** (pas d'encaisse USD) : il est gardé comme proxy « compte/fonds monétaire USD », hors univers.

**Poche A (simulation)** : 6 mois de dépenses USD convertis en une fois en **encaisse USD (T-bills, hors univers)**.
Meilleur substitut dans l'univers : AGG (marge 5,75 % pour couvrir le pire hiver 2011+, maxDD USD 0,102), puis ZST.TO
gardé en CAD et converti par tranches (marge 7,31 %).

**Poche B (simulation)** : parité de risque 36 mois ; approximation statique **XIU.TO 13 · SPY 13 · PG 6 · JNJ 4 ·
XBB.TO 27 · AGG 21 · GLD 12 · ZST.TO 2 · encaisse USD 2** (part USD ≈ 0,58).

Vérification, trace `results/p35_analysis/ticker_check.json` (historique chargé dès 2011-03 pour les estimations de la
parité de risque ; fenêtre évaluée 2021-11 → 2026-09 ; retraits 4 % ; aucune violation de la limite 0,15 en CAD) :

| stratégie | nominal CAD | réel CAD (IPC CA) | nominal USD | réel USD (CPI US) | réel panier | maxDD CAD | maxDD USD | pire 12 mois | richesse réelle |
|---|---|---|---|---|---|---|---|---|---|
| **risk_parity_36m (tickers)** | 8,55 % | 4,93 % | 5,61 % | 1,46 % | 3,13 % | 0,095 | **0,163** | −5,68 % | 0,931 |
| approximation statique | 8,41 % | 4,79 % | 5,47 % | 1,32 % | 3,00 % | 0,094 | 0,162 | −5,59 % | 0,926 |
| e40_u50_gold15 | 8,98 % | 5,35 % | 6,03 % | 1,86 % | 3,54 % | 0,102 | 0,170 | −7,17 % | 0,950 |
| BNC Pondéré, jambe US | 7,35 % | 3,77 % | 4,44 % | 0,33 % | 1,99 % | 0,134 | 0,195 | −10,40 % | 0,873 |
| BNC Pondéré | 7,02 % | 3,46 % | 4,13 % | 0,03 % | 1,68 % | 0,141 | 0,203 | −11,23 % | 0,858 |
| BNC Équilibré | 9,21 % | 5,57 % | 6,26 % | 2,08 % | 3,76 % | 0,146 | 0,208 | −11,10 % | 0,957 |
| encaisse ZST.TO | 3,43 % | −0,01 % | 0,63 % | −3,33 % | −1,73 % | 0,004 | 0,093 | +0,56 % | 0,723 |
| encaisse USD (T-bills) | 6,66 % | 3,10 % | 3,77 % | −0,31 % | 1,33 % | 0,042 | 0,000 | −2,45 % | 0,861 |

Les six portefeuilles BNC (trace `results/p35_B_tickers/20261114T235401Z_non_overlapping_h4.9167.json`, `tables.md`) :
réel panier Prudent −1,80 %, Conservateur −0,41 %, Pondéré 1,68 %, Équilibré 3,76 %, Croissance 6,53 %, Actions 9,28 % ;
maxDD CAD 0,131 → 0,160 (Croissance 0,153 et Actions 0,160 dépassent 0,15). ORACLE a posteriori : SPY 0,75, GLD 0,15,
JNJ 0,10 (richesse 1,389). **Une seule trajectoire, 2022 et +13 % d'USD compris : ce n'est pas une preuve.**
Le même portefeuille a une baisse maximale de 0,095 mesurée en CAD et de 0,163 mesurée en USD : la limite de volonté
dépend de la devise du relevé, ce qui doit être affiché.

## 11. Croisement avec l'analyse réglementaire

### B1. Statuts → contraintes

| poche · classe | statut (`personas-tous.csv`) | traduction moteur |
|---|---|---|
| A · actions CA, actions US, FNB actions, or, crypto | exclu | absents de l'univers A (poids 0) |
| A · FNB oblig. | cœur | univers A = encaisse et obligations ; pas de plafond |
| B · FNB actions, FNB oblig. | cœur | pas de plafond |
| B · actions CA, actions US (titres) | satellite | secteurs US ≤ 10 % (§6) ; par titre 5–9 % (§6) |
| B · or | limité | or ≤ 15 % (§6) |
| B · crypto | exclu | absente |
| « pas maintenant » | aucune poche de Denise | coût d'inflation de l'encaisse montré quand même (§4.3 ; ZST.TO réel panier −1,73 %/an, §10) |

### B2. Volonté vs capacité : voir §8 (A : capacité 0 gagne ; B : volonté 0,15 gagne).

### B3. Tableau de concordance (poche × classe)

Poids robuste = poids moyen de la stratégie robuste ; plage oracle = p10–p90 du poids de la classe dans l'ORACLE
(`crosscheck.json` : `A_robust`, `B15_robust`).

| poche | classe | statut | poids robuste | plage oracle p10–p90 | verdict | explication |
|---|---|---|---|---|---|---|
| A | actions CA | exclu | 0 | non testé (hors univers) | cohérent | Horizon de 6 mois : même les obligations 5 ans violent la limite 0 dans 92 % des fenêtres. |
| A | actions US | exclu | 0 | non testé | cohérent | Idem. |
| A | FNB actions | exclu | 0 | non testé | cohérent | Idem. |
| A | FNB oblig. / encaisse | cœur | 1,00 (USD T-bills) | 1,00–1,00 | cohérent | Seule classe retenue ; la meilleure *forme* est l'encaisse **USD**, absente de l'univers, comme l'analyse le signale (« AGG a une duration »). |
| A | or | exclu | 0 | non testé | cohérent | GLD n'est pas une encaisse USD (maxDD de GLD en USD 0,238 sur 2021-2026, §3). |
| A | crypto | exclu | 0 | non testé | cohérent | Refus explicite. |
| B | actions CA (titres) | satellite | 0 (non inclus) | non testé (aucun titre CA dans l'univers 1977+) | **à trancher** | Plafond dérivé par titre 5–9 % (RY.TO 6, TD.TO 5, FTS.TO 9, ENB.TO 9), mais l'apport des titres CA à la stratégie n'a pas été testé. |
| B | actions US (titres, proxy secteurs) | satellite | 0,101 | 0,07–0,10 | cohérent | L'oracle sature le plafond satellite de 10 % ; au-delà, la limite de baisse est violée. |
| B | FNB actions | cœur | 0,263 | 0,40–0,60 | cohérent | Bloc de croissance présent dans toutes les stratégies robustes ; le choix robuste en tient moins que l'oracle, c'est le prix du pire cas. |
| B | FNB oblig. | cœur | 0,513 | 0,15–0,48 | cohérent | Plus gros bloc du choix robuste ; il porte la stabilité exigée par Q10. |
| B | or | limité | 0,123 | 0,00–0,15 | cohérent | Utile jusqu'à 15 % (p10), absent de l'oracle dans 51 % des fenêtres : c'est bien « limité ». |
| B | crypto | exclu | 0 | non testé | cohérent | Refus explicite. |

**Bilan : 11 cohérents, 1 à trancher, 0 contradiction.** Réserve : pour les classes exclues de A, la concordance est en
partie construite (l'oracle ne pouvait pas les choisir).

### B4. Profil BNC assigné vs portefeuille BNC le plus robuste

- **Poche A** : assigné « Liquidités/Prudent ». Backtest : seule l'encaisse USD tient la limite de 0 ; Prudent (80/6/14)
  contient 20 % d'actions, ce qui contredit le statut « exclu » des actions de la même poche. **Liquidités concorde,
  Prudent ne concorde pas** (à corriger dans l'analyse : A → Liquidités).
- **Poche B** : assigné « Pondéré/Équilibré ». Sous la limite 0,15, le BNC le plus robuste est **Pondéré avec jambe
  obligataire US** (`bnc_pondere_usdfi` : rang 4/33 en roulant 15 ans, 1/33 en non chevauchant, 7/33 en 20 ans, pire
  maxDD 0,140) ; Pondéré tel quel viole la limite dans 11,4 % des fenêtres (pire 0,157) ; **Équilibré la viole dans 100 %
  des fenêtres de 15 ans** (pire 0,193, `tables.json`). **Pondéré concorde ; Équilibré contredit la volonté Q10 de 15 %**
  et ne redevient admissible qu'avec la limite de capacité (0,39), § 8. **À trancher par l'équipe** : retenir Pondéré
  seulement, ou confirmer Q10 = 30 %.

### B5. Réconciliation des chiffres (`fx_stats.json` → `reconciliation_B5`)

Leur méthode (`quant/stats_classes.py`) a été ré-implémentée : elle reproduit leurs chiffres à 1e-4 près. On fait
ensuite varier un facteur à la fois.

| actif | leurs chiffres (quotidien, 2021-11-12 → 2026-11-12) CAGR / vol / maxDD | quotidien → 2026-09-30 | quotidien 2021-11-30 → 2026-09-30 | mensuel, même série | moteur, 58 mois (2021-12 → 2026-09) | moteur, 59 mois (avec 2021-11) |
|---|---|---|---|---|---|---|
| SPY (CAD) | 14,47 % / 16,50 % / 0,222 | 14,91 % / 16,44 % / 0,222 | 15,25 % / 16,47 % / 0,222 | 15,24 % / 13,46 % / 0,187 | 15,24 % / 13,46 % / 0,187 | 15,51 % / 13,35 % / 0,187 |
| AGG (CAD) | 2,24 % / 7,31 % / 0,128 | 1,89 % | 1,45 % / 7,34 % / 0,128 | 1,45 % / 5,95 % / 0,101 | 1,45 % / 5,95 % / 0,101 | 2,13 % / 6,08 % / 0,101 |
| GLD (CAD) | 18,21 % / 18,22 % / 0,260 | 20,30 % / 18,04 % / 0,237 | 21,40 % | 21,39 % / 16,56 % / 0,210 | 21,39 % / 16,56 % / 0,210 | 21,60 % / 16,42 % / 0,210 |
| XBB.TO | 0,71 % / 6,57 % / 0,155 | 0,40 % | 0,26 % | 0,26 % / 6,25 % / 0,130 | 0,26 % / 6,25 % / 0,130 | 0,41 % / 6,21 % / 0,130 |
| CNQ.TO | 28,68 % / 30,37 % / 0,331 | 28,26 % | 28,47 % / 30,14 % / 0,331 | 28,46 % / 28,55 % / 0,206 | **27,89 %** / 28,51 % / 0,206 | 27,18 % / 28,30 % / 0,206 |
| USDCAD | +13,45 % au total (1,2565 → 1,4255) | 2,52 %/an, vol 5,38 % | 2,17 %/an | 2,17 % / 5,86 % / 0,064 | 2,17 % / 5,86 % | 2,78 % / 5,97 % |

Explication des écarts :
1. **Date de fin** : 2026-11-12 contre 2026-09-30. GLD : 18,21 % → 20,30 %, et maxDD 0,260 → 0,237 (la baisse de l'or
   d'octobre-novembre 2026 n'est pas dans la fenêtre du moteur).
2. **Date de début** : le mois « 2021-11 » du moteur part de fin octobre 2021 (yfinance), alors que leur base est le
   2021-11-12. Sur 58 mois (base 2021-11-30), le moteur reproduit **exactement** l'échantillonnage mensuel de leur série
   quotidienne : le moteur et le starter ont les mêmes données.
3. **Fréquence** : en mensuel, la volatilité baisse (SPY 16,47 % → 13,46 %) et la perte maximale aussi (0,222 → 0,187),
   car les creux intra-mois disparaissent. Ce point **inverse une de leurs conclusions** : en quotidien, le change
   ajoute de la volatilité à AGG (7,3 % en CAD contre 6,1 % en USD, `resultats.md`) ; en mensuel, il en retire (6,08 % en
   CAD contre 6,61 % en USD), car la corrélation mensuelle AGG ↔ USDCAD vaut −0,53 (§3).
4. **Change** : ils appliquent le taux BdC du jour avec report sur les 37 jours fériés ; le moteur prend le taux de fin
   de mois. USDCAD total : +13,45 % des deux côtés sur leur fenêtre.
5. **CNQ.TO** : le moteur corrige le dividende spécial compté deux fois le 2022-08-22 (rendement d'août 2022 : 6,21 % brut
   contre 3,97 % corrigé). À fréquence et période égales, cela fait **−0,57 point/an** (28,46 % → 27,89 %). Leur
   contrôle n'a pas trouvé de saut aberrant parce que le double comptage (+2,2 points) reste plus petit que les plus
   fortes variations du titre.

### B6. Comparaison avec le bloc YAML du persona (oracle de test, lu en dernier)

| règle YAML | nos conclusions | verdict |
|---|---|---|
| `no_fx_forecast: true` | aucune prévision ; R7 et R8 non concluants ; la gouvernance doit refuser le pari | cohérent |
| `usd_asset_share_target_band: [s − 0,10 ; s + 0,15]` | bande dérivée (couche encaisse) ≈ [s − 0,15 ; s + 0,05] à 8 ans et [s − 0,05 ; s + 0,15] à 15 ans ; part USD du choix robuste B = 0,58 pour s = 0,5 (dans la bande YAML) | **cohérent** (même ordre de grandeur, asymétrie haute retrouvée à 15 ans) |
| `all_returns_reported_in: [CAD, USD]` | §3 et §10 en CAD, USD et panier | cohérent |
| `fx_missing_days: forward_fill_and_disclose` | 37 jours remplis, documentés (§2.1) | cohérent |
| `no_crypto: true` | crypto exclue | cohérent |
| `min_usd_liquidity_months: 6` | poche A = 6 mois de dépenses USD en encaisse USD ; il faut ajouter **une marge dérivée de 2,3 %** pour le pire hiver | cohérent (+ précision) |
| soft flags : timing de conversion, retenue US, résidence | §4.2 traite le timing ; retenue US et résidence fiscale non modélisées (hors système) | cohérent |
| missing_info | identique (dépenses USD réelles → s ; qui paie quoi ; assurance ; nombre d'hivers) ; on ajoute le KYC de Réal | cohérent |

## 12. Signaux candidats pour l'étape 2 (non testés comme signaux de décision)

- **Différentiel de taux BoC − Fed** (V39079 − DFF dans `macro_rates.csv`) et pente relative des courbes : R8 (A) non
  concluant ; à tester en point-in-time sur le *coût de portage* de la réserve USD, pas comme prévision du change.
- **Prix du pétrole / termes de l'échange** (devise liée aux matières premières) comme explication *ex post* des
  épisodes 2008 et 2014-2015 (§3).
- **Inflation des postes de dépense de Denise** : CPI loyers de Floride (CPI régional Miami/Tampa), CPI soins médicaux US
  (franchise santé à l'étranger) au lieu du CPI-U national.
- Corrélation glissante actions US ↔ USDCAD (régime « valeur refuge » §3) : si elle devient positive, le surplus d'USD
  n'amortit plus les krachs.
- Fondamentaux / nouvelles : politique budgétaire et commerciale É.-U./Canada (tarifs), calendrier des décisions BoC/Fed,
  traité fiscal (retenue à la source de 15 % sur les dividendes US dans un compte non enregistré, à vérifier par un
  professionnel).

## 13. Limites

- **Scénarios** : `s = 0,5` et les retraits à 4 % sont des hypothèses ; la vraie part USD des dépenses manque. Le
  résultat u\* ≈ s est robuste à s, mais pas la valeur de u à retenir.
- **Proxys** : UST_TBILL (encaisse USD) est hors de l'univers du starter ; CA_TBILL est un taux interbancaire ;
  CA_GOV_10Y est lissé (vol sous-estimée, ce qui flatte la parité de risque) ; XBB.TO face à CA_GOV_10Y : corrélation de
  0,58 et ZST.TO face à CA_TBILL : 0,49 (README) ; « actions mondiales » BNC ≈ US_MKT ; secteurs KF ≠ titres connus.
- **Peu de fenêtres indépendantes** : 3 fenêtres de 15 ans et 2 de 20 ans en CAD ; les fenêtres roulantes se chevauchent.
  L'ère CAD ne contient ni 1929 ni 1973-1974 en actions ; l'ère USD montre que la limite de 0,15 y aurait imposé environ
  20 % d'actions.
- **Change** : 1971+ seulement ; le résultat « l'USD amortit les krachs » est historique (§3) et peut cesser.
- **Or** investissable seulement depuis 1975 ; biais du survivant pour les titres ; révisions FRED ; pas de frais de
  gestion, d'impôts, de retenue US, ni de CELI/FERR (le minimum de retrait FERR n'est pas modélisé).
- **Panier** : parts rééquilibrées chaque mois, CPI national et non floridien.
- **ORACLE** pénalisé : il sature les limites (maxDD 0,150 dans les fenêtres de 15 ans).

**Problèmes du moteur ou des données** (moteur et `data/` non modifiés) :
1. `engine.run` déflate seulement par l'IPC d'une devise : pas de passif mixte. Contournement : `analysis/p35/common.py:run_custom`.
2. Les flux n'affectent que la richesse finale : la séquence et l'épuisement sont recalculés dans `derive_b.py`.
3. `assets.csv` → `maturity_years` est lu comme chaîne (`''` pour le cash) : conversion manuelle dans `reverse.py`.
4. `fx_monthly.parquet` → colonne `source` = « FRED DEXCAUS » sur les 670 lignes, alors que, selon `data/SOURCES.md`,
   les valeurs après 2021-11 viennent du starter. Les valeurs correspondent au starter (2026-09 : 1,4188) : c'est une
   **étiquette erronée** à corriger dans `build_data.py`.
5. `load_returns(start="2021-11")` inclut le rendement d'octobre-novembre 2021 (yfinance) : une « période réelle
   2021-11 → 2026-09 » commence donc le 2021-10-31, pas le 2021-11-12 (§11 B5).
6. Coût d'exécution : oracle sur 663 fenêtres de 6 mois ≈ 9 minutes CPU ; ce n'est pas un bug.

## 14. Les quatre questions

- **Quelles données ?** Rendements mensuels reconstitués (Ken French, obligations synthétiques FRED/Shiller/BdC, or,
  yfinance puis starter officiel), USDCAD FRED DEXCAUS puis starter BdC (37 jours fériés remplis), CPI-U et IPC Canada ;
  hash `008f122d5da4f8f7`. Détails : `data/SOURCES.md`.
- **Pourquoi ce choix ?** Les dépenses de Denise sont à moitié en USD (scénario `s`) : on mesure tout en **pouvoir
  d'achat sur son panier mixte**. Ainsi :
  - la réserve d'hiver en USD converti est la seule option qui n'a jamais perdu en USD et qui demande la plus petite
    marge (2,3 %) ;
  - une part USD des actifs ≈ part USD des dépenses minimise le pire manque (§5) ;
  - pour le patrimoine, sous la limite de baisse de 15 % (volonté, plus basse que la capacité), une parité de risque
    ≈ 26 % actions larges + 10 % titres défensifs + 51 % obligations CA/US + 12 % or a le meilleur 10e centile.
- **Quelles limites ?** Celles du §13 : `s` et les retraits sont des scénarios, l'encaisse USD est hors univers, les
  obligations CA sont lissées, il y a peu de fenêtres indépendantes, le change n'est connu que depuis 1971, sans impôts
  ni retenue US.
- **Qu'est-ce qui changerait la réponse ?**
  - la part USD réelle des dépenses : la cible u suit s ;
  - la fin des hivers en Floride ou l'achat d'un condo en USD : le passif USD disparaît ou devient un actif USD ;
  - Q10 confirmée à 30 % : 60 % d'actions, BNC Équilibré admissible (§8) ;
  - un retrait de 6,9 %/an (toutes les dépenses USD payées par le portefeuille) : risque d'épuisement sur 20 ans (§6) ;
  - la mesure de la baisse en USD plutôt qu'en CAD (0,163 contre 0,095, §10) ;
  - un régime où l'USD cesse d'amortir les krachs ;
  - des frais, des impôts et la retenue US réels.

## 15. Reproduire

```bash
cd research/backtest
.venv/bin/python -I analysis/p35/fx_stats.py
.venv/bin/python -I analysis/p35/pocket_a.py
.venv/bin/python -I -m engine.run --profile p35_A_usd --mode rolling --step 1 --horizon 0.5 --out results/p35_A_usd
.venv/bin/python -I -m engine.run --profile p35_A_tickers --mode rolling --step 1 --horizon 0.5 --out results/p35_A_tickers
.venv/bin/python -I analysis/p35/usd_share.py
.venv/bin/python -I analysis/p35/derive_b.py
.venv/bin/python -I analysis/p35/make_profiles.py      # écrit p35_B_cad / p35_B_usd1926 / p35_B_tickers
for j in cad_roll15 cad_non15 cad_roll20 cad_non20 cad_roll15_s03 cad_roll15_s07 cad_roll10 tickers; do
  .venv/bin/python -I analysis/p35/run_b.py $j; done
.venv/bin/python -I -m engine.run --profile p35_B_usd1926 --mode rolling --step 12 --out results/p35_B_usd1926
.venv/bin/python -I -m engine.run --profile p35_B_usd1926 --mode non_overlapping --out results/p35_B_usd1926
.venv/bin/python -I analysis/p35/satellite_names.py
.venv/bin/python -I analysis/p35/ticker_check.py
.venv/bin/python -I analysis/p35/reverse.py
.venv/bin/python -I analysis/p35/crosscheck.py
.venv/bin/python -I analysis/p35/tables.py              # results/p35_analysis/tables.md
```
Note : `make_profiles.py` écrit aussi les groupes au niveau des tickers (GLD ≤ 0,15 ; PG + JNJ ≤ 0,10). Les scripts lisent la trace la plus récente de chaque dossier.
