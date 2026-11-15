# API gratuites de données macroéconomiques et statistiques officielles des États-Unis (état au 14 novembre 2026)

> Notes de recherche pour AlphaForge AI (agent A5 de collecte, base de connaissances OKF).
> Convention : « [Test direct 2026-11-14] » désigne un appel HTTP réel effectué le 14 novembre 2026 depuis l'environnement de recherche. L'URL citée est l'endpoint interrogé. Tout ce qui n'a pas de source primaire est signalé comme tel.

## Q1. Quelles API existent ? (inventaire)

### Takeaway
Au moins 22 sources officielles américaines gratuites sont utilisables par programme. Il y a de vraies API REST (FRED/ALFRED, BLS, BEA, Census, Fiscal Data, NY Fed, EIA, NASS, ERS, CFTC via Socrata, catalogue CKAN de data.gov). Il y a aussi des flux de fichiers stables (XML/CSV du Trésor, DDP de la Fed Board, CSV DOL ETA-539, CSV maître FHFA) et des fichiers Excel de recherche (Philly Fed RTDSM et SPF, GDPNow, Cleveland Fed), dont la plupart sont aussi repris dans FRED. Deux changements structurants en 2026 : le DDP de la Fed Board ferme (FRED devient le canal officiel), et une clé est obligatoire pour l'API Census depuis le 12 mai 2026.

