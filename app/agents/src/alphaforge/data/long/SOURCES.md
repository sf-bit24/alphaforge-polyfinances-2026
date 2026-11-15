# Sources de données : traitements, hypothèses, limites

Tout est reconstruit par `alphaforge/finance/backtest/build_data.py` (`uv run --group finance --group backtest-data python -I -m alphaforge.finance.backtest.build_data`, voir `finance/backtest/README.md`). Les fichiers bruts vont dans
`data/long/raw/<source>/` (un dossier par source, avec un `manifest.json` qui donne l'URL, l'horodatage
UTC de récupération et le sha256), et ne sont **pas** versionnés. Les dates de récupération
exactes sont recopiées dans `data/long/data_version.json` (`raw_manifests`). Build de
référence : récupération du **2026-11-14**, dernier mois complet 2026-10.

Conventions communes
- **Fréquence mensuelle.** Chaque rendement est daté du **dernier jour du mois civil** (`date` = fin de mois).
- **Rendements totaux** (dividendes / coupons réinvestis), simples, en décimal.
- **Quotidien → mensuel** : dernière observation disponible du mois civil, sans forward-fill
  d'un mois sur l'autre. On évite ainsi les problèmes de calendrier (fériés TSX ≠ US, crypto 7 j/7) :
  chaque série est ramenée à la fin de mois de son propre calendrier, puis toutes partagent le
  même index mensuel. Le décalage résiduel (par exemple crypto au 31 vs TSX au 30) vaut au plus quelques jours.
- **Mois incomplet exclu** : le mois en cours (2026-11) est retiré.
- **Plancher** : rien avant 1926-01.
- `return_usd` et `return_cad` : rendement pour un investisseur USD ou CAD **non couvert**.
  Conversion : `(1+r_usd)·(USDCAD_t/USDCAD_{t-1}) − 1`, et l'inverse pour les actifs en CAD.
  Sans taux de change (avant 1971-01), la colonne convertie vaut NaN ; `load_returns(..., fx_fill="flat")`
  permet alors d'utiliser le rendement en devise locale (hypothèse d'un change constant), signalé dans `attrs["info"]`.
- `flag` : drapeaux de qualité par mois (voir la liste en bas).

---

## 1. Ken French Data Library (Tuck/Dartmouth)
- **URLs** : `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/`
  `F-F_Research_Data_Factors_CSV.zip`, `12_Industry_Portfolios_CSV.zip`, `F-F_International_Countries.zip`.
  Fichiers US générés à partir de la base CRSP **202609**, donc données jusqu'en 2026-09.
- **Séries produites**
  - `US_MKT` = Mkt-RF + RF (marché US pondéré par la capitalisation, NYSE/AMEX/NASDAQ), depuis 1926-07.
  - `UST_TBILL` = RF (bon du Trésor à 1 mois), depuis 1926-07.
  - `US_IND_*` = 12 portefeuilles industriels **pondérés par la capitalisation** (bloc « Average Value Weighted Returns -- Monthly »).
    Définitions par codes **SIC**, pas GICS : BusEq = ordinateurs, logiciels, électronique (≈ tech) ;
    Telcm = télécoms ; Enrgy = pétrole, gaz, charbon ; Utils = SIC 4900-4949 (inclut les gazoducs).
  - `lookthrough_us_mkt.parquet` = part de chaque industrie dans la capitalisation totale
    (`Number of Firms × Average Firm Size`), variable dans le temps. Elle sert au plafond tech
    « look-through » de `US_MKT` (et, en approximation, de SPY/ESGV). Valeurs calculées par le
    script : BusEq 0,052 en 1926-07, 0,249 en 2000-12, 0,435 en 2026-09 ; Enrgy 0,162 en 1926-07, 0,031 en 2026-09.
  - `CA_EQ` = fichier pays `Canada.Dat`, « Value-Weight Dollar Returns » (→ `return_usd`) et
    « Local Returns » (→ `return_cad`), version « All 4 Data Items Not Reqd », depuis **1977-01**.
    Ce fichier international n'est mis à jour qu'une fois par an et s'arrête en 2025-12. Les mois
    suivants sont complétés par XIU.TO (flag `extended_with_XIU.TO`). Sur 1999-11..2025-12 :
    corrélation CA_EQ~XIU.TO = 0,9835 (`data_version.json` → `qa.proxy_vs_etf`).
- **Hypothèses et limites** : les valeurs −99,99/−999 sont traitées comme manquantes. Avant 1962,
  CRSP couvre essentiellement le NYSE, et la finance y est peu représentée (part Money 0,009 en 1926-07).
  Les industries sont des portefeuilles reconstitués chaque fin juin.
- **Conditions d'utilisation** : données mises à disposition gratuitement par K. French à des fins de
  recherche et d'enseignement ; citer « Kenneth R. French Data Library ». Pas de licence formelle.

## 2. FRED (Federal Reserve Bank of St. Louis)
- **URL** : `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIE>`.
  Ce point d'accès refuse certains User-Agent : le script utilise un UA de type curl.
- **Séries** et statut de copyright indiqué par FRED :
  - Taux du Trésor US : `DGS1, DGS2, DGS3, DGS5, DGS10, DGS20, DGS30` (quotidiens, depuis 1962 ; DGS2 depuis 1976 ;
    DGS20 avec un trou 1987-1993 ; DGS30 avec trous) et `GS1, GS2, GS3, GS5, GS10, GS20, GS30` (moyennes mensuelles,
    depuis 1953-04 pour la plupart). Source Board of Governors H.15, **domaine public** (citation demandée).
  - Moody's `AAA`, `BAA` (mensuels, depuis 1919) et `DAAA`, `DBAA` (quotidiens, depuis 1986) : **copyrighted, citation required**
    (© Moody's). Usage d'analyse avec citation ; les fichiers bruts ne sont pas redistribués. Seuls les rendements
    dérivés sont dans `data/long` (parquets non versionnés). En cas de doute sur la redistribution, reconstruire localement.
  - `CPIAUCNS` (IPC-U US, non désaisonnalisé, depuis 1913) : BLS, domaine public.
  - `DEXCAUS` (CAD par USD, quotidien, depuis 1971-01-04) : Board of Governors H.10, domaine public.
  - OCDE MEI : `CANCPIALLMINMEI` (IPC Canada, 1914-01 → 2025-03), `IRLTLT01CAM156N` (taux long, État canadien, depuis 1955-01),
    `IR3TIB01CAM156N` (taux interbancaire à 3 mois, Canada, depuis 1956-01) : **copyrighted, citation required** (OCDE).
- **Limites** : FRED publie la série **révisée** et la date de **référence**, pas la date de publication.
  Une stratégie qui utiliserait l'IPC du mois t en t aurait un léger look-ahead. Les stratégies du moteur
  n'utilisent pas l'inflation, qui ne sert qu'aux métriques réelles. **Mois manquant** : le BLS n'a pas publié
  l'IPC d'octobre 2025. L'indice est interpolé log-linéairement et 2025-10 et 2025-11 portent le flag
  `cpi_interpolated` (`inflation_monthly.parquet`, colonne `flag_us`).

## 3. Robert Shiller : `ie_data.xls`
- **URL** : `https://img1.wsimg.com/blobby/go/e5e77e0b-59d1-44d9-ab25-4763ac982e53/downloads/ie_data.xls`
  (lien « U.S. Stock Markets 1871-Present » de shillerdata.com ; même fichier que l'ancien
  `econ.yale.edu/~shiller/data/ie_data.xls`).
- **Usage** : colonne « Rate GS10 », c'est-à-dire le taux long de l'État US (GS10 après 1953, taux longs historiques avant).
  Elle n'est utilisée qu'**avant 1953-04** pour les obligations synthétiques. Le fichier s'arrête en 2024-09, sans conséquence ici.
- **Conditions** : données publiques mises à disposition par R. Shiller ; citer « Shiller, Irrational Exuberance data ».

## 4. Or : datahub `core/gold-prices`
- **URL** : `https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv`
- **Contenu** (README du dépôt) : 1833-1959 = tableau historique de Timothy Green, uniquement
  **annuel** et répété chaque mois ; 1960 → aujourd'hui = Banque mondiale « Pink Sheet », **moyenne mensuelle**.
- **Flags** : `annual_avg_repeated_monthly` (< 1960 : rendement nul en cours d'année, saut en janvier),
  `fixed_official_price` (≤ 1971-08), `non_investable_us_private_ban` (1933-04 → 1974-12 : détention privée d'or
  interdite aux É.-U.). **Avant 1975, l'or est non investissable ou peu informatif** et il vaut mieux l'exclure des fenêtres.
- **Limites** : les moyennes mensuelles lissent la série (vol proxy 0,1359 contre GLD 0,1734 sur 2004-12..2026-10, corrélation 0,6323).
  Pas de frais de garde ni de rendement.
- **Conditions** : dépôt sous ODC-PDDL ; données Banque mondiale librement réutilisables.

## 5. Banque du Canada : API Valet
- **URL** : `https://www.bankofcanada.ca/valet/observations/V41690973/csv?start_date=1990-01-01`
  (IPC d'ensemble Canada, Statistique Canada, non désaisonnalisé, depuis 1995-01).
- **Usage** : prolonge l'IPC canadien après la fin de la série OCDE (2025-03). Les variations mensuelles
  StatCan sont utilisées à partir de 1995-02, celles de l'OCDE avant. Contrôle sur 362 mois communs :
  corrélation 0,99999999837, écart absolu moyen 1,07e-07.
- **Conditions** : conditions d'utilisation de la Banque du Canada (réutilisation avec attribution) ;
  données StatCan sous la Licence du gouvernement ouvert de Statistique Canada.
- Les rendements canadiens à 10 ans et le cash CAD ne viennent **pas** de Valet, car l'historique Valet ne
  commence qu'en 2001-2005 et ne permet pas de remonter avant. Ils viennent de l'OCDE via FRED (section 2).

## 6. Yahoo Finance via `yfinance` (31 tickers de l'univers)
- **Appel** : `yfinance.download(t, period="max", interval="1d", auto_adjust=False)`, colonnes `Close` et `Adj Close`.
- **Usage** : rendements mensuels `adj_close` **avant 2021-12**. À partir de **2021-12**, ce sont ceux du
  **starter dataset officiel** (`prices_daily.csv`), par cohérence avec le projet. Le premier rendement du starter
  est 2021-12, car sa base est la fin novembre 2021.
- **Concordance** sur les 59 mois communs (`data/long/qa_overlap.csv`) : corrélation 1,0 et écart absolu
  moyen 0,0 pour les 31 tickers. Les deux viennent de Yahoo (écart maximal ≤ 1e-6).
- **Correction CNQ.TO 2022-08-22** : Yahoo a enregistré le dividende spécial à la fois comme « split »
  1,021 et comme dividende de 0,75. `adj_close` le compte donc deux fois ce jour-là : rendement journalier
  0,027794 contre un rendement total réel (close + dividende)/(close_{t−1}·1,021) − 1 = 0,006078.
  Le rendement d'août 2022 est corrigé (flag `corrected_double_counted_special_dividend`). Calcul dans
  `fix_cnq_special_dividend()` ; valeurs dans `data_version.json` → `qa.cnq_fix_2022_08_22`.
- **Limites** : `adj_close` est recalculé à chaque téléchargement. Les niveaux changent ; les rendements bougent à peine (écart max mesuré entre deux téléchargements du même jour : 2,7e-06), mais assez pour changer `data_sha256`, qui identifie un build précis.
  Les données Yahoo ne sont pas certifiées par les bourses. L'historique des `.TO` ne commence qu'en 1995 chez Yahoo.
  BTC-USD commence en 2014-09 et ETH-USD en 2017-11 (dates Yahoo ; le BTC s'échangeait avant). Premier mois après
  cotation : flag `first_month_after_listing`. **Biais du survivant** : l'univers a été choisi en 2026.
- **Conditions** : conditions d'utilisation de Yahoo (usage personnel/non commercial,
  https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html), comme pour le starter.

## 7. Starter dataset officiel (organisateurs)
- `source/Datathon2026/Datathon2026/alphaforge_starter/` : `prices_daily.csv` (adj_close), `fx_usdcad_daily.csv`
  (Banque du Canada), `corporate_actions.csv`, `assets_universe.csv`. Il est lu en place et jamais copié dans le dépôt.
- **FX** : USDCAD de fin de mois = FRED DEXCAUS jusqu'en 2021-10, puis le FX du starter à partir de 2021-11-30.
  Le starter n'a pas de ligne les jours fériés canadiens : on prend le **dernier jour disponible du mois**,
  ce qui revient à un forward-fill dans le mois. Écart max FRED/starter sur 60 fins de mois communes : 0,0099 CAD.
- **Conditions** : « Free to use within the datathon » (`sources_metadata.csv`).

---

## Reconstructions synthétiques

### Obligations à maturité constante (`finance/backtest/bonds.py`, testé dans `tests/finance/backtest/test_bonds.py`)
Fin du mois t−1 : achat d'une obligation **au pair** de maturité N, avec un coupon y_{t−1} payé semestriellement.
Fin du mois t : il reste N − 1/12 an, réévaluation au taux y_t, revente, rachat d'une nouvelle obligation au pair.

    r_t = P(c = y_{t-1}, y = y_t, M = N − 1/12) − 1 + y_{t-1}/12
    P(c, y, M) = (c/y)·(1 − (1+y/2)^(−2M)) + (1+y/2)^(−2M)     (P = 1 + c·M si y = 0)

Les périodes fractionnaires suivent la formule d'annuité continue (pas de jours courus ni de convention de calendrier).
Pas de frais, pas de fiscalité. Le test vérifie un prix calculé à la main (coupon 6 %, taux 7 %, 2 ans : 0,981635)
et un rendement mensuel construit sur ce cas.

Règles de priorité et de repli, de la meilleure à la moins bonne. Les flags décrivent le mois :
| Série | 1. | 2. | 3. | 4. |
|---|---|---|---|---|
| `UST_2Y` | DGS2 fin de mois (1976+) | moyenne (DGS1, DGS3) fin de mois (1962+) `fallback_avg_DGS1_DGS3` | moyenne (GS1, GS3) mensuelle (1953-04+) | < 1953-04 : interpolation linéaire en maturité entre le T-bill (RF annualisé) et le taux long Shiller `fallback_interp_bill_long` |
| `UST_5Y` | DGS5 fin de mois | GS5 moyenne mensuelle | < 1953-04 : interpolation T-bill/taux long | |
| `UST_10Y` | DGS10 fin de mois | GS10 moyenne mensuelle | < 1953-04 : taux long Shiller `shiller_long_rate` | |
| `UST_20Y` | DGS20 fin de mois | DGS30 `fallback_DGS30` (trou de DGS20 1987-1993) | GS20 puis GS30 (moyennes) | < 1953-04 : taux long Shiller |
| `CORP_AAA/BAA` (N = 20) | DAAA/DBAA fin de mois (1986+) | AAA/BAA moyenne mensuelle (1919+) | | |
| `CA_GOV_10Y` (N = 10) | OCDE IRLTLT01CAM156N (moyenne mensuelle, 1955+) | | | |

- `monthly_avg_yield` : rendement calculé sur des **moyennes mensuelles** de taux. La série est lissée
  (volatilité sous-estimée, léger retard), ce qui concerne tout ce qui précède 1962 et une partie des séries.
- `splice` : premier mois d'une nouvelle source de taux (le rendement mélange deux sources).
- `no_default_losses` (AAA/BAA) : reconstruire à partir des taux ignore les défauts, les dégradations et
  les remboursements anticipés. Le rendement réalisé est donc **surestimé**, surtout pour Baa.
- Concordance avec de vrais FNB (`qa.proxy_vs_etf`, calculé par le script) :

| proxy ~ FNB | mois | corr | rend. moyen annualisé proxy / FNB | vol proxy / FNB |
|---|---|---|---|---|
| US_MKT ~ SPY | 404 | 0,9874 | 0,1158 / 0,1140 | 0,1522 / 0,1473 |
| UST_20Y ~ TLT | 291 | 0,9870 | 0,0412 / 0,0431 | 0,1194 / 0,1351 |
| UST_10Y ~ AGG | 277 | 0,8775 | 0,0289 / 0,0303 | 0,0733 / 0,0447 |
| UST_5Y ~ AGG | 277 | 0,8322 | 0,0222 / 0,0303 | 0,0409 / 0,0447 |
| CORP_AAA ~ AGG | 277 | 0,8850 | 0,0450 / 0,0303 | 0,1005 / 0,0447 |
| GOLD ~ GLD | 263 | 0,6323 | 0,1115 / 0,1095 | 0,1359 / 0,1734 |
| CA_EQ ~ XIU.TO | 314 | 0,9835 | 0,0946 / 0,0905 | 0,1357 / 0,1389 |
| CA_GOV_10Y ~ XBB.TO | 310 | 0,5843 | 0,0367 / 0,0357 | 0,0516 / 0,0475 |
| CA_TBILL ~ ZST.TO | 187 | 0,4866 | 0,0156 / 0,0223 | 0,0040 / 0,0077 |
| US_IND_BUSEQ ~ QQQ | 330 | 0,9819 | 0,1311 / 0,1303 | 0,2362 / 0,2326 |

Lecture : la correspondance est bonne pour les actions et pour TLT. Elle est faible pour AGG (indice agrégé,
avec MBS et crédit), XBB.TO (OCDE en moyenne mensuelle, contre un indice univers incluant provinces et sociétés),
ZST.TO (taux interbancaire, contre un FNB ultra-court) et GLD (moyenne mensuelle contre fin de mois).

### Cash canadien (`CA_TBILL`)
`r_t = taux3m_{t−1} / 100 / 12`, où le taux est l'interbancaire à 3 mois de l'OCDE. C'est une approximation
d'un T-bill canadien, pas un indice investissable (flag `proxy_interbank_rate`).

### USDCAD avant 1971
FRED DEXCAUS commence le 1971-01-04 et il n'y a **aucune** série gratuite fiable avant dans ce build.
Pour mémoire, le Canada avait un taux flottant de 1950 à 1962, une parité fixe de 1962 à 1970, puis à nouveau
un taux flottant à partir de 1970-06. Par défaut, `return_cad` des actifs USD (et `return_usd` des actifs CAD)
commence donc en **1971-02**. Avec `fx_fill="flat"`, le moteur substitue le rendement local avant cette date,
ce qui revient à supposer un change constant (couverture parfaite). C'est une hypothèse, pas une donnée.

---

## Liste des flags
| flag | signification |
|---|---|
| `first_month_after_listing` | premier rendement mensuel disponible chez Yahoo (base = fin du mois de cotation) |
| `monthly_avg_yield` | obligation synthétique construite sur des moyennes mensuelles de taux (lissage) |
| `fallback_*`, `shiller_long_rate` | maturité de repli (voir le tableau ci-dessus) |
| `splice` | changement de source de taux ce mois-là |
| `no_default_losses` | obligations de sociétés sans pertes de défaut |
| `annual_avg_repeated_monthly`, `fixed_official_price`, `non_investable_us_private_ban` | or avant 1975 |
| `extended_with_XIU.TO` | CA_EQ après la fin du fichier Ken French |
| `proxy_interbank_rate` | cash canadien approximé par l'interbancaire |
| `corrected_double_counted_special_dividend` | correction CNQ.TO 2022-08 |
| `cpi_interpolated` (inflation) | IPC US interpolé (mois non publié) |

## Biais et limites majeurs (à rappeler dans tout livrable)
- **Biais du survivant** : les 31 tickers ont été choisis en 2026 ; leurs historiques longs (AAPL, NVDA…) sont ceux de gagnants.
- **Proxys ≠ produits investissables** : pas de frais de gestion, de spreads ni d'impôts ; indices reconstitués a posteriori.
- **Révisions et dates de référence** (FRED/OCDE) : séries révisées, datées du mois de référence.
- **Lissage** des séries construites sur des moyennes mensuelles (obligations avant 1962, or, Canada 10 ans).
- **Ruptures de régime** : étalon-or, contrôle des taux (1942-1951), change fixe : le passé lointain est peu comparable.