### Cited Findings
**Agrégateur central (Fed de St. Louis)**
- FRED API v1 : familles d'endpoints Categories, Releases (`releases`, `releases/dates`, `release`, `release/dates`, `release/series`, `release/sources`, `release/tags`, `release/related_tags`, `release/tables`), Series (`series`, `series/observations`, `series/release`, `series/search`, `series/updates`, `series/vintagedates`, etc.), Sources, Tags, plus la Maps API (GeoFRED) — [FRED API docs](https://fred.stlouisfed.org/docs/api/fred/)
- FRED API v2 : un seul endpoint documenté, `fred/v2/release/observations` (toutes les séries d'une release en masse) — [FRED API v2](https://fred.stlouisfed.org/docs/api/fred/v2/index.html)
- ALFRED (archives des vintages) passe par la même API, avec les paramètres temps réel `realtime_start`/`realtime_end` — [Real-Time Periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)
- FRED-MD (mensuel) et FRED-QD (trimestriel) : bases macro « big data » de McCracken, sous forme de fichiers CSV par vintage — [FRED-MD/QD](https://www.stlouisfed.org/research/economists/mccracken/fred-databases)
- Connecteur MCP officiel FRED : `https://mcp.stlouisfed.org` — [FRED MCP Connector](https://fred.stlouisfed.org/help/data/connecting-fred-to-ai-services/FRED-MCP-Connector)

**Agences statistiques fédérales**
- BLS Public Data API v1 (sans inscription) et v2 (avec inscription) — [BLS Developers](https://www.bls.gov/developers/)
- BEA API, jeux de données : NIPA, NIUnderlyingDetail, FixedAssets, Regional, ITA, IIP, IntlServTrade, IntlServSTA (« New »), GDPByIndustry, UnderlyingGDPbyIndustry (« New »), InputOutput, MNE — [BEA API signup](https://apps.bea.gov/api/signup/)
- Census Data API, Economic Indicators Time Series (`timeseries/eits/...`) : `advm3`, `bfs`, `ftd` (commerce international), `hv`, `m3`, `marts` (ventes au détail avancées), `mhs`, `mhs2`, `mrts`, `mtis`, `mwts`, `qfr`, `qpr`, `qss`, `qtax`, `resconst` (mises en chantier), `ressales` (ventes de logements neufs), `vip` (dépenses de construction) — [Census EITS](https://www.census.gov/data/developers/data-sets/economic-indicators.html)
- DOL ETA, demandes d'assurance-chômage : fichier CSV ETA-539 à `https://oui.doleta.gov/unemploy/csv/ar539.csv` — [Montana LMI fact sheet](https://nvlmi.mt.gov/_docs/Other-Publications/Current-Fact-Sheet/National-Weekly-Claims-Report) ; [data.gov ETA-539](https://catalog.data.gov/dataset/unemployment-insurance-weekly-claims-extended-benefits-trigger-data-eta-539) ; fichier accessible (HTTP 200, 13,4 Mo, Last-Modified 14 nov. 2026) [Test direct 2026-11-14](https://oui.doleta.gov/unemploy/csv/ar539.csv)
- USDA NASS Quick Stats API (`api_GET`, `get_param_values`, `get_counts`) — [NASS Quick Stats API](https://quickstats.nass.usda.gov/api)
- USDA ERS Data APIs (dont ARMS, en REST et GraphQL) — [ERS Developer](https://www.ers.usda.gov/developer) ; [ARMS Data API](https://ers.usda.gov/developer/data-apis/arms-data-api)
- EIA API v2 (énergie) — [EIA API documentation](https://www.eia.gov/opendata/documentation.php)

**Trésor**
- Fiscal Data API (Bureau of the Fiscal Service) : 184 endpoints, dont `avg_interest_rates`, `debt_to_penny`, `rates_of_exchange`, MTS et DTS — [Fiscal Data API docs](https://fiscaldata.treasury.gov/api-documentation/)
- Flux XML des taux quotidiens du Trésor : `daily_treasury_yield_curve`, `daily_treasury_bill_rates`, `daily_treasury_long_term_rate`, `daily_treasury_real_yield_curve`, `daily_treasury_real_long_term` — [Treasury XML feed](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed)

**Système fédéral de réserve**
- Fed Board Data Download Program (DDP) : G.19, G.17, H.3, H.8, charge-offs, SLOOS, E.2, papier commercial, G.20, SCOOS, G.5/H.10, Z.1, DSR, H.15, Policy Rates, H.4.1, H.6 — [DDP](https://www.federalreserve.gov/datadownload/)
- NY Fed Markets Data APIs : taux de référence (SOFR, EFFR, OBFR, TGCR, BGCR, moyennes et indice SOFR), plus SOMA, repo/reverse repo, primary dealers, securities lending, FX swaps, AMBS et opérations sur Treasuries — [NY Fed OpenAPI spec](https://markets.newyorkfed.org/static/docs/markets-api.yml)
- Philadelphia Fed : Real-Time Data Set for Macroeconomists (RTDSM) — [RTDSM](https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-for-macroeconomists) ; Survey of Professional Forecasters (SPF) — [SPF Data Files](https://www.philadelphiafed.org/surveys-and-data/data-files)
- Atlanta Fed GDPNow (fichier Excel ; série FRED `GDPNOW`) — [GDPNow](https://www.atlantafed.org/research-and-data/data/gdpnow) ; [FRED GDPNOW](https://fred.stlouisfed.org/graph?graph_id=1439392)
- Cleveland Fed : nowcasts d'inflation quotidiens et anticipations d'inflation mensuelles (FRED `EXPINF10YR`, etc.) — [Inflation Nowcasting](https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting) ; [FRED EXPINF10YR](https://fred.stlouisfed.org/series/EXPINF10YR)
- Calendrier FOMC (page HTML, 2021–2027) — [FOMC calendars](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)

**Autres**
- FHFA House Price Index : fichier maître en CSV/JSON/XML/SQL — [FHFA HPI datasets](https://www.FHFA.gov/DataTools/Downloads/Pages/House-Price-Index-Datasets.aspx)
- CFTC Commitments of Traders (Socrata) : Legacy Futures Only `6dca-aqww`, Legacy Combined `jun7-fc8e`, Disaggregated Futures Only `72hh-3qpy`, Disaggregated Combined `kh3c-gbw2`, TFF Futures Only `gpe5-46if`, TFF Combined `yw9f-hn96`, Supplemental CIT `4zgm-a668` — [CFTC API Help](https://publicreporting.cftc.gov/stories/s/r4w3-av2u)
- data.gov : catalogue fédéral, API CKAN à `catalog.data.gov/api/3/` — [data.gov APIs](https://data.gov/developers/apis/)

### Inferences
- Pour A5, la stratégie la plus simple est probablement « FRED/ALFRED d'abord ». FRED couvre déjà H.15, BLS, BEA, Census, GDPNow et Cleveland Fed, et il est la seule source qui expose les vintages par API de façon homogène. On garde les API d'agence pour trois cas : les séries absentes de FRED, la provenance « primaire » exigée par le brief, et le contrôle croisé.
- Le DDP de la Fed Board ferme (voir Q5). Il vaut mieux ne pas construire de connecteur DDP et passer par FRED pour H.15, H.10, G.17 et Z.1.

### Gaps
- Je n'ai pas retrouvé de liste officielle exhaustive des 184 endpoints Fiscal Data : la page n'en affiche que 10.
- Les routes EIA v2 autres que `electricity` (petroleum, natural-gas, total-energy, steo) n'apparaissent pas dans la page de documentation que j'ai lue. Je ne les ai pas vérifiées une par une.
- Je n'ai pas trouvé d'API officielle FHFA documentée sur fhfa.gov : seulement des fichiers téléchargeables. Une « FHFA HPI API » est mentionnée par des annuaires tiers ([apis.io](https://apis.io/apis/fhfa/fhfa-house-price-index-api/)), mais sans confirmation officielle.

## Q2. Fiche par API : URL, authentification, limites, formats, couverture, licence

### Takeaway
Les données fédérales américaines sont en général du domaine public, avec une citation demandée. Le vrai risque juridique est ailleurs. D'abord, les séries tierces hébergées par FRED (ICE, S&P, Moody's, etc.), marquées « Copyrighted ». Ensuite, les clauses d'API qui imposent une mention de non-endorsement (FRED, Census, NASS), interdisent de répliquer FRED, ou imposent les conditions du NY Fed sur les taux de référence. Les limites documentées les plus contraignantes : FRED 120 requêtes/min, BLS v2 500 requêtes/jour, BEA environ 100 requêtes/min (source secondaire), NASS 50 000 lignes par requête, EIA 5 000 lignes par réponse JSON.

### Cited Findings

#### FRED (API v1)
- Base : `https://api.stlouisfed.org/fred/...`. Sans clé, l'API renvoie `{"error_code":400,"error_message":"Bad Request. Variable api_key is not set..."}` — [Test direct 2026-11-14](https://api.stlouisfed.org/fred/series/observations?series_id=GDP&file_type=json)
- Clé : chaîne de 32 caractères alphanumériques en minuscules. Il faut se connecter à un compte fredaccount.stlouisfed.org pour la demander. « Developers should request a distinct API key for each application » et « All users of an application shall use their own API key ». Le délai d'obtention n'est pas indiqué — [FRED API Keys](https://fred.stlouisfed.org/docs/api/api_key.html)
- Limite de débit : « Up to 120 requests per minute are allowed before being served a 429 error code ». « Not complying with the throttling can result in a temporary block » — [FRED Errors](https://fred.stlouisfed.org/docs/api/fred/errors.html)
- Des sources tierces évoquent une sous-limite de 40/min sur les observations et un plafond de 6 000/jour. Ce n'est pas confirmé par la documentation officielle — [FRED MCP server docs (tiers)](https://glama.ai/mcp/servers/@stefanoamorelli/fred-mcp-server/blob/41a5270f604aef6d81d0c33a9f2054be0d43a4dd/docs/api-reference/overview.mdx)
- Formats (`series/observations`) : `xml` (par défaut), `json`, `xlsx`, `csv` (zip contenant CSV + README). `limit` vaut 100 000 par défaut et au maximum. `observation_start` vaut 1776-07-04 par défaut. L'agrégation de fréquence (`frequency`, `aggregation_method` = avg/sum/eop) ne marche qu'en xml/json. Les transformations `units` possibles : lin, chg, ch1, pch, pc1, pca, cch, cca, log — [series/observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
- Conditions (API Terms of Use) :
  - toute application doit afficher « This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis » ;
  - interdiction de « replicates or attempts to replace the essential user experience » de FRED/ALFRED ;
  - interdiction d'utiliser « FRED® »/« ALFRED® » dans un hostname ;
  - interdiction de retirer les mentions de droits ;
  - pas de clause explicite sur le cache ;
  - en cas de résiliation, obligation de détruire toutes les copies du « FRED® API software » ;
  - pas de date de mise à jour sur la page.
  [FRED API Terms of Use](https://fred.stlouisfed.org/docs/api/terms_of_use.html)
- Séries tierces : « Series owned by third parties may be subject to copyright ». Tout usage au-delà de l'usage personnel exige de « contact the data owner to obtain permission ». La Fed de St. Louis ne peut pas accorder cette permission. Ces séries se reconnaissent au mot « Copyright » dans leurs notes — [FRED API Terms of Use](https://fred.stlouisfed.org/docs/api/terms_of_use.html)
- Étiquettes de droits FRED : « Public Domain: Citation Requested », « Copyrighted: Citation Required », « Copyrighted: Pre-approval Required ». Pour les données sous copyright, il faut obtenir la permission du fournisseur d'origine (indiqué dans les « Notes ») pour tout partage au-delà d'un usage « personal, non-commercial » — [FRED FAQ cite](https://fred.stlouisfed.org/help/fred-faq/frequently_asked_questions/cite)
- Exemple ICE BofA (`BAMLC0A4CBBBEY`) :
  - « Starting in April 2026, this series will only include 3 years of observations » ;
  - « Reproduction of this data in any form is prohibited except with the prior written permission of ICE Data Indices » ;
  - redistribution à des tiers interdite sans accord écrit.
  [FRED BAMLC0A4CBBBEY](https://fred.stlouisfed.org/series/BAMLC0A4CBBBEY)
- Précédent : les données ICE Benchmark Administration (Libor ICE, swap rates) ont été retirées de FRED le 31 janvier 2022 — [FRED blog 2022](https://news.research.stlouisfed.org/2022/01/ice-benchmark-administration-ltd-iba-data-to-be-removed-from-fred/)
- Une série d'une banque de réserve peut porter des signaux contradictoires. `EXPINF10YR` (Cleveland Fed) porte l'étiquette « Public Domain: Citation Requested » alors que la page indique « Data in this graph are copyrighted ». Citation suggérée : « Federal Reserve Bank of Cleveland, 10-Year Expected Inflation [EXPINF10YR], retrieved from FRED... » — [FRED EXPINF10YR](https://fred.stlouisfed.org/series/EXPINF10YR)

#### FRED API v2
- `GET https://api.stlouisfed.org/fred/v2/release/observations?release_id=52&format=json`.
- Clé « set in a HTTP header ». La page ne nomme pas le header.
- Formats json (par défaut) et xml ; `limit` jusqu'à 500 000.
- Pagination par `next_cursor`/`has_more`.
- Champ `last_updated` par série ; une même réponse peut mélanger des séries mises à jour et non mises à jour pendant une mise à jour de la release.
- Aucun paramètre vintage/temps réel documenté.
[FRED v2 release/observations](https://fred.stlouisfed.org/docs/api/fred/v2/release_observations.html)

#### FRED-MD / FRED-QD
- Fichier `current.csv` plus des fichiers mensuels datés. Archives : FRED-MD 1999-08→2014-12 et 2015-01→2024-12 ; FRED-QD 2018-05→2024-12. Le fichier courant est remplacé au début de chaque mois — [FRED-MD/QD](https://www.stlouisfed.org/research/economists/mccracken/fred-databases) (vu via résultats de recherche)
- Journal des changements par vintage (ex. claims en données désaisonnalisées à partir du vintage 2015-08) — [fredmdchanges.pdf](https://files.stlouisfed.org/files/htdocs/fred-databases/fredmdchanges.pdf)
- Une documentation tierce cite des fichiers `2026-04-md.csv` / `2026-04-qd.csv` — [macroforecast docs](https://macroforecast.readthedocs.io/en/latest/datasets/fred_md.html)

#### BLS Public Data API
- Base v2 : `https://api.bls.gov/publicAPI/v2/timeseries/data/`.
  - GET pour une série ; POST JSON pour plusieurs séries.
  - Champs : `seriesid[]`, `startyear`, `endyear`, `catalog`, `calculations`, `annualaverage`, `aspects`, `registrationkey`.
  - Option `?latest=true`.
  - Endpoints `.../timeseries/popular` et `.../surveys`.
  - Sortie JSON (ou `.xlsx`). Les notes de bas de page portent un `code` et un `text`, par exemple `P` = « Preliminary ».
  - Par défaut, l'API renvoie les 3 dernières années.
  [BLS API Signature v2](https://www.bls.gov/developers/api_signature_v2.htm)
- Limites :

  | | v2 (inscrit) | v1 |
  |---|---|---|
  | Requêtes/jour | 500 | 25 |
  | Séries/requête | 50 | 25 |
  | Années/requête | 20 | 10 |
  | Débit | 50 requêtes/10 s | 50 requêtes/10 s |

  La clé doit être renouvelée « at least once a year ». Inscription : email + organisation + CAPTCHA ; la clé arrive par email (labstat@bls.gov), délai non indiqué. Une FAQ interne mentionne encore « must not exceed a 10 year period », ce qui contredit la limite de 20 ans.
  [BLS API FAQ](https://www.bls.gov/developers/api_faqs.htm)
- Conditions :
  - citer la date d'accès ;
  - mentionner « BLS.gov cannot vouch for the data or analyses derived from these data after the data have been retrieved from BLS.gov » ;
  - interdiction d'utiliser le logo BLS et de modifier le contenu en le citant comme BLS ;
  - blocage possible si les limites sont contournées ;
  - dernière modification le 30 août 2023.
  [BLS Terms of Service](https://www.bls.gov/developers/termsOfService.htm)
- La page Developers est datée « Last Modified February 9, 2016 » et n'affiche aucun avis récent — [BLS Developers](https://www.bls.gov/developers/)
- Comportement observé en v1 GET : la requête `CUUR0000SA0?startyear=2025&endyear=2025` a renvoyé des données 2026, avec `latest:true` sur octobre 2026 = 337.511. Les paramètres en query string semblent donc ignorés en GET v1 — [Test direct 2026-11-14](https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0?startyear=2025&endyear=2025)

#### BEA API
- Inscription : nom ou organisation, email valide et acceptation des conditions. Contact : developers@bea.gov — [BEA API signup](https://apps.bea.gov/api/signup/)
- Le UserID est un identifiant unique de 36 caractères. L'API fournit des méthodes de données et de métadonnées — [BEA API docs](https://apps.bea.gov/API/docs/index.htm)
- Limites : 100 requêtes, 100 Mo et 30 erreurs par minute. Source secondaire (guide de bibliothèque universitaire). Le guide officiel est un PDF que je n'ai pas pu extraire — [UA Libraries BEA cookbook](https://ua-libraries-research-data-services.github.io/UALIB_ScholarlyAPI_Cookbook/overview/bea.html)
- Conditions générales : « information posted on the BEA web site is in the public domain and may be used or reproduced without specific permission ». Citation suggérée : « Source: U.S. Bureau of Economic Analysis ». Le logo est réservé — [BEA FAQ](https://bea.gov/help/faq/145) (vu via résultats de recherche). Conditions propres à l'API : PDF `bea_api_tos.pdf` lié depuis [BEA API signup](https://apps.bea.gov/api/signup/), non lu.

#### Census Data API (EITS)
- Base : `https://api.census.gov/data/timeseries/eits/{programme}`.
  - Variables : `cell_value`, `data_type_code`, `time_slot_id`, `error_data`, `category_code`, `seasonally_adj`.
  - Filtre `time` : `2004`, `2004-05`, `from+2010`, `from+2004-05+to+2012-12`.
  - Couverture : « various years - present ».
  [Census EITS](https://www.census.gov/data/developers/data-sets/economic-indicators.html)
- Clé obligatoire : « All data queries to the Census Data API now require an API key » — [Census EITS](https://www.census.gov/data/developers/data-sets/economic-indicators.html). Entrée en vigueur le 12 mai 2026 — [repost de l'email Census](https://buttondown.com/crgibbons/archive/census-data-api-to-require-api-key/). L'obligation a été levée pour les requêtes de métadonnées en juin 2026, mais reste en vigueur pour les données — [Census newsletter juin 2026](https://content.govdelivery.com/accounts/USCENSUS/bulletins/41aaf23)
- Sans clé, l'API répond HTTP 302 vers `https://api.census.gov/data/missing_key.html` — [Test direct 2026-11-14](https://api.census.gov/data/timeseries/eits/marts?get=cell_value&time=2026-08)
- Guide utilisateur daté du 12 mai 2026, révisé le 14 mai 2026 — [Census API User Guide](https://www.census.gov/data/developers/guidance/api-user-guide.html)
- Conditions :
  - mention obligatoire « This product uses the Census Bureau Data API but is not endorsed or certified by the Census Bureau » ;
  - interdiction de ré-identifier des personnes ou des entreprises ;
  - limites non chiffrées, blocage possible ;
  - page révisée le 14 avril 2026.
  [Census Terms of Service](https://www.census.gov/data/developers/about/terms-of-service.html)

#### U.S. Treasury Fiscal Data API
- Base : `https://api.fiscaldata.treasury.gov/services/api/fiscal_service`.
  - Aucune clé : « does not require a user account or registration for a token ».
  - Formats json (par défaut), csv, xml.
  - Pagination `page[number]`, `page[size]` (100 par défaut).
  - Filtres `field:op:value` (lt, lte, gt, gte, eq, in).
  - Toutes les valeurs sont renvoyées en chaînes (`"null"` compris). Endpoints en v1 et v2.
  - Limites de débit non documentées.
  [Fiscal Data API docs](https://fiscaldata.treasury.gov/api-documentation/)
- Licence : « The data is offered free, without restriction, and available to copy, adapt, redistribute ». Usage commercial autorisé — [Fiscal Data API docs](https://fiscaldata.treasury.gov/api-documentation/)
- `debt_to_penny` : dernier `record_date` = 2026-11-12, 8 433 enregistrements. La réponse contient `meta.labels`, `dataTypes` et `dataFormats`, mais aucun champ de date de publication — [Test direct 2026-11-14](https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny?sort=-record_date&page[size]=1). Attention : avec curl, il faut l'option `-g` à cause des crochets.

#### Taux quotidiens du Trésor (XML / CSV)
- XML : `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data={type}&field_tdr_date_value={yyyy}`. Variantes : `=all&page=n` (pages de 300 lignes, numérotées à partir de 0) et `field_tdr_date_value_month={yyyymm}`. Historique : courbe par (par yield) depuis 1990, bills depuis 2002, long terme depuis 2000, réels depuis 2003 — [Treasury XML feed](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed) ; avis développeur [XML changes](https://home.treasury.gov/developer-notice-xml-changes)
- CSV : `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv` fonctionne. Colonnes : `Date, 1 Mo, 1.5 Month, 2 Mo, 3 Mo, 4 Mo, 6 Mo, 1 Yr, 2 Yr, 3 Yr, 5 Yr, 7 Yr, 10 Yr, 20 Yr, 30 Yr`. Dernière ligne : 11/13/2026 — [Test direct 2026-11-14](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv)
- Archives CSV multi-années (ex. `par-yield-curve-rates-1990-2023.csv`) — [Treasury CSV archive](https://home.treasury.gov/interest-rates-data-csv-archive)

#### Fed Board : Data Download Program (DDP)
- Paquets H.15 : Treasury Constant Maturities (CSV, toutes observations), moyennes hebdomadaires et mensuelles (CSV), et « All H.15 data » en SDMX/ZIP (67,6 Mo) — [DDP H.15](https://www.federalreserve.gov/datadownload/Choose.aspx?rel=H15)
- Pas d'API ni de clé ; téléchargement par paquets. Fermeture annoncée (voir Q5) — [DDP](https://www.federalreserve.gov/datadownload/)
- Licence : « Unless otherwise indicated, information on Board's website is in the public domain » et « may be copied and distributed without permission ». « Please cite to the Board as the source » — [Fed Board disclaimer](https://www.federalreserve.gov/disclaimer.htm)
- « All releases available through the DDP are now accessible within the FRED database » — [FRED collection Federal Reserve Board Data](https://fred.stlouisfed.org/collection/federal-reserve-board-data) (vu via résultats de recherche)

#### NY Fed Markets Data APIs
- Base : `https://markets.newyorkfed.org`, avec une version bêta sous `/beta`. Aucun schéma d'authentification dans la spécification OpenAPI 3.0.
  - Taux : `/api/rates/{secured|unsecured|all}/.../latest|last/{n}|search.{json|xml|csv|xlsx}`. `ratetype` secured = tgcr, bgcr, sofr, sofrai ; unsecured = effr, obfr.
  - Paramètres `startDate`, `endDate` (yyyy-MM-dd ; date du jour par défaut) et `type` = rate ou volume.
  - Erreurs : HTTP 400 pour une requête invalide.
  - Une seule version de production. « Last Updated: June 12, 2026 ».
  - Limites de débit non documentées.
  [NY Fed OpenAPI spec](https://markets.newyorkfed.org/static/docs/markets-api.yml)
- Réponse SOFR : champs `effectiveDate`, `percentRate`, percentiles, `volumeInBillions`, `revisionIndicator`. Dernière valeur : 2026-11-12 = 3.90 %. L'historique remonte au moins à début avril 2018 — [Test direct 2026-11-14](https://markets.newyorkfed.org/api/rates/secured/sofr/last/2.json) ; [Test direct (2018)](https://markets.newyorkfed.org/api/rates/secured/sofr/search.json?startDate=2018-01-01&endDate=2018-04-05)
- Conditions (dernière mise à jour 9 juin 2023) :
  - usage et distribution « personal or business purposes » ;
  - avis obligatoire « subject to the Terms of Use posted at newyorkfed.org » ;
  - « [User] is not affiliated with the New York Fed » si le produit utilise le nom d'un taux ;
  - interdiction d'imposer des conditions plus restrictives ;
  - « None of the Content is investment advice » ;
  - SOFR et BGCR sont calculés à partir de données sous licence de DTCC Solutions LLC.
  [NY Fed Terms of Use](https://www.newyorkfed.org/privacy/termsofuse)

#### Philadelphia Fed : RTDSM et SPF
- RTDSM : vintages (« snapshots ») de séries macro.
  - Téléchargements : « Complete vintage history » (en niveaux) et valeurs de 1re, 2e et 3e publication pour certaines variables.
  - « All data are updated at the end of each month ».
  - Ajout récent de 24 variables PIB-revenu (GDI).
  [RTDSM](https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-for-macroeconomists)
- Variables : ROUTPUT, NOUTPUT, RCON, P, PCON, PCONX, CPI (vintages trimestriels), PCPI (vintages mensuels), PCPIX, RUC, EMPLOY, M1, M2, IPT, HSTARTS, etc. — [RTDSM Full-Time Series History](https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-full-time-series-history)
- Les vintages commencent en novembre 1965 — [Croushore & Stark doc](https://facultystaff.richmond.edu/~dcrousho/docs/brso00dc.pdf) (vu via résultats de recherche)
- SPF : enquête trimestrielle lancée en 1968:Q4 (ASA/NBER), reprise par la Philly Fed en 1990:Q2. Fichiers Excel : moyennes, médianes, réponses individuelles, dispersion — [SPF documentation](https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/survey-of-professional-forecasters/spf-documentation.pdf) ; [SPF mean forecasts](https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/mean-forecasts)

#### Atlanta Fed GDPNow
- Prévisions historiques dans un tableur téléchargeable : `GDPTrackingModelDataAndForecasts.xlsx`, avec les onglets TrackingDeepArchives (2011:Q3–2014:Q1), TrackingArchives (depuis 2014:Q2), TrackingHistory, ContribHistory et TrackingHistoryGold — [GDPNow](https://www.atlantafed.org/research-and-data/data/gdpnow) ; [GDPNow slides](https://www.atlantafed.org/-/media/documents/cqer/researchcq/gdpnow/RealGDPTrackingSlides.pdf)
- Série FRED `GDPNOW` (trimestrielle, en % annualisé). La valeur courante est révisée plusieurs fois par trimestre — [FRED GDPNOW](https://fred.stlouisfed.org/graph?graph_id=1439392) (vu via résultats de recherche)

#### Cleveland Fed
- Nowcasts quotidiens de l'inflation CPI et PCE, headline et core. DOI de citation : `10.26509/frbc-inflationnowcast` — [Inflation Nowcasting](https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting) ; [Nowcasting users guide](https://www.Clevelandfed.Org/-/media/project/clevelandfedtenant/clevelandfedsite/indicators-and-data/inflation-nowcasting/nowcasting_users_guide.pdf)
- Anticipations d'inflation : modèle fondé sur les taux du Trésor, l'inflation, les swaps d'inflation et les enquêtes — [Inflation Expectations](https://www.clevelandfed.org/en/indicators-and-data/inflation-expectations)
- Sur FRED, `EXPINF10YR` est mensuelle et a été mise à jour le 10 novembre 2026 — [FRED EXPINF10YR](https://fred.stlouisfed.org/series/EXPINF10YR)

#### EIA API v2
- Base : `https://api.eia.gov/v2/{route}/data`, HTTPS uniquement.
  - Clé gratuite reçue par email. Elle doit passer en paramètre d'URL `api_key` (le header n'est pas lu).
  - Plafonds : 5 000 lignes par réponse JSON, 300 en XML ; pagination `offset`/`length`.
  - Throttling par seconde et par heure, sans chiffres ; suspension temporaire de la clé en cas de dépassement.
  - Version 2.1.0. APIv1 dépréciée. Les anciens identifiants de série restent accessibles via `/v2/seriesid/{ID}`.
  [EIA API documentation](https://www.eia.gov/opendata/documentation.php)
- Licence : « U.S. government publications are in the public domain ». Citation avec date, par exemple « Source: U.S. Energy Information Administration (Oct 2008) ». Exception pour les contenus tiers — [EIA Copyrights and Reuse](https://www.eia.gov/about/copyrights_reuse.php)

#### USDA NASS Quick Stats et ERS
- NASS :
  - clé obligatoire (paramètre `key`), obtenue par formulaire et email, utilisable immédiatement ;
  - au maximum 50 000 lignes par requête (erreur « exceeds limit = 50000 ») ; vérifier d'abord avec `get_counts` ;
  - formats JSON, CSV, XML ;
  - mention obligatoire « This product uses the NASS API but is not endorsed or certified by NASS ».
  [NASS Quick Stats API](https://quickstats.nass.usda.gov/api)
- ERS :
  - clé api.data.gov passée en `api_key` ;
  - ARMS sous `https://api.ers.usda.gov/data/arms/`, GraphQL sous `/data/arms/graphql`.
  [ARMS Data API](https://ers.usda.gov/developer/data-apis/arms-data-api) ; [ERS API ToS](https://ers.usda.gov/developer/api-terms-of-service)
- Limite par défaut d'api.data.gov : 1 000 requêtes/heure par clé (source secondaire) — [Jentic ERS](https://jentic.com/apis/api.ers.usda.gov/usda-ers)

#### DOL ETA (assurance-chômage)
- ETA-539 = données hebdomadaires « finales ». ETA-538 = chiffres avancés, 5 jours après la semaine de référence — [OMB supporting statement](https://omb.report/icr/202509-1205-006/doc/162970900)
- La page `claims.asp` affichait une erreur de base de données (Informix) lors de la consultation — [DOL claims](https://oui.doleta.gov/unemploy/claims.asp)

#### FHFA HPI
- Fichier maître (trimestriel et mensuel) : `https://www.fhfa.gov/hpi/download/monthly/hpi_master.csv`, HTTP 200, environ 17 Mo — [Test direct 2026-11-14](https://www.fhfa.gov/hpi/download/monthly/hpi_master.csv) ; formats CSV/JSON/XML/SQL — [FHFA HPI datasets](https://www.FHFA.gov/DataTools/Downloads/Pages/House-Price-Index-Datasets.aspx)
- Publication mensuelle, par exemple « FHFA HPI monthly September 2026 » — [FHFA](https://www.fhfa.gov/document/d/hpi/fhfa-hpi-monthly-september-2026)

#### CFTC COT (Socrata SODA)
- `https://publicreporting.cftc.gov/resource/{id}.json` avec `$limit`, `$order`, `$select` et `$where`. Le jeu Legacy Futures Only remonte au 1986-01-15. Dernière date de rapport : 2026-11-03, avec `X-SODA2-Truth-Last-Modified: Fri, 06 Nov 2026 20:30:33 GMT` (soit 15 h 30 ET le vendredi) — [Test direct 2026-11-14](https://publicreporting.cftc.gov/resource/6dca-aqww.json)
- Identifiants des jeux de données — [CFTC API Help](https://publicreporting.cftc.gov/stories/s/r4w3-av2u)

#### Calendrier FOMC
- Page HTML (2021–2027). Les dates de réunion restent provisoires jusqu'à leur confirmation. Réunions 2026 : 27–28 janv., 17–18 mars, 28–29 avr., 16–17 juin, 28–29 juil., 15–16 sept., 27–28 oct., 8–9 déc. — [FOMC calendars](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) ; [Chicago Fed calendars](https://www.chicagofed.org/utilities/about-us/federal-reserve-calendars)

#### data.gov (CKAN)
- API CKAN `http://catalog.data.gov/api/3/` — [data.gov APIs](https://data.gov/developers/apis/)
- Catalogue bêta `catalog-beta.data.gov` en janvier 2026 (511 462 jeux contre 391 139 sur le catalogue en ligne) — [Rogue Scholar, janv. 2026](https://rogue-scholar.org/records/hnrkb-3h835)
- Lancement du catalog.data.gov repensé en avril 2026 — [data.gov timeline](https://data.gov/timeline/)

### Inferences
- Matrice de synthèse :

  | Source | Clé | Limite documentée | Licence (résumé) |
  |---|---|---|---|
  | FRED/ALFRED | oui, une par application | 120/min | Données publiques sauf séries « Copyrighted » ; mention de non-endorsement ; pas de clone de FRED |
  | BLS | v2 oui (renouvellement annuel) | 500/j, 50 séries, 20 ans | Pas de mention explicite « domaine public » dans les ToS ; citer la date d'accès + disclaimer |
  | BEA | oui | ~100 req/30 err/100 Mo par min (secondaire) | Domaine public, citation appréciée |
  | Census | oui (depuis le 12/05/2026) | non chiffrée | Mention de non-endorsement |
  | Fiscal Data | non | non documentée | Libre, commercial OK |
  | Trésor XML/CSV | non | — | Non vérifiée |
  | NY Fed | non | non documentée | Conditions NY Fed + disclaimers ; données DTCC pour SOFR/BGCR |
  | EIA | oui | 5 000 lignes JSON | Domaine public, citation avec date |
  | NASS | oui | 50 000 lignes | Mention de non-endorsement |
  | CFTC | non (token optionnel) | non vérifiée | Non vérifiée |

- L'exigence du brief (« origin, date, processing, licence, reuse ») peut être couverte de façon systématique. Côté FRED, on lit les étiquettes de droits (via `fred/series/tags`) et les notes de chaque série, puis on refuse automatiquement les séries marquées « Copyrighted: Pre-approval Required ». Les séries du kit de départ (DFF, DGS2, DGS10, CPIAUCSL, UNRATE) viennent de la Fed Board/Trésor et du BLS, donc probablement du domaine public. À confirmer par leurs étiquettes.
- L'avis de non-endorsement exigé par FRED, Census et NASS doit apparaître dans l'interface d'AlphaForge (pied de page, par exemple), pas seulement dans la base de connaissances.

### Gaps
- Je n'ai pas pu lire le guide PDF BEA ni le PDF des conditions de l'API BEA : pas d'outil PDF disponible. Les limites BEA ne sont confirmées que par une source secondaire. La durée de blocage (souvent citée à 1 heure) n'est pas vérifiée.
- Le nom du header d'authentification de FRED v2 n'est pas documenté sur la page lue. Peut-être `Authorization: Bearer`, mais c'est non vérifié.
- Je n'ai pas lu les conditions d'utilisation des sites home.treasury.gov, Philly Fed, Atlanta Fed, Cleveland Fed, FHFA, CFTC ni DOL. Ce sont probablement des œuvres du gouvernement fédéral (domaine public) pour le Trésor, la FHFA, la CFTC et le DOL. Pour les Fed régionales (entités non gouvernementales), il faut vérifier.
- Je n'ai pas trouvé de limites de débit officielles pour Fiscal Data, NY Fed, Census, EIA (pas de chiffres) ni CFTC/Socrata.
- Je n'ai pas pu vérifier la représentation d'octobre 2025 dans FRED pour CPIAUCSL et UNRATE : le téléchargement `fredgraph.csv` a expiré.

## Q3. Capacité point-in-time (dates de publication, vintages, premières publications)

### Takeaway
ALFRED, via l'API FRED, est la seule API qui rend directement « la valeur telle que connue à la date D » pour des milliers de séries. On l'obtient en fixant `realtime_start = realtime_end = D` sur `fred/series/observations`, ou avec `vintage_dates=D`, et `output_type=4` donne les premières publications. Le calendrier des publications (`fred/releases/dates`, `fred/release/dates`) date les sorties. La Philly Fed RTDSM est la référence académique de secours (Excel, vintages depuis 1965). Les API d'agence (BLS, BEA, Census, Fiscal Data, NY Fed) ne servent que la dernière valeur révisée.

### Cited Findings
- Le paramètre temps réel : « The real-time period marks when facts were true or when information was known until it changed ».
  - `realtime_start` et `realtime_end` valent par défaut la date du jour (mode FRED) ; l'intervalle inclut ses deux bornes.
  - `realtime_start=1776-07-04&realtime_end=9999-12-31` renvoie toute l'information connue.
  [Real-Time Periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)
- `output_type` de `series/observations` :
  - 1 = « Observations by Real-Time Period » ;
  - 2 = « Observations by Vintage Date, All Observations » ;
  - 3 = « Observations by Vintage Date, New and Revised Observations Only » ;
  - 4 = « Observations, Initial Release Only ».
  [series/observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
- `vintage_dates` : liste de dates YYYY-MM-DD séparées par des virgules, « used to download data as it existed on these specified dates in history ». Maximum par requête : 2 000 en JSON/XML et 1 000 en CSV/XLSX. Avec `output_type=2` : 450 CSV / 225 XLSX pour une série quotidienne, 110/55 pour USRECD — [series/observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
- `fred/series/vintagedates` liste les dates de vintage d'une série. `fred/release/dates` et `fred/releases/dates` donnent les dates de publication — [FRED API docs](https://fred.stlouisfed.org/docs/api/fred/)
- `fred/releases/dates` : `realtime_start` vaut par défaut le 1er janvier de l'année en cours, `realtime_end` 9999-12-31, `limit` au plus 1 000, tri `release_date desc`. Par défaut (`include_release_dates_with_no_data=false`), la requête « excludes future release dates which may be available in the FRED release calendar ». Passer `true` pour obtenir le calendrier futur, avec l'attribut `release_last_updated` — [releases/dates](https://fred.stlouisfed.org/docs/api/fred/releases_dates.html)
- FRED v2 `release/observations` n'expose ni vintage ni temps réel, seulement `last_updated` — [FRED v2 release/observations](https://fred.stlouisfed.org/docs/api/fred/v2/release_observations.html)
- Le connecteur MCP FRED n'a pas d'outil vintage. Ses réponses portent `realtime_start`/`realtime_end`, et il renvoie vers ALFRED pour les vintages antérieurs — [FRED MCP Connector](https://fred.stlouisfed.org/help/data/connecting-fred-to-ai-services/FRED-MCP-Connector)
- fredapi encapsule ALFRED : `get_series_first_release('GDP')`, `get_series_as_of_date('GDP', '6/1/2014')` (renvoie `date`, `realtime_start`, `value`), `get_series_all_releases('GDP')` et `get_series_vintage_dates('GDP')` — [fredapi GitHub](https://github.com/mortada/fredapi)
- Philly Fed RTDSM : historique complet de chaque vintage, et valeurs de 1re, 2e et 3e publication pour certaines variables ; mise à jour en fin de mois — [RTDSM](https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-for-macroeconomists). CPI en vintages trimestriels (CPI) et mensuels (PCPI) — [RTDSM Full-Time Series History](https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-full-time-series-history)
- FRED-MD/QD : un fichier CSV par vintage mensuel ; archives 1999-08→2024-12 — [FRED-MD/QD](https://www.stlouisfed.org/research/economists/mccracken/fred-databases)
- GDPNow : onglets d'historique des prévisions (TrackingArchives depuis 2014:Q2) — [GDPNow](https://www.atlantafed.org/research-and-data/data/gdpnow)
- BLS : les notes de bas de page signalent par exemple `P` = « Preliminary », sans historique de vintages — [BLS API Signature v2](https://www.bls.gov/developers/api_signature_v2.htm)
- NY Fed : champ `revisionIndicator` dans les réponses SOFR — [Test direct 2026-11-14](https://markets.newyorkfed.org/api/rates/secured/sofr/last/2.json)
- Fiscal Data : seulement `record_date`, aucun champ de date de publication — [Test direct 2026-11-14](https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny?sort=-record_date&page[size]=1)
- DOL : ETA-538 avancé contre ETA-539 final — [OMB supporting statement](https://omb.report/icr/202509-1205-006/doc/162970900)
- CFTC : la date de rapport (mardi) et la date de mise en ligne (vendredi 15 h 30 ET) sont deux dates différentes — [Test direct 2026-11-14](https://publicreporting.cftc.gov/resource/6dca-aqww.json)

### Inferences
- **Recette « valeur connue à la date D » (ALFRED)** :
  `GET https://api.stlouisfed.org/fred/series/observations?series_id=CPIAUCSL&realtime_start=D&realtime_end=D&file_type=json&api_key=...`
  Chaque observation renvoyée porte `realtime_start` (première date où ce chiffre était connu) et `realtime_end`. Pour reconstruire de nombreuses dates D d'un coup, utiliser `vintage_dates=D1,D2,...` avec `output_type=2`, ou `realtime_start=1776-07-04&realtime_end=9999-12-31` (output_type=1) puis filtrer localement sur `realtime_start <= D <= realtime_end`. Pour la date de publication d'une valeur, `realtime_start` de la première observation qui la contient sert de proxy de date de publication. Pour les sorties futures, croiser avec `fred/release/dates?include_release_dates_with_no_data=true`.
- **Modèle OKF** : stocker pour chaque point quatre champs, `observation_date`, `value`, `realtime_start` (connu depuis) et `realtime_end` (connu jusqu'à). L'agent de simulation n'expose alors que les points où `realtime_start <= date_simulée`. C'est la protection directe contre le look-ahead demandée par le brief.
- Les séries quotidiennes de marché (DGS10, DFF, SOFR) ne sont presque jamais révisées. On peut prendre la date d'observation plus un jour ouvré comme date de disponibilité. Pour la NY Fed, surveiller `revisionIndicator`.
- Les séries que ALFRED n'archive pas (Fiscal Data, CFTC, FHFA hors FRED) demandent un archivage local d'A5 : on horodate chaque collecte et on garde l'historique des réponses. Sinon il n'y a pas de point-in-time possible.

### Gaps
- Je n'ai pas vérifié la couverture ALFRED pour chacune des 5 séries du kit de départ (dates de vintages disponibles). On peut le faire avec `fred/series/vintagedates`, mais il faut une clé.
- Je n'ai pas confirmé la convention de datation des vintages RTDSM (milieu de mois ou de trimestre ?) ni le format exact des fichiers (xlsx, disposition lignes/colonnes).
- J'ignore si FRED-MD/QD et GDPNow publient des dates de publication par observation.

## Q4. Clients Python et serveurs MCP

### Takeaway
Les clients mûrs côté Python sont fredapi (Apache-2.0, le seul à gérer ALFRED nativement), pyfredapi (v0.9.1), beaapi (officiel BEA, CC0) et les wrappers usuels. Côté MCP, il existe depuis 2026 un connecteur officiel FRED (gratuit, sans clé API mais avec un compte dédié, 5 outils, sans vintages). Les autres serveurs MCP (BLS, BEA, multi-sources) sont communautaires et à auditer.

### Cited Findings
- fredapi : `pip install fredapi`, version 0.5.1, licence Apache-2.0. Méthodes ALFRED : `get_series_first_release`, `get_series_latest_release`, `get_series_as_of_date`, `get_series_all_releases`, `get_series_vintage_dates` — [fredapi GitHub](https://github.com/mortada/fredapi)
- pyfredapi : couvre « all the FRED API endpoints », FRED et ALFRED, sortie pandas ou JSON. Version 0.9.1, dépôt `gw-moore/pyfredapi` — [pyfredapi PyPI](https://pypi.org/project/pyfredapi/)
- fedfred (autre client FRED avec usages avancés) — [fedfred docs](https://nikhilxsunder.github.io/fedfred/installation/advanced_usage.html)
- beaapi : client officiel du BEA (organisation GitHub `us-bea`), `pip install beaapi`, licence CC0-1.0. Exemples : `beaapi.get_data(beakey, datasetname='NIPA', TableName='T20305', Frequency='Q', Year='2015')`, `search_metadata`. Pendant R : `bea.R` — [beaapi PyPI](https://pypi.org/project/beaapi/)
- Autres clients BEA non officiels : beapy, pyBEA, python-bea, datapungibea (ce dernier annonce des vintages) — [recherche PyPI](https://pypi.org/project/datapungibea/1.0.1/)
- NASS : clients R `rnassqs` et `usdarnass`, avec pré-comptage des lignes — [rnassqs](https://docs.ropensci.org/rnassqs/articles/rnassqs.html)
- Connecteur MCP officiel FRED :
  - endpoint `https://mcp.stlouisfed.org` ;
  - compte « FRED MCP Connector » (Okta), distinct du compte FRED ; « does not require a FRED API key » ; gratuit ;
  - outils : `fred-search-series`, `fred-get-series-metadata`, `fred-get-series-observations`, `fred-download-series-observations-link`, `fred-graph-series` ;
  - disponible dans l'annuaire de connecteurs Claude (claude.ai/directory/fred) ;
  - aucune limite d'usage publiée.
  [FRED MCP Connector](https://fred.stlouisfed.org/help/data/connecting-fred-to-ai-services/FRED-MCP-Connector)
- Annonce faite par le gouverneur Waller à FRED Con. Près de la moitié du trafic FRED viendrait d'agents IA — [PYMNTS](https://www.pymnts.com/?p=4264473) ; [Crypto Briefing](https://cryptobriefing.com/federal-reserve-fred-mcp-connector-ai/)
- Serveurs MCP communautaires :
  - FRED MCP de stefanoamorelli — [Glama](https://glama.ai/mcp/servers/@stefanoamorelli/fred-mcp-server/blob/41a5270f604aef6d81d0c33a9f2054be0d43a4dd/docs/api-reference/overview.mdx) ;
  - « US Government Open Data MCP » de lzinga (37 à 40 API, dont BLS, BEA, Census) — [Glama](https://glama.ai/mcp/servers/lzinga/us-government-open-data-mcp) ;
  - econstats-mcp (FRED, BLS, BEA, FMI, Banque mondiale, BCE) — [Glama](https://glama.ai/mcp/servers/joshfwaldman1/econstats-mcp) ;
  - BLS MCP de kovashikawa (données fictives par défaut) — [Glama](https://glama.ai/mcp/servers/kovashikawa/bls_mcp) ;
  - mcp-bea — [Glama](https://glama.ai/mcp/servers/@shawndrake2/mcp-bea).

### Inferences
- Pour A5 : utiliser fredapi (ou pyfredapi) pour FRED/ALFRED, `requests` direct pour BLS (POST JSON), Census, Fiscal Data, NY Fed et CFTC (SODA), et beaapi pour le BEA. Le connecteur MCP officiel FRED convient à l'exploration interactive par un agent LLM. Il ne remplace pas l'API pour le point-in-time, faute d'outil vintage.
- Les MCP communautaires multi-sources sont pratiques pour un prototype de datathon. Il faut toutefois contrôler qu'ils transmettent bien les métadonnées de licence et de date que le brief exige.

### Gaps
- Je n'ai pas vérifié le statut de maintenance 2026 de fredapi (date du dernier commit non affichée), ni de clients BLS Python (par exemple le paquet `bls`) ou Census (`census`, `cenpy`).
- Je n'ai pas trouvé de date précise de lancement du connecteur MCP FRED ni de limites d'usage.

## Q5. Pièges connus 2025–2026 (changements d'API, shutdowns, dépréciations, clés)

### Takeaway
Le shutdown du 1er octobre au 12 novembre 2025 a laissé des trous permanents. L'IPC d'octobre 2025 (« - », code X dans l'API BLS) et le taux de chômage d'octobre 2025 ne seront jamais publiés. Les variations sur 12 mois de l'IPC d'octobre 2026 manquent aussi. Le BEA a annulé le PIB avancé du T3 2025. En 2026, trois autres changements comptent : une clé est obligatoire pour l'API Census depuis le 12 mai 2026, le DDP de la Fed Board ferme (packages préformatés retirés le 31 mars 2027, page supprimée le 1er juillet 2027), et l'historique des séries ICE BofA sur FRED est tronqué à 3 ans depuis avril 2026.

### Cited Findings
**Shutdown du 1er octobre au 12 novembre 2025**
- Dates du « lapse in appropriations from October 1, 2025, through November 12, 2025 ». « BLS could not collect October 2025 reference period survey data » : aucun communiqué IPC pour octobre 2025 — [BLS CPI shutdown FAQ](https://www.bls.gov/cpi/additional-resources/2025-federal-government-shutdown-impact-cpi-faq.htm)
- Représentation dans les tableaux et dans la Public Data API : un tiret, avec la note « Data unavailable due to the 2025 lapse in appropriations ». Pas de variation nette ni en pourcentage — [BLS CPI shutdown FAQ](https://www.bls.gov/cpi/additional-resources/2025-federal-government-shutdown-impact-cpi-faq.htm)
- Confirmé : `{"year":"2025","period":"M10","value":"-","footnotes":[{"code":"X","text":"Data unavailable due to the 2025 lapse in appropriations"}]}` pour CUUR0000SA0 — [Test direct 2026-11-14](https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0?startyear=2025&endyear=2025)
- La moyenne annuelle 2025 (M13) est calculée sur 11 valeurs. Les loyers et l'OER d'octobre 2025 sont reportés depuis avril 2025. La variation d'avril 2026 des loyers sera « atypical » — [BLS CPI shutdown FAQ](https://www.bls.gov/cpi/additional-resources/2025-federal-government-shutdown-impact-cpi-faq.htm) (dernière modification le 16 septembre 2026)
- « BLS cannot publish 12-month percent changes for October 2026 for indexes where October 2025 data are unavailable » — [BLS notice 12m changes 2026-10](https://www.bls.gov/cpi/notices/2026/12m-changes-202610.htm) (dernière modification le 10 novembre 2026)
- C-CPI-U finales pour octobre–décembre 2025 prévues le 10 novembre 2026. Enquête CE non collectée en octobre et novembre 2025 — [BLS CPI shutdown FAQ](https://www.bls.gov/cpi/additional-resources/2025-federal-government-shutdown-impact-cpi-faq.htm)
- Emploi : l'enquête auprès des ménages (qui produit le taux de chômage) d'octobre 2025 ne peut pas être collectée rétroactivement. Les effectifs salariés d'octobre ont été publiés avec novembre — [Axios](https://www.axios.com/2025/11/13/government-shutdown-bls-report) ; [HR Brew](https://www.hr-brew.com/stories/2025/11/13/bls-missing-data-govt-shutdown)
- BEA : « The advance estimate of third-quarter GDP, originally scheduled during October, was canceled ». Estimation initiale le 23 décembre 2025, estimation mise à jour le 22 janvier 2026. Le PIB avancé du T4 2025 a été reporté. Le PIB par État a été décalé au 23 janvier 2026 — [BEA blog 2025-12-10](https://www.bea.gov/news/blog/2025-12-10/economic-release-schedule-updates)
- DOL : pas de rapport hebdomadaire national des demandes de chômage après le 25 septembre 2025 pendant le shutdown, mais des données téléchargeables pour la plupart des États. Les estimations ont été produites par des tiers (Bloomberg, JPMorgan) — [Bloomberg](https://www.bloomberg.com/news/articles/2025-10-23/us-initial-jobless-claims-rose-last-week-state-data-suggest)
- GDPNow : la mise à jour du 9 octobre 2025 a été reportée faute de nouvelles données mensuelles — [investingLive](https://investinglive.com/centralbank/atlanta-fed-gdpnow-growth-estimate-for-q3-remains-at-38-20251007) ; [Calculated Risk](https://www.calculatedriskblog.com/2025/10/q3-gdp-tracking-flyin-blind.html)
- Le Trésor a fixé un indice d'octobre 2025 de 325.604 pour ses propres calculs (TIPS) — [Treasury press release](https://home.treasury.gov/news/press-releases/sb0324) (vu via résultats de recherche)

**Shutdown partiel de début 2026**
- Le rapport sur l'emploi de janvier 2026, prévu le 6 février, a été reporté pour cause de « partial shutdown » — [WTOP](https://wtop.com/business-finance/2026/02/labor-department-delays-january-jobs-report-because-of-partial-shutdown/) ; [CBS News](https://www.cbsnews.com/news/jobs-report-delay-january-2026-bls-government-shutdown)
- Il a été reprogrammé au 11 février 2026, après un shutdown de quatre jours. JOLTS de décembre a aussi été reporté — [ROIC](https://www.roic.ai/news/bls-reschedules-january-employment-report-for-february-11-amid-government-shutdown-02-04-2026). Les sources divergent sur la date de début (30 ou 31 janvier 2026).

**Changements d'API et dépréciations**
- Fed Board DDP :
  - « As announced on July 16, today the Build Your Package function in the Data Download Program has been retired » (annonce datée du 2026-11-12) ;
  - « the Board plans to remove the preformatted data package option on March 31, 2027 » ;
  - « July 1, 2027, DDP page removal » ;
  - redirection vers FRED.
  [DDP H.15](https://www.federalreserve.gov/datadownload/Choose.aspx?rel=H15) ; [DDP](https://www.federalreserve.gov/datadownload/)
- Census : clé obligatoire pour toutes les requêtes de données depuis le 12 mai 2026 ; exemption ajoutée en juin 2026 pour les métadonnées — [repost de l'email Census](https://buttondown.com/crgibbons/archive/census-data-api-to-require-api-key/) ; [Census newsletter juin 2026](https://content.govdelivery.com/accounts/USCENSUS/bulletins/41aaf23)
- FRED : séries ICE BofA limitées à 3 ans d'observations depuis avril 2026 — [FRED BAMLC0A4CBBBEY](https://fred.stlouisfed.org/series/BAMLC0A4CBBBEY). Arrivée d'une API v2 (bulk par release, clé en header) — [FRED v2](https://fred.stlouisfed.org/docs/api/fred/v2/index.html)
- EIA : APIv1 dépréciée (maintenue « until at least January 2023 »), APIv2 uniquement en HTTPS — [EIA API documentation](https://www.eia.gov/opendata/documentation.php)
- BLS : clé v2 à renouveler chaque année — [BLS API FAQ](https://www.bls.gov/developers/api_faqs.htm)
- NY Fed : pas de versions multiples en production ; les nouveautés arrivent d'abord sous `/beta` — [NY Fed OpenAPI spec](https://markets.newyorkfed.org/static/docs/markets-api.yml)
- Trésor : avis développeur sur les changements du flux XML — [Treasury XML changes](https://home.treasury.gov/developer-notice-xml-changes). Une colonne « 1.5 Month » est présente dans le CSV 2026 — [Test direct 2026-11-14](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv)
- data.gov : catalogue repensé en avril 2026, bêta en janvier 2026 — [data.gov timeline](https://data.gov/timeline/) ; [Rogue Scholar](https://rogue-scholar.org/records/hnrkb-3h835)
- La page DOL `claims.asp` était en erreur de base de données lors de la consultation, alors que le CSV restait accessible — [DOL claims](https://oui.doleta.gov/unemploy/claims.asp) ; [Test direct 2026-11-14](https://oui.doleta.gov/unemploy/csv/ar539.csv)

### Inferences
- Les parseurs d'A5 doivent traiter la valeur `"-"` de BLS (code X) comme `NaN`, avec un motif explicite (« lapse in appropriations »), et ne pas planter sur un `float("-")`. Ne pas interpoler silencieusement : documenter l'imputation éventuelle dans le front-matter OKF (champ `processing`).
- Pour CPIAUCSL et UNRATE du kit de départ : octobre 2025 manque et le glissement annuel d'octobre 2026 n'est pas publié par le BLS. Tout calcul d'inflation sur 12 mois autour de ces dates doit être marqué « dérivé, non officiel ».
- Pour les simulations historiques, les publications retardées ou annulées de fin 2025 et début 2026 décalent les dates de disponibilité réelles. Il faut utiliser les `realtime_start` d'ALFRED plutôt qu'un calendrier théorique, pour éviter un look-ahead implicite.
- Nouvelles clés à prévoir pour le datathon : FRED, BLS v2, BEA, Census (désormais obligatoire), EIA, NASS et api.data.gov (ERS). Fiscal Data, NY Fed, Trésor, CFTC, FHFA et DOL n'en demandent pas.

### Gaps
- Je n'ai trouvé aucune information sur un éventuel shutdown ou retard de données après février 2026. Le CPI d'octobre 2026 est bien disponible dans l'API BLS au 14 novembre 2026 (337.511, `latest:true`), ce qui suggère un calendrier normal en fin 2026 — [Test direct 2026-11-14](https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0?startyear=2025&endyear=2025)
- Je n'ai pas vérifié l'effet du shutdown sur les vintages de la Philly Fed RTDSM, sur FRED-MD/QD, ni sur les autres séries BEA (PCE de septembre 2025, commerce).
- Je n'ai pas vérifié si le BLS ou d'autres agences ont modifié leurs API en 2026 : aucune annonce trouvée, et la page Developers du BLS est datée de 2016.
- Les sources divergent sur le début du shutdown 2026 (30 ou 31 janvier) et sa durée exacte.
