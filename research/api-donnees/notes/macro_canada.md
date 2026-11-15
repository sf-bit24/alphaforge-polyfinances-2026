# API de données macroéconomiques et statistiques officielles canadiennes (fédéral + provinces), état au 14 novembre 2026

> Méthode : la plupart des faits ci-dessous ont été **vérifiés par appel direct aux API le 2026-11-14 (samedi) depuis une IP non-cloud (WSL résidentiel)**. Quand une ligne cite une URL d'API, cette URL est la source primaire et la réponse a été observée en direct. Les autres faits viennent de la documentation officielle (citée). Tout ce qui vient seulement d'un extrait de moteur de recherche, ou qui est plus ancien, est signalé.
> Notation : « (live) » = observé par appel direct ce jour.

---

## Q1. Quelles API et quels points d'accès lisibles par machine existent ?

### Takeaway
Il y a deux vraies API « de série temporelle » fédérales, sans clé et bien documentées : **Banque du Canada Valet** (2 616 groupes, 16 380 séries) et **Statistique Canada WDS + SDMX** (8 282 tableaux), plus le **Delta File** quotidien et un **calendrier de diffusion JSON**. Presque tout le reste (Finances Canada, BSIF/OSFI, SCHL/CMHC, REC/CER, ISDE/ISED, RNCan/NRCan) passe par l'**API CKAN du Portail du gouvernement ouvert** (avec un DataStore interrogeable pour certaines ressources, p. ex. l'OSFI), ou par des fichiers CSV/ZIP. Côté provinces, il y a des CKAN pour l'Ontario, la C.-B., l'Alberta et le Québec, et une API JSON sans clé pour le tableau de bord économique de l'Alberta. Je n'ai trouvé aucune API documentée pour l'ISQ, l'HMIP de la SCHL, l'ACI/CREA ou Paiements Canada.

### Cited Findings

**Tableau d'inventaire (pertinence pour A5 : ★★★ = source principale, ★★ = complément, ★ = marginal)**

| # | Source | Point d'accès | Auth | Formats | Pertinence |
|---|---|---|---|---|---|
| 1 | Banque du Canada – Valet | `https://www.bankofcanada.ca/valet/` | aucune | JSON, CSV, XML | ★★★ |
| 2 | StatCan – Web Data Service (WDS) | `https://www150.statcan.gc.ca/t1/wds/rest/` | aucune | JSON (+ liens ZIP CSV/SDMX) | ★★★ |
| 3 | StatCan – SDMX REST | `https://www150.statcan.gc.ca/t1/wds/sdmx/statcan/rest/` | aucune | SDMX-ML 2.1, SDMX-JSON, CSV | ★★ |
| 4 | StatCan – Delta File (quotidien) | `https://www150.statcan.gc.ca/n1/delta/YYYYMMDD.zip` | aucune | ZIP (CSV + métadonnées) | ★★ (archivage PIT) |
| 5 | StatCan – calendrier des indicateurs clés | `https://www150.statcan.gc.ca/n1/dai-quo/ssi/homepage/schedule-key_indicators-eng.json` | aucune | JSON | ★★★ (dates de publication) |
| 6 | StatCan – tableaux « temps réel » (millésimes) | via WDS/SDMX (p. ex. 36-10-0491) | aucune | idem WDS | ★★★ (PIT) |
| 7 | Portail du gouvernement ouvert (CKAN) | `https://open.canada.ca/data/api/3/action/` | aucune en lecture | JSON (métadonnées), DataStore JSON, fichiers CSV/XLSX/ZIP | ★★ |
| 8 | Finances Canada – Revue financière / Tableaux de référence financiers | ressources CKAN + canada.ca | aucune | ZIP (CSV), HTML, XLSX | ★★ |
| 9 | BSIF/OSFI – FINDAT sur le gouvernement ouvert | CKAN DataStore | aucune | CSV, DataStore JSON | ★★ |
| 10 | SCHL/CMHC – tableaux miroirs StatCan + HMIP | WDS (34-10-xxxx), CKAN ; HMIP = portail web | aucune | CSV/XML ; HMIP : exports | ★★ |
| 11 | Régie de l'énergie du Canada (REC/CER) | CKAN + `https://www.cer-rec.gc.ca/open/...csv` | aucune | CSV | ★ |
| 12 | Centre canadien d'information sur l'énergie (CCIE/CCEI, RNCan + StatCan) | `https://energy-information.canada.ca/sdmx/rest/` | aucune | SDMX, CSV, JSON | ★ |
| 13 | ISDE/ISED (BSF, insolvabilité) | CKAN (org `ic`) | aucune | XLSX/CSV | ★ |
| 14 | Ontario | `https://data.ontario.ca/api/3/action/` | aucune | CKAN | ★ |
| 15 | Colombie-Britannique | `https://catalogue.data.gov.bc.ca/api/3/action/` | aucune | CKAN | ★ |
| 16 | Alberta – CKAN + API du tableau de bord économique | `https://open.alberta.ca/api/3/action/` ; `https://api.economicdata.alberta.ca/data?table=...` | aucune | CKAN ; JSON | ★ |
| 17 | Québec – Données Québec (ISQ) | `https://www.donneesquebec.ca/recherche/api/3/action/` | aucune | CKAN | ★ |
| 18 | ACI/CREA (MLS HPI) | téléchargement XLSX, pas d'API | — | XLSX | ★ (licence restrictive) |
| 19 | Paiements Canada | rapports PDF + pages statistiques, pas d'API | — | PDF/HTML | ★ |

- Valet expose **2 616 groupes** (live, `lists/groups/json`) et **16 380 séries** (live, `lists/series/json`) — [Valet lists/groups](https://www.bankofcanada.ca/valet/lists/groups/json), [Valet lists/series](https://www.bankofcanada.ca/valet/lists/series/json)
- Valet sert « exchange rates, economic statistics (including those associated with research, forecasting and analysis), other financial statistics and reports » — [Valet OpenAPI spec v1.0.1](https://www.bankofcanada.ca/valet/static/swagger/api-en.yml)
- Familles de groupes Valet, par préfixe (live) : SAN 690, BOS 333, MPR 327, CSCE 221, FSR 154, FSS 100, CES 82, INDINF 20, CORRA 11, BCPI 4, FX 4, CEER 8, TBILL 3, A4 12 — [Valet lists/groups](https://www.bankofcanada.ca/valet/lists/groups/json)
- **Groupes Valet utiles au-delà du dataset de départ** (noms exacts, live) — [Valet lists/groups](https://www.bankofcanada.ca/valet/lists/groups/json) :
  - **Change** : `FX_RATES_DAILY` (27 séries, p. ex. FXUSDCAD, FXEURCAD, FXJPYCAD, FXCNYCAD, FXMXNCAD), `FX_RATES_MONTHLY`, `FX_RATES_ANNUAL`, `FX_RATES_RECIPROCAL`, et pour l'historique `LEGACY_NOON_RATES`, `LEGACY_CLOSING_RATES`, `LEGACY_MONTHLY_RATES`, `LEGACY_ANNUAL_RATES`.
  - **Taux de change effectif** : `CEER`, `CEER_DAILY` (CEER_BROADN, CEER_MCN, CEER_OITPN, CEER_BROADN_XUS), `CEER_MONTHLY_NOMINAL`, `CEER_MONTHLY_REAL`, plus les pondérations.
  - **CORRA** : `CORRA` (14 séries : AVG.INTWO, volumes, nombre de déclarants, centiles 5/25/75/95, statut de publication, méthode), `CORRA_COMPOUNDED_INDEX`, `CORRA_METRICS`, `CORRA_TRANSPARENCY` (« summary of errors detected after publication »), `CORRA_TRANSPARENCY_METRICS`, `illustrative_rate_and_corra`.
  - **Marché monétaire et obligataire** : `MONEY_MARKET` (AVG.INTWO, CL.CDN.MOST.1DL, bons du Trésor de 1 mois à 1 an `TB.CDN.30D/60D/90D/180D/1Y.MID`), `TBILL_ALL`, `TBILL_TUESDAY`, `TBILL_WEDNESDAY`, `bond_yields_benchmark` (2, 3, 5, 7 et 10 ans, long terme, RRB), `bond_yields_all`, `bond_yields_marketable` (rendements moyens 1–3, 3–5, 5–10 et 10+ ans), `RRB_INDEX_RATIO`.
  - **Politique monétaire** : `ATABLE_POLICY_INSTRUMENT` (taux cible STATIC_ATABLE_V39079, taux du financement à un jour V122514), `ATABLE_INFLATION_CONTROL_TARGET`, `ATABLE_MONETARY_CONDITIONS`, `ATABLE_MONETARY_AGGREGATES`, `MONETARY_POLICY_IMPLEMENTATION`, `SETTLEMENT_BALANCES`.
  - **Inflation** : `CPI_MONTHLY` (9 séries : V41690973, V41690914, STATIC_TOTALCPICHANGE, STATIC_CPIXFET, CPIW, ATOM_V41693242 [IPCX], CPI_MEDIAN, CPI_TRIM, CPI_COMMON).
  - **Indicateurs des pressions sur la capacité et l'inflation** : `INDINF_CPI*`, `INDINF_EXPECTATIONS*`, `INDINF_LABOUR*`, `INDINF_PRODUCT*`, `INDINF_REAL_ESTATE*`, `INDINF_WAGES*`, `INDINF_BOS_Q`.
  - **Indice des prix des produits de base (IPPB/BCPI)** : `BCPI_WEEKLY`, `BCPI_MONTHLY` (M.BCPI, M.BCNE, M.ENER, M.MTLS, M.FOPR, M.AGRI, M.FISH ; chaque libellé renvoie au vecteur StatCan, p. ex. « Monthly BCPI Total – v52673496 »), `BCPI_ANNUAL`, `BCPI_WEIGHTS`.
  - **Enquête sur les perspectives des entreprises (EPE/BOS)** : `bos`, `BOS_ACTIVITY_PRICE_DATA` (BOS_ACTIVITY_INDICATOR, BOS_PRICE_INDICATOR), `BOS_BYREGION_*`, `BOS_BYSECTOR_*`, `BOS_BYSIZE_*`, `BOS_*_MAGNITUDE_DATA`, plus des groupes de graphiques par édition (`BOS_2026Q1` à `BOS_2026Q3_C9`).
  - **Enquête canadienne sur les attentes des consommateurs (CSCE)** : `CSCE` (135 séries, p. ex. CES_C1_SHORT_TERM, CES_C1_MID_TERM, CES_C1_LONG_TERM), `CES_DEMOGRAPHICS`, groupes par édition (`CSCE_2026Q3_*`).
  - **Enquête auprès des responsables du crédit (SLOS)** : `SLOS`, `slos_business_lending_conditions`, `slos_mortgage_lending`, etc.
  - **Rapport sur la politique monétaire (RPM/MPR)** : 327 groupes de données de graphiques **par édition**, de `MPR_2024M04_*` à `MPR_2026M10_*` (p. ex. `MPR_2026M10_USCAD_YIELDS`, `MPR_2026M10_SPREAD_BRENT`, `MPR_2026M01_AARGG_CAN` « Contributions to average annual real GDP growth »).
  - **Revue du système financier** : `FSR_*` (171 groupes).
  - **Projections économiques du personnel (historiques)** : `SWP-GDP`, `SWP-PCPI`, `SWP-PCPIX`, `SWP-URATE`, `SWP-LYGAP`, `SWP-R1N`, `SWP-R20N`, `SWP-USCANPFX`, etc. ; un millésime par trimestre de projection (SWP-GDP : 133 séries, de `SWP-GDP1986Q4` à `SWP-GDP2019Q4`).
  - **Taux bancaires et crédit** : `CHARTERED_BANK_INTEREST` (taux préférentiel V80691311, hypothèques ordinaires 1, 3 et 5 ans V80691333/V80691334/V80691335, CPG), `A4_RATES_*`, `A4_FUNDS_*`, `E1_MONTHLY` (agrégats monétaires), `E2_MONTHLY` (crédit), `C1`–`C9`, `J2_*` (marges de crédit hypothécaires), `K8`, `G4`/`G6`/`G7` (dette du GdC).
  - **Adjudications et dette** : `AUC_*` (obligations, bons du Trésor, RRB, ultra-longues, calendrier), `GOC_OUTSTANDING`, `OFFICIAL_INT_RES`.
- Je n'ai trouvé aucun groupe CDOR dans la liste Valet (recherche par mot-clé sur le JSON live) — [Valet lists/groups](https://www.bankofcanada.ca/valet/lists/groups/json)
- StatCan WDS : `getAllCubesListLite` renvoie **8 282 tableaux** (live) — [WDS getAllCubesListLite](https://www150.statcan.gc.ca/t1/wds/rest/getAllCubesListLite)
- StatCan propose quatre voies d'accès : WDS (« discrete amount of data points »), SDMX REST, **Delta File** (« all data and metadata released by Statistics Canada each business day… preferred mechanism for users who want to obtain large updates ») et téléchargement CSV/SDMX de tableaux complets — [StatCan Developers](https://www.statcan.gc.ca/en/developers)
- Calendrier JSON : « Returns every release date of major economic indicators since March 14, 2012 », GET, sans authentification, version française en remplaçant `-eng` par `-fra` (page modifiée le 2025-03-28) — [schedule-key_indicators-eng.json doc](https://www.statcan.gc.ca/en/developers/schedule-key_indicators-eng-json)
- Calendrier JSON (live) : 2 882 entrées, dont 79 dates futures au 2026-11-14. Exemples : IPC d'octobre 2026 le 2026-11-16 ; Commerce de détail de septembre 2026 le 2026-11-20 ; PIB du T3 2026 le 2026-11-30 ; EPA de novembre 2026 le 2026-12-04 — [schedule JSON](https://www150.statcan.gc.ca/n1/dai-quo/ssi/homepage/schedule-key_indicators-eng.json)
- Calendrier lisible par un humain (toutes les diffusions du Quotidien) — [Release schedule](https://www150.statcan.gc.ca/n1/dai-quo/cal2-eng.htm)
- Portail CKAN fédéral : `package_search` répond sans clé (live) ; l'aide en ligne de l'API est à `help_show` — [CKAN package_search help](https://open.canada.ca/data/api/3/action/help_show?name=package_search)
- Organisations CKAN pertinentes (live) : `fin` (Revue financière 2018–2026, Tableaux de référence financiers), `osfi-bsif` (37 jeux), `cmhc-schl` (37 jeux), `cer-rec` (85 jeux), `ic` (statistiques d'insolvabilité), `nrcan-rncan` — [CKAN package_search](https://open.canada.ca/data/api/3/action/package_search?q=organization:osfi-bsif)
- Alberta : les pages du tableau de bord économique renvoient à des URL d'API comme `https://api.economicdata.alberta.ca/data?table=GDPMarket_36100222&GeoName=Alberta&...`. L'appel sans clé renvoie du JSON `[{"Date","GeoID","GeoName","Estimates","Prices","Value"}]` depuis 1981 (live) — [Alberta Economic Dashboard – GDP](https://economicdashboard.alberta.ca/dashboard/gdp-at-market-prices/), [API Alberta (exemple)](https://api.economicdata.alberta.ca/data?table=GDPMarket_36100222&GeoName=Alberta&Estimates=Gross%20domestic%20product%20at%20market%20prices&Prices=Chained%20(2017)%20dollars)
- CCEI : l'API est conforme SDMX REST, avec des exemples du type `https://energy-information.canada.ca/sdmx/rest/data/STC,DF_38100139,1.0/A.1.1.14` et des formats `csv` et `jsondata` (page modifiée le 2023-02-24, donc ancienne) — [CCEI Web Data Service User Guide](https://energy-information.canada.ca/en/resources/web-data-service-user-guide)
- SCHL/CMHC : le portail HMIP est décrit comme « free… access anytime to the latest housing market data » (extrait de recherche). Le paquet R `cmhc` se présente comme « API wrapper for extracting CMHC data out of the CMHC Housing Market Information Portal » — [HMIP](https://www.cmhc-schl.gc.ca/hmiportal), [mountainMath/cmhc README](https://github.com/mountainMath/cmhc)
- ACI/CREA : les données MLS® HPI se téléchargent en Excel (.xlsx) via l'outil HPI. Prochain paquet statistique annoncé le mardi 17 novembre 2026 (extrait de recherche, non relu en entier) — [CREA MLS HPI](https://www.crea.ca/housing-market-stats/mls-home-price-index/), [CREA stats](https://creastats.crea.ca/en-CA/)
- Paiements Canada : rapport annuel « Canadian Payment Methods and Trends » (édition 2025 en PDF ; 22,5 G transactions et 12,2 T$ en 2024) et pages statistiques ACSS/Lynx. Aucune API ni portail de données ouvertes trouvé — [Payments Canada 2024 data release](https://www.payments.ca/insights/research/canada-reaches-122-trillion-payment-transactions-2024-credit-cards-accounting-1-3), [CPMT 2025 PDF](https://www.payments.ca/sites/default/files/PaymentsCanada_Canadian_Payment_Methods_and_Trends_2025_EN.pdf)

### Inferences
- Pour A5, le noyau « API » se limite à Valet + WDS/SDMX + le calendrier JSON + les tableaux temps réel. Tout le reste relève de l'ingestion de fichiers (CKAN → CSV/ZIP/XLSX), avec un adaptateur par source.
- De nombreuses données « provinciales » ou « sectorielles » (mises en chantier de la SCHL, prix des produits de base, PIB de l'Alberta) sont en fait des **tableaux StatCan republiés**. Mieux vaut les prendre directement dans WDS, qui fournit un `releaseTime`, plutôt que par le miroir provincial ou CKAN, qui n'a qu'un `metadata_modified`.

### Gaps
- Je n'ai trouvé **aucune API officielle documentée** pour l'ISQ, la SCHL (HMIP), l'ACI/CREA ni Paiements Canada (Q1 et fiches ci-dessous).
- Je n'ai pas inventorié exhaustivement les 16 380 séries Valet. Seuls les groupes ont été listés (et les groupes « chart » des rapports n'ont pas été détaillés un par un).
- L'ARC/CRA n'expose aucune donnée macro par API (rien trouvé). Je n'ai pas fait de recherche approfondie.

---

## Q2. Fiche technique par API : URL, documentation, authentification, limites, formats, couverture, licence

### Takeaway
Aucune des sources retenues n'exige de clé, d'OAuth ou de frais. Les seules limites de débit chiffrées et publiées sont celles de StatCan (50 req/s pour le serveur, 25 req/s par IP). La Banque du Canada interdit de contourner ses limites sans les chiffrer. Les licences permettent toutes la redistribution avec attribution : Licence ouverte de StatCan, Licence du gouvernement ouvert – Canada 2.0, et conditions de la BdC. Seule l'ACI/CREA interdit l'usage commercial sans permission écrite.

### Cited Findings

#### Fiche 1 — Banque du Canada, Valet API
- **URL de base** : `https://www.bankofcanada.ca/valet`. **Documentation** : Swagger sur `/valet/docs` (OpenAPI 3.0.3, version de spec 1.0.1) et guide pratique — [Valet docs](https://www.bankofcanada.ca/valet/docs), [spec YAML](https://www.bankofcanada.ca/valet/static/swagger/api-en.yml), [How-to guide](https://www.bankofcanada.ca/valet-api-how-to/)
- **Endpoints** : `/lists/{groups|series}/{format}`, `/series/{seriesName}/{format}`, `/groups/{groupName}/{format}`, `/observations/{seriesNames}/{format}` (plusieurs séries séparées par des virgules), `/observations/group/{groupName}/{format}`, `/fx_rss`, `/fx_rss/{seriesNames}`, et les recherches paginées `/search/series` et `/search/groups` — [spec YAML](https://www.bankofcanada.ca/valet/static/swagger/api-en.yml)
- **Paramètres** : `start_date`, `end_date` (AAAA-MM-JJ), `recent`, `recent_weeks`, `recent_months`, `recent_years`, `order_dir` (asc|desc) — [spec YAML](https://www.bankofcanada.ca/valet/static/swagger/api-en.yml)
- **Formats** : `json`, `csv`, `xml`. Le CSV contient des blocs « TERMS AND CONDITIONS », « SERIES » et « OBSERVATIONS » (live) — [spec YAML](https://www.bankofcanada.ca/valet/static/swagger/api-en.yml), [exemple CSV](https://www.bankofcanada.ca/valet/observations/FXUSDCAD/csv?recent=2)
- **Authentification et coût** : « No registration is required… You do not need an access key. » ; « There is no cost » — [How-to guide](https://www.bankofcanada.ca/valet-api-how-to/)
- **Limites de débit** : aucun chiffre publié. Le guide renvoie aux conditions d'utilisation et recommande de démarrer lentement en période de pointe, d'appliquer un back-off aléatoire ou croissant et de mettre en cache les données quotidiennes — [How-to guide](https://www.bankofcanada.ca/valet-api-how-to/). Les conditions interdisent de « Circumvent such limit or limits imposed by the Bank with respect to the number or frequency of requests… (e.g., the Bank of Canada Valet API) » — [BoC Terms](https://www.bankofcanada.ca/terms/)
- **Avertissement de délai** : « there may be a brief processing delay between when data is published and when it appears in the API » — [spec YAML](https://www.bankofcanada.ca/valet/static/swagger/api-en.yml)
- **Heure de publication du change** : « Daily average exchange rates – published once each business day by 16:30 ET. All Bank of Canada exchange rates are indicative rates only. » Les moyennes mensuelles et annuelles sont publiées vers 16 h 30 HE le dernier jour ouvrable de la période — [spec YAML](https://www.bankofcanada.ca/valet/static/swagger/api-en.yml)
- **En-têtes HTTP observés** : `Cache-Control: max-age=30`, `Access-Control-Allow-Origin: *`, `Server: BoC` (live) — [Valet lists/groups](https://www.bankofcanada.ca/valet/lists/groups/json)
- **Fraîcheur observée** (live, 2026-11-14) : V39079 (cible du taux à un jour) = 2,50 au 2026-11-12 ; AVG.INTWO (CORRA) = 2,53 ; rendement 10 ans 3,78 et 2 ans 3,33 au 2026-11-12 ; FXUSDCAD = 1,4257 au 2026-11-13 ; M.BCPI à 2026-10 ; W.BCPI au 2026-11-04 ; CPI_TRIM = 1,8 pour 2026-09 ; BOS_ACTIVITY_INDICATOR = −0,2 daté 2026-07-01 ; CES_C1_SHORT_TERM = 4,03 daté 2026-07-01 — [observations](https://www.bankofcanada.ca/valet/observations/V39079,AVG.INTWO,FXUSDCAD,BD.CDN.2YR.DQ.YLD,BD.CDN.10YR.DQ.YLD,TB.CDN.90D.MID,CEER_BROADN/json?recent=1)
- **Profondeur historique** : exemple SWP-GDP2019Q4, observations de 1980-03-31 à 2021-12-31 (live). Les autres profondeurs varient selon la série et n'ont pas été mesurées une à une — [SWP-GDP2019Q4](https://www.bankofcanada.ca/valet/observations/SWP-GDP2019Q4/json)
- **Licence et conditions** : « the Bank permits you to freely use, copy, distribute and transmit its website content » si l'on respecte trois règles. (1.1) Attribution : « You must attribute the Bank of Canada as the source of the content, and indicate if changes were made », sans laisser croire à un endossement. (1.2) Exactitude. (1.3) Avis : si le contenu est fourni via un service payant, il faut informer l'acheteur qu'il est disponible gratuitement sur le site de la Banque. Exceptions : images de billets, logo et mot-symbole, **contenu de tiers** (« The Bank does not grant You permission to re-use such third-party content unless it expressly indicates ») — [BoC Terms](https://www.bankofcanada.ca/terms/)
- Chaque réponse Valet inclut `"terms": {"url": "https://www.bankofcanada.ca/terms/"}` (live) — [Valet groups/CPI_MONTHLY](https://www.bankofcanada.ca/valet/groups/CPI_MONTHLY/json)
- Les séries IPC de Valet sont décrites comme « as published by Statistics Canada and tracked by the Bank of Canada » (live) — [Valet groups/CPI_MONTHLY](https://www.bankofcanada.ca/valet/groups/CPI_MONTHLY/json)

#### Fiche 2 — Statistique Canada, Web Data Service (WDS)
- **URL de base** : `https://www150.statcan.gc.ca/t1/wds/rest/`. **Guide** : version 1.6 du 24 janvier 2025 (« Added issueDate field to 3 methods; Notes regarding error response status code ») — [WDS User Guide](https://www.statcan.gc.ca/en/developers/wds/user-guide)
- **Méthodes** : getChangedSeriesList, getChangedCubeList/{date}, getCubeMetadata, getSeriesInfoFromCubePidCoord, getSeriesInfoFromVector, getAllCubesList, getAllCubesListLite, getChangedSeriesDataFromCubePidCoord, getChangedSeriesDataFromVector, getDataFromCubePidCoordAndLatestNPeriods, getDataFromVectorsAndLatestNPeriods, getBulkVectorDataByRange, getDataFromVectorByReferencePeriodRange (GET, ajoutée en v1.5, 10 février 2021), getFullTableDownloadCSV, getFullTableDownloadSDMX, getCodeSets — [WDS User Guide](https://www.statcan.gc.ca/en/developers/wds/user-guide)
- **Limites** : « Server limits of 50 requests per second with a individual IP address limit of 25 requests per second. » ; « From 12 midnight Eastern Standard Time until 8:30am, certain methods will not return data… HTTP response code of 409 (Not available) could occur » ; mises à jour « every business day at 8:30 am Eastern » — [WDS User Guide](https://www.statcan.gc.ca/en/developers/wds/user-guide)
- **Volume** : « Web Data Service methods are not meant to obtain large data updates, as there will be limits to the number of data points per request… the Delta File is designed for users who need to consume large volume of data points ». Le guide ne chiffre pas ces limites — [WDS User Guide](https://www.statcan.gc.ca/en/developers/wds/user-guide)
- **Authentification** : le guide n'en mentionne aucune. Tous les appels POST et GET ont fonctionné sans clé (live) — [WDS User Guide](https://www.statcan.gc.ca/en/developers/wds/user-guide), [getDataFromVectorsAndLatestNPeriods](https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods)
- **Format** : JSON. Chaque point de données contient `refPer`, `refPerRaw`, `value`, `decimals`, `scalarFactorCode`, `symbolCode`, `statusCode`, `securityLevelCode`, `releaseTime`, `frequencyCode` (live) — [getDataFromVectorsAndLatestNPeriods](https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods)
- **Exemples d'appels vérifiés** :
  - POST `getDataFromVectorsAndLatestNPeriods` avec `[{"vectorId":41690973,"latestN":2}]` renvoie IPC 2026-08 = 169,8 (releaseTime 2026-09-14T08:30) et 2026-09 = 170,0 (releaseTime 2026-10-19T08:30) — [endpoint](https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods)
  - GET `getDataFromVectorByReferencePeriodRange?vectorIds="65201210"&startRefPeriod=2026-01-01&endReferencePeriod=2026-03-01` — [endpoint](https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorByReferencePeriodRange?vectorIds=%2265201210%22&startRefPeriod=2026-01-01&endReferencePeriod=2026-03-01)
  - GET `getChangedCubeList/2026-11-13` liste les tableaux diffusés ce jour-là avec leur `releaseTime` (p. ex. 10-10-0139, 10-10-0132, 10-10-0145) — [endpoint](https://www150.statcan.gc.ca/t1/wds/rest/getChangedCubeList/2026-11-13)
  - GET `getFullTableDownloadCSV/18100004/en` renvoie `https://www150.statcan.gc.ca/n1/tbl/csv/18100004-eng.zip` ; `getFullTableDownloadSDMX/18100004` renvoie `.../n1/tbl/sdmx/18100004-SDMX.zip` — [endpoint CSV](https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/18100004/en), [endpoint SDMX](https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadSDMX/18100004)
- **En-têtes HTTP observés** : `Cache-Control: max-age=1800`, `Access-Control-Allow-Origin: *`, serveur nginx (live) — [getDataFromVectorsAndLatestNPeriods](https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods)
- **Couverture** : 8 282 tableaux, actifs et archivés. Exemples de profondeur (live, getCubeMetadata) : 14-10-0287 (EPA) de 1976-01 à 2026-10 ; 18-10-0256 (IPC de base) de 1949-01 à 2026-09 ; 12-10-0011 (commerce) de 1997-01 à 2026-09 ; 34-10-0158 (mises en chantier) de 1990-01 à 2026-09 — [getCubeMetadata](https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata)
- **Licence** : Licence ouverte de Statistique Canada (modifiée le 2025-07-10). Licence « worldwide, royalty-free, non-exclusive » pour « use, reproduce, publish, freely distribute, or sell the Information » et les « Value-added Products », avec droit de sous-licence. Obligations : reproduire fidèlement, ne pas suggérer d'endossement, ne pas tenter de réidentifier. **Mention obligatoire** : « Source: Statistics Canada, name of product, reference date. Reproduced and distributed on an "as is" basis with the permission of Statistics Canada. » ; pour un produit à valeur ajoutée : « Adapted from Statistics Canada, name of product, reference date. This does not constitute an endorsement by Statistics Canada of this product. » Interdiction d'utiliser le nom, les logos ou le mot-symbole Canada sans autorisation — [StatCan Open Licence](https://www.statcan.gc.ca/en/terms-conditions/open-licence)

#### Fiche 3 — Statistique Canada, SDMX REST
- **Points d'entrée** : `.../t1/wds/sdmx/statcan/rest/data/DF_{PID}/{clé}` et `.../rest/vector/v{vectorId}` ; paramètres `startPeriod`, `endPeriod`, `firstNObservations`, `lastNObservations`, `detail` — [SDMX User Guide](https://www.statcan.gc.ca/en/developers/sdmx/user-guide)
- **Formats négociés par l'en-tête Accept** : SDMX-ML 2.1 Generic (par défaut), Structure Specific, SDMX-JSON (`application/vnd.sdmx.data+json;version=1.0.0-wd`), CSV (`text/csv`) — [SDMX User Guide](https://www.statcan.gc.ca/en/developers/sdmx/user-guide)
- **Vérifié** : `rest/data/DF_18100004/2.2?lastNObservations=2` renvoie du SDMX-ML avec l'attribut `VECTOR_ID=41690973` et les observations 2026-08 = 169,8 et 2026-09 = 170,0. `rest/vector/v41690973` avec l'en-tête SDMX-JSON exact renvoie du JSON. Avec `Accept: text/csv`, j'ai obtenu une réponse vide (live) — [SDMX data](https://www150.statcan.gc.ca/t1/wds/sdmx/statcan/rest/data/DF_18100004/2.2?lastNObservations=2), [SDMX vector](https://www150.statcan.gc.ca/t1/wds/sdmx/statcan/rest/vector/v41690973?lastNObservations=1)
- Le guide WDS ne documente que le téléchargement SDMX de tableaux complets (`getFullTableDownloadSDMX`), sans requête REST SDMX — [WDS User Guide](https://www.statcan.gc.ca/en/developers/wds/user-guide)
- **Licence** : la même que WDS (Licence ouverte de StatCan) — [StatCan Open Licence](https://www.statcan.gc.ca/en/terms-conditions/open-licence)

#### Fiche 4 — StatCan Delta File
- **URL** : `https://www150.statcan.gc.ca/n1/delta/YYYYMMDD.zip`. Le fichier du 20261113 a répondu 200 avec `application/zip`, et le format `2026-11-13.zip` a répondu 404 (live) — [Delta 20261113](https://www150.statcan.gc.ca/n1/delta/20261113.zip)
- Contenu : « all data and metadata released by Statistics Canada each business day » ; guide dédié — [Delta File page](https://www.statcan.gc.ca/en/developers/df)
- **Rétention observée** (live) : les fichiers du 2026-09-08 au 2026-11-13 sont disponibles. Ceux du 2026-09-04, du 2026-09-01 et d'avant (y compris 2025 et 2026-08) renvoient 404. C'est une fenêtre glissante d'environ 2 mois **observée**, pas documentée — [Delta 20260908](https://www150.statcan.gc.ca/n1/delta/20260908.zip)

#### Fiche 5 — Portail du gouvernement ouvert (CKAN), open.canada.ca
- **URL de base** : `https://open.canada.ca/data/api/3/action/` (CKAN Action API : `package_search`, `package_show`, `organization_show`, `datastore_search`). Lecture sans clé (live). `Cache-Control: public, max-age=30` (live) — [package_search](https://open.canada.ca/data/api/3/action/package_search?q=fiscal%20monitor&rows=0), [help_show](https://open.canada.ca/data/api/3/action/help_show?name=package_search)
- **DataStore** : certaines ressources ont `datastore_active=True`. Exemple OSFI « M4 – Consolidated Balance Sheet » (resource_id `d0f6040e-671c-4301-a235-e9e7ba164604`) : `datastore_search` renvoie **1 571 487 lignes**, dont la plus récente est datée 2026-09-30 (live) — [datastore_search](https://open.canada.ca/data/api/3/action/datastore_search?resource_id=d0f6040e-671c-4301-a235-e9e7ba164604&limit=2)
- **Licence** : la plupart des jeux concernés portent `license_id = ca-ogl-lgo` (live). C'est l'OGL–Canada **version 2.0** : licence « worldwide, royalty-free, perpetual, non-exclusive… including for commercial purposes » ; « Copy, modify, publish, translate, adapt, distribute ». Attribution obligatoire, et à défaut d'une mention propre au fournisseur : « Contains information licensed under the Open Government Licence – Canada. » Exemptions : renseignements personnels, droits de tiers, logos et symboles officiels — [OGL–Canada 2.0](https://open.canada.ca/en/open-government-licence-canada)

#### Fiche 6 — Finances Canada : Revue financière et Tableaux de référence financiers
- **Revue financière (Fiscal Monitor)** : un jeu CKAN par année. Le jeu 2026 contient, pour chaque mois, une page HTML EN/FR et un ZIP « Data tables and charts » ; dernière ressource : **juillet 2026**, ajoutée le 2026-10-06 ; « April and May 2026 » est combiné ; licence OGL (live) — [CKAN Fiscal Monitor 2026](https://open.canada.ca/data/api/3/action/package_show?id=f5f4327b-2a09-484a-a518-64ca26405386)
- Les ZIP suivent le modèle `https://open.canada.ca/data/dataset/f5f4327b-.../resource/.../download/2026-07.zip` (live) — [CKAN Fiscal Monitor 2026](https://open.canada.ca/data/api/3/action/package_show?id=f5f4327b-2a09-484a-a518-64ca26405386)
- **Tableaux de référence financiers** : l'édition « Fiscal Reference Tables November 2026 » existe (titre vérifié en direct), ainsi que le « Annual Financial Report… Fiscal Year 2025-2026 » — [FRT 2026](https://www.canada.ca/en/department-finance/services/publications/fiscal-reference-tables/2026.html), [AFR 2026](https://www.canada.ca/en/department-finance/services/publications/annual-financial-report/2026.html). L'édition de novembre 2025 couvre la situation financière des administrations fédérale, provinciales-territoriales et locales, en 9 parties ; parution le 7 novembre 2025 (extrait de recherche) — [FRT 2025](https://www.canada.ca/en/department-finance/services/publications/fiscal-reference-tables/2025.html)
- CKAN contient d'anciennes éditions avec CSV (p. ex. octobre 2018, septembre 2017 en CSV/XLSX), mais je n'y ai trouvé aucune édition 2024–2026 (live) — [CKAN FRT](https://open.canada.ca/data/api/3/action/package_search?q=title:%22fiscal%20reference%20tables%22)

#### Fiche 7 — BSIF/OSFI (FINDAT sur le gouvernement ouvert)
- Jeux publiés : Banks (M4 bilan consolidé, P3 état des résultats, BA/BCAR capital, E3 pertes de crédit attendues, LR levier), Foreign bank branches, Trust, Loan, Life (LICAT, LF1), P&C (PC1), et « Who we regulate ». Les données mensuelles paraissent **le 15 de chaque mois**, les trimestrielles fin mai, août, novembre et mars. Chaque jeu a un dictionnaire, un manuel et un guide API (PDF). Page modifiée le 2026-07-28 — [OSFI – Working with Open Government data](https://www.osfi-bsif.gc.ca/en/data-forms/open-government-osfi-financial-data/working-open-government-data)
- Le jeu Banks a la fréquence `P1M` et ses ressources CSV sont actives dans le DataStore (live) — [CKAN OSFI Banks](https://open.canada.ca/data/api/3/action/package_show?id=91ed76b4-a1a2-4f87-9c4c-59cd64f7a9de)
- La plateforme FINDAT héritée devait être mise hors ligne le **4 septembre 2026** (selon un extrait de recherche d'une page OSFI, non relu en entier) — [OSFI temporary measures](https://www.osfi-bsif.gc.ca/index%2Ephp/en/data-forms/open-government-osfi-financial-data/temporary-measures-ease-transition-open-government)

#### Fiche 8 — SCHL/CMHC
- 37 jeux CKAN `cmhc-schl` (CSV, XML, HTML ; OGL), p. ex. « Housing starts, all areas, Canada and provinces », « Housing starts, all areas, seasonally adjusted at annual rates », « Average rents… », métadonnées modifiées le 2026-09-16 (live) — [CKAN cmhc-schl](https://open.canada.ca/data/api/3/action/package_search?q=organization:cmhc-schl)
- Équivalent StatCan avec releaseTime : tableau 34-10-0158 « Canada Mortgage and Housing Corporation, housing starts, all areas, Canada and provinces, seasonally adjusted at annual rates, monthly », de 1990-01 à 2026-09, releaseTime 2026-10-19 (live) — [getCubeMetadata](https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata)
- HMIP : le paquet R `cmhc` (v0.2.12, 2026) interroge un point non documenté, `POST https://www03.cmhc-schl.gc.ca/hmip-pimh/en/TableMapChart/ExportTable` — [cmhc R source](https://github.com/mountainMath/cmhc/blob/master/R/cmhc.R)
- Calendrier 2026 de la SCHL : mises en chantier mensuelles, dernière diffusion de 2026 le 15 décembre (extrait de recherche) — [CMHC release calendar](https://www.cmhc-schl.gc.ca/en/professionals/housing-markets-data-and-research/market-reports/news-releases-reports-calendar)
- Selon la documentation du paquet R, les produits sous licence utilisant des données de la SCHL doivent porter une mention de source (SCHL, nom du produit, date de référence) — [cmhc README (CRAN mirror)](https://ftp.fau.de/cran/web/packages/cmhc/readme/README.html)

#### Fiche 9 — Énergie : REC/CER, CCIE/CCEI, RNCan/NRCan
- REC/CER : 85 jeux CKAN (OGL), p. ex. « Natural Gas – Exports », « Liquefied Natural Gas – Exports », mis à jour le 2026-11-13 (live) — [CKAN cer-rec](https://open.canada.ca/data/api/3/action/package_search?q=organization:cer-rec)
- Fichiers CSV directs de l'Avenir énergétique **2026** : `benchmark-prices-2026.csv`, colonnes « Scenario, Variable, Year, Value » (p. ex. « Canada Net-zero », « Brent – US$/bbl ») (live) — [CER benchmark prices 2026](https://www.cer-rec.gc.ca/open/energy/energyfutures2026/benchmark-prices-2026.csv)
- CCEI : API SDMX (voir Q1) ; outil d'électricité à haute fréquence avec lien API — [CCEI high-frequency electricity](https://energy-information.canada.ca/en/resources/high-frequency-electricity-data)
- RNCan : sur CKAN, surtout des jeux techniques (p. ex. « Fuel consumption ratings », mis à jour le 2026-10-18) ; peu de séries macro (live) — [CKAN nrcan](https://open.canada.ca/data/api/3/action/package_search?q=organization:nrcan-rncan%20AND%20title:fuel)

#### Fiche 10 — ISDE/ISED
- Organisation CKAN `ic` : « Historic Insolvency Statistics – Monthly (from 1987) » (XLSX), « Monthly Insolvency Statistics… by NAICS » et « …by Forward Sortation Area », mis à jour le 2026-10-08, OGL (live) — [CKAN insolvency](https://open.canada.ca/data/api/3/action/package_search?q=insolvency%20statistics)

#### Fiche 11 — Provinces
- **Ontario** : CKAN `https://data.ontario.ca/api/3/action/`, 2 967 jeux. Licences OGL-ON-1.0 ou `ontario.ca-tou` selon le jeu. « Ontario's fiscal and economic indicators » n'a plus été modifié depuis 2021-01-14 (périmé) ; « Public Accounts: Annual report » modifié le 2026-09-24 (live) — [data.ontario.ca package_search](https://data.ontario.ca/api/3/action/package_search?q=fiscal)
- **Colombie-Britannique** : CKAN `https://catalogue.data.gov.bc.ca/api/3/action/`, 3 364 jeux. Jeux BC Stats et Treasury Board, p. ex. « Fall 2024 Economic & Fiscal Update (Q2) » modifié le 2025-05-02, `license_id = 2` (live) — [BC catalogue package_search](https://catalogue.data.gov.bc.ca/api/3/action/package_search?q=fiscal)
- **Alberta** : CKAN `https://open.alberta.ca/api/3/action/`, 37 650 jeux, licence OGLA. « Alberta Activity Index data table » modifié le 2026-10-30, plus l'API JSON sans clé du tableau de bord (fiche Q1) (live) — [open.alberta.ca package_search](https://open.alberta.ca/api/3/action/package_search?q=economic)
- **Québec** : CKAN Données Québec `https://www.donneesquebec.ca/recherche/api/3/action/`, 1 619 jeux. L'organisation `isq` (Institut de la statistique du Québec) n'a que **7 jeux**, surtout géographiques (codes postaux, géographie du recensement harmonisée), sous `cc-by` (live) — [Données Québec organization_list](https://www.donneesquebec.ca/recherche/api/3/action/organization_list?all_fields=true&limit=200)
- La recherche n'a fait ressortir aucune API de l'ISQ. Les ressources trouvées sont la Banque de données des statistiques officielles sur le Québec (BDSO) et des pages de données de l'ISQ, sans documentation d'API — [ISQ données](https://statistique.quebec.ca/fr/services-recherche/donnees), [HEC – BDSO](https://www.hec.ca/biblio/banques-de-donnees/banque-donnees-statistiques-officielles.html)

#### Fiche 12 — ACI/CREA (MLS® HPI)
- Pas d'API. Téléchargement XLSX via l'outil HPI. Selon des extraits des conditions d'utilisation de l'ACI : « Any commercial use of the Content in whole or in part… is specifically forbidden except with the prior written authority of CREA », avec téléchargement autorisé « to conduct analyses, to generate graphs and charts, and in the reporting of results » (extraits de recherche, non relus en entier) — [CREA MLS HPI](https://www.crea.ca/housing-market-stats/mls-home-price-index/), [CREA reference materials](https://crea.ca/housing-market-stats/mls-home-price-index/resources)

### Inferences
- **Redistribution dans la base de connaissances OKF** : StatCan (Licence ouverte), OGL–Canada (Finances, OSFI, SCHL sur CKAN, REC, ISDE) et la BdC permettent la redistribution, y compris publique, si l'on fournit l'attribution. Gabarits YAML suggérés :
  - `licence: "Statistics Canada Open Licence"` et `attribution: "Source: Statistics Canada, Table 18-10-0004-01, <date de référence>. Reproduced and distributed on an 'as is' basis with the permission of Statistics Canada."`
  - `licence: "OGL-Canada-2.0"` et `attribution: "Contains information licensed under the Open Government Licence – Canada."`
  - `licence: "Bank of Canada Terms of Use"` et `attribution: "Source: Bank of Canada (Valet API), <série>; modifications: <...>"`.
- Pour les séries IPC servies par Valet, la donnée d'origine vient de StatCan (contenu de tiers au sens de l'article 2.3 des conditions de la BdC). Il est plus sûr de **citer StatCan et la BdC** dans les deux cas, ou de prendre l'IPC directement dans WDS.
- Les données de l'ACI/CREA ne devraient **pas** être redistribuées dans la base partagée (usage commercial interdit sans permission). Au mieux, on peut stocker des agrégats dérivés pour analyse interne, ou s'en passer au profit du NHPI de StatCan (v111955442) et des tableaux de la SCHL.
- Le débit de 25 req/s par IP de WDS est très au-delà des besoins de l'agent A5. Le vrai risque est la fenêtre de verrouillage minuit–8 h 30 HE (codes 409), qu'il faut prévoir dans l'ordonnanceur.

### Gaps
- Valet : la Banque ne publie aucune limite chiffrée (requêtes/s, taille de réponse).
- CKAN open.canada.ca : je n'ai pas trouvé de limite de débit documentée. La page de documentation de l'API du portail n'a pas été relue.
- WDS : nombre maximal de vecteurs ou de points par requête non chiffré dans le guide.
- `license_id = 2` du catalogue de la C.-B. : je n'ai pas vérifié s'il correspond à l'Open Government Licence – British Columbia.
- Licences de l'ISQ (hors CC-BY sur Données Québec), de l'HMIP de la SCHL (hors miroirs OGL) et de Paiements Canada : textes non relus.
- La date d'arrêt de FINDAT (4 septembre 2026) ne vient que d'un extrait de recherche.

---

## Q3. Capacité « point-in-time » : dates de publication, millésimes, historique des révisions, valeur telle que publiée initialement

### Takeaway
- **Aucune des API ne fournit nativement la valeur « telle que publiée initialement » pour toutes les séries.**
- Dans **WDS**, `releaseTime` est l'horodatage de la **dernière** diffusion du point : il est **écrasé à chaque révision** (démontré en direct ci-dessous).
- **Valet** ne renvoie que la date de référence et la valeur, sans date de publication ni millésime.
- Trois mécanismes officiels existent pour reconstituer le point-in-time :
  1. Les **19 tableaux « temps réel » de StatCan**, avec une dimension « Release » (PIB mensuel 36-10-0491, PIB en dépenses 36-10-0431, commerce 12-10-0165, IPC de base 18-10-0259, etc.).
  2. Les **groupes Valet par édition** (RPM `MPR_YYYYMmm_*`, EPE `BOS_YYYYQn_*`, CSCE, projections du personnel `SWP-*`).
  3. L'**archivage prospectif** par A5 du Delta File et des réponses WDS et Valet, avec la date de collecte.
- Le **calendrier JSON** de StatCan donne les dates de publication futures et passées des indicateurs clés.

### Cited Findings
- `releaseTime` est défini comme « Release Time (8:30 EST) – which is the only Statistics Canada release time, unless there is a correction » ; les valeurs révisées portent `symbolCode` « r » et les provisoires « p » ; des champs de correction existent au niveau du tableau — [WDS User Guide](https://www.statcan.gc.ca/en/developers/wds/user-guide)
- `issueDate` « represents the first time a cube is published » ; c'est une donnée **au niveau du tableau**, pas du point — [WDS User Guide](https://www.statcan.gc.ca/en/developers/wds/user-guide)
- **Preuve en direct de l'écrasement** : pour v65201210 (PIB mensuel), **tous** les points de 2025-01 à 2026-08 portent `releaseTime = 2026-10-30T08:30` (diffusion du PIB d'août, avec révisions), et non leur date de première publication. Exemple : 2026-01 vaut 2 339 783 avec un releaseTime au 2026-10-30 — [getDataFromVectorByReferencePeriodRange](https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorByReferencePeriodRange?vectorIds=%2265201210%22&startRefPeriod=2026-01-01&endReferencePeriod=2026-03-01)
- `getBulkVectorDataByRange` (POST `{"vectorIds":[...],"startDataPointReleaseDate":"...","endDataPointReleaseDate":"..."}`) filtre selon la **date de diffusion du point**. Pour la fenêtre 2026-10-01 à 2026-11-14, il renvoie l'IPC 2026-09 et **toute** la série PIB depuis 2025-01, puisque tout a été révisé le 2026-10-30 (live) — [getBulkVectorDataByRange](https://www150.statcan.gc.ca/t1/wds/rest/getBulkVectorDataByRange)
- `getChangedSeriesList` liste les séries mises à jour à 8 h 30 le jour de diffusion, « available until midnight that day ». Un samedi, l'appel renvoie `{"message":"The product is not released yet"}` (live) — [WDS User Guide](https://www.statcan.gc.ca/en/developers/wds/user-guide), [getChangedSeriesList](https://www150.statcan.gc.ca/t1/wds/rest/getChangedSeriesList)
- `getChangedCubeList/{date}` accepte « any date from today backward », ce qui permet de reconstituer l'historique des diffusions par tableau, mais pas les valeurs — [WDS User Guide](https://www.statcan.gc.ca/en/developers/wds/user-guide), [getChangedCubeList/2026-11-13](https://www150.statcan.gc.ca/t1/wds/rest/getChangedCubeList/2026-11-13)
- **Tableaux temps réel de StatCan** : « Data tables that provide the revision history of 19 economic and social time series » ; « vintages of data as of January 2015, some are expanded » ; « released approximately one week after the official release of the source data tables » (page modifiée le 2025-12-16) — [Real-time data tables](https://www.statcan.gc.ca/en/dai/btd/rct)
- Les 19 paires (tableau régulier → tableau temps réel) — [Real-time data tables](https://www.statcan.gc.ca/en/dai/btd/rct) :
  - 12-10-0163 → **12-10-0165** (commerce de marchandises, base douanière et BdP)
  - 16-10-0013 → 16-10-0014 ; 16-10-0012 → 16-10-0015 ; 16-10-0047 → 16-10-0118 ; 16-10-0048 → 16-10-0119 (fabrication)
  - 20-10-0003 → 20-10-0005 ; 20-10-0074 → 20-10-0019 ; 20-10-0076 → 20-10-0020 (commerce de gros)
  - 18-10-0256 → **18-10-0259** (IPC de base, définitions de la BdC)
  - 20-10-0056 → **20-10-0081** (ventes au détail) ; 20-10-0067 → 20-10-0082
  - 14-10-0220 → 14-10-0331 ; 14-10-0223 → 14-10-0332 (EERH, emploi et rémunération)
  - 36-10-0434 → **36-10-0491** (PIB mensuel par industrie)
  - 36-10-0018 → 36-10-0042 (compte courant)
  - 36-10-0103 → 36-10-0430 (PIB en revenus) ; 36-10-0104 → **36-10-0431** (PIB en dépenses)
  - 34-10-0035 → 34-10-0278 ; 34-10-0036 → 34-10-0279 (dépenses en immobilisations)
- **État en direct des tableaux temps réel** (getCubeMetadata, 2026-11-14) — [getCubeMetadata](https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata) :
  - 36-10-0491 : ACTIF, données jusqu'à 2026-08, releaseTime 2026-11-09, dimension **« Release » à 141 membres** (du plus récent au plus ancien, jusqu'au « March 03, 2015 »), 120 609 séries.
  - 36-10-0431 : ACTIF, jusqu'au T2 2026 (cubeEndDate 2026-04-01), releaseTime 2026-09-10, 56 millésimes (le plus ancien : « November 30, 2012 »).
  - 12-10-0165 : ACTIF, jusqu'à 2026-08, releaseTime 2026-10-19, 35 millésimes (le plus ancien : « December 06, 2023 »).
  - 18-10-0259 (IPC de base) : ACTIF mais **en retard**, données jusqu'à 2026-03 seulement, releaseTime 2026-05-04, 113 millésimes (le plus ancien : « December 22, 2016 »).
  - 20-10-0081 (détail) : **ARCHIVÉ (« inactive »)**, données jusqu'à 2025-12, dernière diffusion le 2026-03-02.
- Dans les tableaux temps réel, la première valeur publiée pour une période de référence est la dernière valeur non manquante de sa colonne de millésime (extrait de recherche résumant la page StatCan) — [Real-time data tables](https://www.statcan.gc.ca/eng/dai/btd/rct)
- **Calendrier JSON** : objets `{date, type, title, description, url}` ; « every release date of major economic indicators since March 14, 2012 », y compris les dates futures (live) — [schedule JSON doc](https://www.statcan.gc.ca/en/developers/schedule-key_indicators-eng-json), [schedule JSON](https://www150.statcan.gc.ca/n1/dai-quo/ssi/homepage/schedule-key_indicators-eng.json)
- **Valet** : les observations ne contiennent que `{"d": "<date de référence>", "<série>": {"v": "<valeur>"}}`, sans date de publication (live) — [observations CPI](https://www.bankofcanada.ca/valet/observations/CPI_TRIM,CPI_MEDIAN,CPI_COMMON,V41690973/json?recent=2)
- Exemples de décalage dans Valet : l'EPE (`BOS_ACTIVITY_INDICATOR`) est datée 2026-07-01 pour le T3, et l'IPC est daté au 1er du mois de référence (2026-09-01), alors que StatCan l'a publié le 2026-10-19 (live) — [observations BOS](https://www.bankofcanada.ca/valet/observations/BOS_ACTIVITY_INDICATOR/json?recent=1), [WDS IPC](https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods)
- **Millésimes BdC disponibles par construction** :
  - groupes RPM par édition (`MPR_2024M04_*` à `MPR_2026M10_*`) ;
  - EPE et CSCE par trimestre (`BOS_2026Q3_*`, `CSCE_2026Q3_*`) ;
  - projections du personnel `SWP-<VAR><YYYYQn>`, qui contiennent l'historique tel que connu à ce moment plus la projection (p. ex. `SWP-GDP2019Q4`, de 1980 à 2021T4) ; dernier millésime disponible : 2019T4 (live).

  Sources : [Valet lists/groups](https://www.bankofcanada.ca/valet/lists/groups/json), [SWP-GDP2019Q4](https://www.bankofcanada.ca/valet/observations/SWP-GDP2019Q4/json)
- `CORRA_TRANSPARENCY` = « CORRA: summary of errors detected after publication » : c'est la seule trace explicite de révision d'un taux BdC trouvée dans Valet (live) — [Valet lists/groups](https://www.bankofcanada.ca/valet/lists/groups/json)
- Le Delta File contient tout ce qui a été diffusé un jour ouvrable donné, mais la fenêtre observée n'est que d'environ 2 mois (Q2, fiche 4) — [Delta File page](https://www.statcan.gc.ca/en/developers/df)
- CKAN : les dates `metadata_modified` et `last_modified` sont celles de l'ajout au catalogue. Par exemple, les ZIP de janvier à mars 2026 de la Revue financière ont tous été ajoutés le 2026-06-15 (live). Ce ne sont donc **pas** des dates de publication — [CKAN Fiscal Monitor 2026](https://open.canada.ca/data/api/3/action/package_show?id=f5f4327b-2a09-484a-a518-64ca26405386)

### Inferences
- **Recette pour A5** (date d'observation ≠ date de publication, sans anticipation) :
  1. `observation_date` = `refPer` (WDS) ou `d` (Valet).
  2. `publication_date` = la date du calendrier JSON StatCan pour l'indicateur et la période. À défaut, le `releaseTime` WDS **uniquement s'il n'y a pas eu de révision**. Pour les taux de marché BdC : jour ouvrable + 16 h 30 HE (change) ou J+1 par prudence (rendements : la dernière observation datée du 2026-11-12 était encore la plus récente le 2026-11-14 au soir, ce qui suggère une publication décalée ; non documenté).
  3. `vintage_id` = le membre « Release » du tableau temps réel, ou la date de collecte par A5.
  4. `first_release_value` = la valeur tirée du tableau temps réel (PIB, commerce, IPC de base, EERH, etc.). Pour les séries sans tableau temps réel (EPA, IPC global, mises en chantier), il faut **archiver soi-même** chaque jour (Delta File ou snapshot WDS horodaté) à partir de maintenant.
- L'IPC global non désaisonnalisé (v41690973) n'est pratiquement jamais révisé, alors que l'IPC désaisonnalisé, l'EPA désaisonnalisée (révisions saisonnières annuelles) et le PIB le sont. Les risques d'anticipation sont donc surtout sur le PIB, le commerce, le détail et l'EPA. Ce point vient de ma connaissance générale des pratiques de StatCan, non vérifiée dans cette session.
- Pour les simulations historiques avant 2015 (date de début des tableaux temps réel), les projections `SWP-*` de la BdC offrent une approximation du savoir de l'époque pour le PIB, l'IPC et le chômage. Leur rythme de publication est en retard : dernier millésime 2019T4 au 2026-11-14.

### Gaps
- Je n'ai pas vérifié si StatCan prévoit de rattraper ou de remplacer 18-10-0259 (IPC de base en retard) et 20-10-0081 (détail archivé).
- Valet n'expose aucune information de révision (hors CORRA_TRANSPARENCY). La politique de révision des séries BdC (p. ex. rendements, IPPB) n'est pas documentée dans les pages lues.
- La rétention du Delta File n'est pas documentée (seulement observée).
- Le champ `date` du calendrier JSON porte des heures factices (« 00:00:01 », « 00:00:02 »), qui semblent servir à l'ordre de tri plutôt qu'à l'heure réelle (8 h 30 HE) ; c'est une inférence non confirmée.

---

## Q4. Clients Python officiels ou bien maintenus, et serveurs MCP

### Takeaway
Ni la BdC ni StatCan ne publient de client officiel. Côté StatCan, `stats_can` (Ian Preston, GPL-3.0) est mûr et actif : v3.3.0 le 2026-09-25. Côté SDMX générique, `sdmx1` inclut une source « StatCan ». Pour Valet, `pyvalet` est ancien (v1.1.1, janvier 2024) et un client maison de quelques dizaines de lignes suffit. Plusieurs serveurs MCP **communautaires** existent (le plus suivi : ReyemTech/mcp-canada, MIT, 62 étoiles, modules BdC, StatCan, CKAN et provinces), mais aucun n'est officiel.

### Cited Findings
- `stats-can` / `stats_can` : version 3.3.0 du 2026-09-25, « Read StatsCan data into python, mostly pandas dataframes », documentation sur stats-can.readthedocs.io, versions récentes 3.1.0 → 3.3.0 — [PyPI stats-can](https://pypi.org/project/stats-can/), [docs](https://stats-can.readthedocs.io)
- Dépôt ianepreston/stats_can : 78 étoiles, GPL-3.0, dernier push le 2026-10-26. Changements récents : #633 (2026-04-29) « Implement get_series_info_from_cube_pid_coord », #631-632 (2026-04) correctifs du modèle pydantic des métadonnées — [GitHub stats_can](https://github.com/ianepreston/stats_can), [issues](https://github.com/ianepreston/stats_can/issues)
- `pyvalet` : version 1.1.1 du 2024-01-31, « BoC Valet API Wrapper », aucune URL de projet sur PyPI — [PyPI pyvalet](https://pypi.org/project/pyvalet/)
- `sdmx1` : version 2.28.0 du 2026-10-18. Son `sources.json` compte 36 sources, dont **`StatCan`** (ainsi que ECB, IMF, OECD, BIS, etc.) — [PyPI sdmx1](https://pypi.org/project/sdmx1/), [sources.json](https://raw.githubusercontent.com/khaeru/sdmx/main/sdmx/sources.json)
- `pandasdmx` : dernière version 1.10.0 du 2023-02-25 (inactif) — [PyPI pandasdmx](https://pypi.org/project/pandasdmx/)
- `ckanapi` : version 4.11 du 2026-03-20, client officiel du projet CKAN, utilisable pour open.canada.ca et les portails provinciaux — [PyPI ckanapi](https://pypi.org/project/ckanapi/)
- Côté R (utile comme référence d'implémentation) : `cmhc` (mountainMath, v0.2.12 en 2026, 30 étoiles, push le 2026-07-21) et le miroir CRAN de `valet` — [mountainMath/cmhc](https://github.com/mountainMath/cmhc), [cran/valet](https://github.com/cran/valet)
- **Serveurs MCP (communautaires)** :
  - **ReyemTech/mcp-canada** : MIT, 62 étoiles, créé le 2026-04-06, push le 2026-10-22, Python. « 295 tools… across 9 federal APIs + 9 provincial APIs + 2 municipal ». Modules Bank of Canada (8 outils, Valet), CKAN Open Data (7), Statistics Canada (15, « Time series, cube metadata, SDMX filtering »), Ontario, Québec (Données Québec), C.-B., Alberta. Enveloppe de réponse avec `_meta` (attribution de la source, statut du cache). Installation : `uvx mcp-canada install` — [GitHub ReyemTech/mcp-canada](https://github.com/ReyemTech/mcp-canada)
  - **Aryan-Jhaveri/mcp-statcan** : MIT, 8 étoiles, créé le 2025-04-07, push le 2026-11-06, « MCP server + CLI for Statistics Canada… via WDS » — [GitHub](https://github.com/Aryan-Jhaveri/mcp-statcan)
  - **dsanchezp18/maplestats-mcp** : 6 étoiles, « StatCan, Census, PUMFs, Bank of Canada, CMHC… », push le 2026-11-15 — [GitHub](https://github.com/dsanchezp18/maplestats-mcp)
  - **pipeworx-io** : mcp-bank-of-canada (« Keyless »), mcp-statcan, mcp-opendata-canada (CKAN), 0 à 1 étoile — [mcp-bank-of-canada](https://github.com/pipeworx-io/mcp-bank-of-canada), [mcp-statcan](https://github.com/pipeworx-io/mcp-statcan), [mcp-opendata-canada](https://github.com/pipeworx-io/mcp-opendata-canada)
  - **hemaaanth/statcan2** : « Every Statistics Canada table, charted. Open data API and MCP server » (0 étoile) — [GitHub](https://github.com/hemaaanth/statcan2)
  - Résultats de recherche de dépôts GitHub en date du 2026-11-14 — [GitHub search](https://github.com/search?q=statcan+mcp&type=repositories)

### Inferences
- Pour un projet de datathon soumis à des exigences de traçabilité, un **client maison minimal** est préférable : `httpx` + retry/back-off, Valet sur `/observations/{series}/json`, WDS en POST `getDataFromVectorsAndLatestNPeriods`, `getCubeMetadata`, `getBulkVectorDataByRange` et le JSON de calendrier. Le code est plus simple à auditer et chaque appel peut journaliser l'URL, l'horodatage de collecte et la licence dans le YAML OKF.
- `stats_can` peut accélérer le prototypage (téléchargement de tableaux complets, métadonnées), mais sa licence GPL-3.0 est contaminante si le code est redistribué. À évaluer si le monolithe AlphaForge est publié.
- `mcp-canada` (MIT) peut servir d'inspiration ou d'outil d'exploration pour l'agent, mais il ne gère pas, à ma connaissance, le point-in-time (non vérifié). Il ne remplace pas la couche d'ingestion versionnée.

### Gaps
- Je n'ai pas audité le code des serveurs MCP (qualité, gestion des millésimes, limites).
- Je n'ai pas vérifié si `pyvalet` fonctionne encore avec la spec Valet 1.0.1 (endpoints `/search` ajoutés).

---

## Q5. Pièges connus 2025–2026 (changements d'endpoints, dépréciations, pannes, blocage d'IP cloud)

### Takeaway
Je n'ai trouvé **aucune preuve** de blocage d'IP cloud ou de rupture d'endpoint majeure pour Valet ou WDS en 2025–2026. Les pièges concrets sont ailleurs :
- `releaseTime` est écrasé par les révisions ;
- WDS a une fenêtre de verrouillage minuit–8 h 30 HE (409) ;
- les fuseaux horaires sont incohérents entre méthodes WDS ;
- Valet ne publie pas de date de publication et ajoute un délai de traitement ;
- certains tableaux temps réel sont en retard ou archivés ;
- le Delta File n'est conservé qu'environ 2 mois ;
- FINDAT de l'OSFI a été migré vers le gouvernement ouvert ;
- l'HMIP de la SCHL n'est accessible que par un endpoint non documenté ;
- les métadonnées CKAN sont décalées par rapport aux publications réelles.

### Cited Findings
- WDS : les codes 409 sont possibles de minuit à 8 h 30 HE pendant les mises à jour — [WDS User Guide](https://www.statcan.gc.ca/en/developers/wds/user-guide)
- **Fuseaux horaires incohérents (live)** : `getAllCubesListLite` renvoie `"releaseTime": "2012-08-01T12:30:00Z"` (UTC, suffixe Z), alors que les points de données renvoient `"releaseTime": "2026-10-19T08:30"` (heure de l'Est, sans décalage) — [getAllCubesListLite](https://www150.statcan.gc.ca/t1/wds/rest/getAllCubesListLite), [getDataFromVectorsAndLatestNPeriods](https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods). Le guide lui-même montre les deux formats dans ses exemples — [WDS User Guide](https://www.statcan.gc.ca/en/developers/wds/user-guide)
- Guide WDS v1.6 (2025-01-24) : ajout de `issueDate` et notes sur les codes d'erreur. C'est la seule évolution documentée en 2025 — [WDS User Guide](https://www.statcan.gc.ca/en/developers/wds/user-guide)
- `getSeriesInfoFromVector` renvoie un objet `null`, avec `productId 0` pour un vecteur inexistant ou terminé, au lieu d'une erreur HTTP (live : v132036, v41693242, v44200206, v108785712). Les clients doivent tester `object` ≠ null. C'est d'ailleurs ce qui a fait planter mon premier script — [getSeriesInfoFromVector](https://www150.statcan.gc.ca/t1/wds/rest/getSeriesInfoFromVector)
- Note : `ATOM_V41693242` (IPCX) existe dans Valet, mais v41693242 ne renvoie rien dans WDS (live). Les codes Valet de type « V… » ne sont donc pas toujours des vecteurs StatCan valides — [Valet groups/CPI_MONTHLY](https://www.bankofcanada.ca/valet/groups/CPI_MONTHLY/json), [getSeriesInfoFromVector](https://www150.statcan.gc.ca/t1/wds/rest/getSeriesInfoFromVector)
- Valet : délai de traitement possible entre la publication et l'arrivée dans l'API ; la BdC se réserve le droit de modifier ses certificats TLS « at any time and without notice » — [How-to guide](https://www.bankofcanada.ca/valet-api-how-to/)
- Valet : la spec actuelle est la version 1.0.1, avec de nouveaux endpoints `/search/series` et `/search/groups` paginés. Les requêtes au-delà de la dernière page renvoient 200 avec un champ `message` (et non 404) — [spec YAML](https://www.bankofcanada.ca/valet/static/swagger/api-en.yml)
- Valet : les groupes `LEGACY_NOON_RATES` et `LEGACY_CLOSING_RATES` indiquent que les anciens taux midi et de clôture sont des séries héritées distinctes de `FX_RATES_DAILY` (live). Il faut les traiter comme une rupture de série — [Valet lists/groups](https://www.bankofcanada.ca/valet/lists/groups/json)
- Un groupe nommé `DELETE_ME` (« delete ») apparaît dans la liste publique des groupes (live). Il faut filtrer les groupes techniques — [Valet lists/groups](https://www.bankofcanada.ca/valet/lists/groups/json)
- Tableaux temps réel : 18-10-0259 a cessé d'avancer depuis mai 2026 et 20-10-0081 est archivé (live, voir Q3) — [getCubeMetadata](https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata)
- Delta File : rétention observée d'environ 2 mois (Q2, fiche 4) — [Delta File page](https://www.statcan.gc.ca/en/developers/df)
- Une vignette CRAN (cancensus) avertit que le WDS « is not a stable API » et que le serveur est parfois indisponible (extrait de recherche) — [cancensus statcan_wds vignette](https://search.r-project.org/CRAN/packages/cancensus/vignettes/statcan_wds.html)
- **Blocage d'IP cloud / User-Agent** : la recherche n'a donné aucun signalement. En test, depuis une IP non-cloud, Valet a répondu 200 avec un User-Agent vide et avec `python-requests/2.32.3`, et WDS a répondu 200 avec `python-requests` (live) — [Valet FXUSDCAD](https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=1), [WDS getCodeSets](https://www150.statcan.gc.ca/t1/wds/rest/getCodeSets)
- OSFI : migration de FINDAT vers le gouvernement ouvert, l'ancienne plateforme devant être retirée le 4 septembre 2026 (extrait de recherche). Les nouvelles données sont en CSV et dans le DataStore CKAN (live) — [OSFI Working with Open Government data](https://www.osfi-bsif.gc.ca/en/data-forms/open-government-osfi-financial-data/working-open-government-data), [CKAN OSFI Banks](https://open.canada.ca/data/api/3/action/package_show?id=91ed76b4-a1a2-4f87-9c4c-59cd64f7a9de)
- SCHL HMIP : le seul accès programmatique connu est le `POST .../hmip-pimh/en/TableMapChart/ExportTable` non documenté, utilisé par le paquet R `cmhc`, avec un timeout de 300 s dans le code. Le paquet a dû s'adapter en 2025 (ajout de la table SAAR des mises en chantier, issues #27 et #29) — [cmhc R source](https://github.com/mountainMath/cmhc/blob/master/R/cmhc.R), [cmhc issues](https://github.com/mountainMath/cmhc/issues)
- CKAN : le jeu « Ontario's fiscal and economic indicators » n'a pas été mis à jour depuis 2021-01-14, et la fréquence du jeu Revue financière 2026 est `not_planned` alors qu'il est mensuel en pratique (live) — [data.ontario.ca](https://data.ontario.ca/api/3/action/package_search?q=fiscal), [CKAN Fiscal Monitor 2026](https://open.canada.ca/data/api/3/action/package_show?id=f5f4327b-2a09-484a-a518-64ca26405386)
- Contexte de politique monétaire : le cadre a été renouvelé pour cinq ans, « from January 2027 to December 2031 ». Les métadonnées de régime (cible d'inflation) devront noter ce renouvellement — [Bank of Canada page](https://www.bankofcanada.ca/?p=201766)

### Inferences
- Il faut normaliser tous les horodatages WDS en `America/Toronto` → UTC dans le YAML OKF : `publication_datetime_utc` et `publication_datetime_local`.
- L'ordonnanceur A5 devrait éviter WDS entre 0 h et 8 h 35 HE, collecter vers 8 h 45 HE les jours de diffusion (piloté par le calendrier JSON), et collecter Valet après 17 h HE pour le change et les taux.
- Comme le blocage d'IP AWS n'est ni documenté ni testé, il faut prévoir un **test de fumée depuis l'environnement AWS du datathon** et un repli : Delta File ou ZIP CSV mis en cache dans S3.

### Gaps
- Je n'ai pas pu tester depuis une IP AWS ou cloud. Le risque de blocage reste **non vérifié**.
- Je n'ai trouvé aucun historique public de pannes de Valet ou de WDS en 2025–2026 (pas de page de statut identifiée).
- La cessation du CDOR (2024) n'a pas été vérifiée dans cette session. Seule l'absence d'un groupe CDOR dans Valet a été constatée.

---

## Q6. Séries prioritaires pour le contexte investisseur canadien (avec identifiants vérifiés)

### Takeaway
Tous les identifiants ci-dessous ont été **vérifiés en direct** via `getSeriesInfoFromVector` / `getSeriesInfoFromCubePidCoord` (StatCan) ou `groups/{name}` / `observations` (Valet) le 2026-11-14. Ils couvrent : l'inflation (globale, de base, attentes), l'activité (PIB mensuel et trimestriel), l'emploi (EPA), le logement (mises en chantier, NHPI), la consommation (détail), le commerce extérieur, les taux (directeur, CORRA, bons du Trésor, courbe GdC), le change et les produits de base.

### Cited Findings

**Statistique Canada (WDS, préfixe « v »)**, vérifiés via [getSeriesInfoFromVector](https://www150.statcan.gc.ca/t1/wds/rest/getSeriesInfoFromVector) et [getSeriesInfoFromCubePidCoord](https://www150.statcan.gc.ca/t1/wds/rest/getSeriesInfoFromCubePidCoord) :

| Thème | Vecteur | Tableau | Titre WDS (exact) | Fréq. |
|---|---|---|---|---|
| IPC global (non désais.) | v41690973 | 18-10-0004 | Canada;All-items | mensuelle |
| IPC global (désais.) | v41690914 | 18-10-0006 | Canada;All-items | mensuelle |
| IPC moyenne annuelle | v41693271 | 18-10-0005 | Canada;All-items | annuelle |
| IPC-tronq (a/a %) | v108785715 | 18-10-0256 | …trimmed mean approach, CPI-trim (year-over-year percent change) | mensuelle |
| IPC-méd (a/a %) | v108785714 | 18-10-0256 | …weighted median approach, CPI-median (year-over-year percent change) | mensuelle |
| IPC-comm (a/a %) | v108785713 | 18-10-0256 | …factor model, CPI-common (year-over-year percent change) | mensuelle |
| PIB réel mensuel, toutes industries, $ enchaînés 2017, désais. TA | v65201210 | 36-10-0434 | Canada;Seasonally adjusted at annual rates;Chained (2017) dollars;All industries | mensuelle |
| PIB réel trimestriel (dépenses), $ enchaînés 2017, désais. TA | v62305752 | 36-10-0104 | Canada;Chained (2017) dollars;Seasonally adjusted at annual rates;Gross domestic product at market prices | trimestrielle |
| Taux de chômage, 15+, désais. | v2062815 | 14-10-0287 | Canada;Unemployment rate;Total - Gender;15 years and over;Estimate;Seasonally adjusted | mensuelle |
| Emploi, 15+, désais. | v2062811 | 14-10-0287 | Canada;Employment;…;Seasonally adjusted | mensuelle |
| Population active, 15+, désais. | v2062810 | 14-10-0287 | Canada;Labour force;…;Seasonally adjusted | mensuelle |
| Chômeurs, 15+, désais. | v2062814 | 14-10-0287 | Canada;Unemployment;…;Seasonally adjusted | mensuelle |
| Taux de chômage T.-N.-L. (exemple prov.) | v2063004 | 14-10-0287 | Newfoundland and Labrador;Unemployment rate;… | mensuelle |
| Taux de chômage RMR Toronto, désais. | v1235049756 | 14-10-0383 | Toronto, Ontario;Unemployment rate;Estimate;Seasonally adjusted | mensuelle |
| Mises en chantier, Canada, désais. TA (SCHL) | v52300157 | 34-10-0158 | Canada | mensuelle |
| Ventes au détail totales, désais. | v1446859483 | 20-10-0056 | Canada;Retail trade;Total retail sales;Seasonally adjusted | mensuelle |
| **Balance commerciale** de marchandises, base BdP, désais., tous pays | v87008984 | 12-10-0011 | Canada;Trade Balance;Balance of payments;Seasonally adjusted;All countries | mensuelle |
| Exportations, base BdP, désais., tous pays | v87008955 | 12-10-0011 | Canada;Export;Balance of payments;Seasonally adjusted;All countries | mensuelle |
| Indice des prix des logements neufs (NHPI) total | v111955442 | 18-10-0205 | Canada;Total (house and land) | mensuelle |
| Population (estimation trimestrielle) | v1 | 17-10-0009 | Canada | trimestrielle |
| IPPB (BCPI) total | v52673496 | 10-10-0132 | Canada;Total, all commodities | mensuelle |
| Obligations GdC, rendement moyen 3-5 ans | v122485 | 10-10-0122 | …marketable bonds, average yield: 3-5 year | mensuelle |
| Obligations GdC, rendement moyen 10+ ans | v122487 | 10-10-0122 | …marketable bonds, average yield: over 10 years | mensuelle |
| Obligation de référence GdC long terme | v122544 | 10-10-0122 | …benchmark bond yields: long term | mensuelle |
| Taux préférentiel | v80691311 | 10-10-0145 | Chartered bank administered interest rates - Prime rate | hebdomadaire |
| Financement à un jour du marché monétaire | v39050 | 10-10-0139 | Canada;Overnight money market financing | quotidienne |

- Le tableau 12-10-0011 précise que « The concept of Trade Balance exists only on a Balance of Payments seasonally adjusted basis » (live) — [getCubeMetadata 12100011](https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata)
- Dernières valeurs et dates de diffusion observées (live) : IPC 2026-09 = 170,0 (diffusé le 2026-10-19 à 8 h 30) ; PIB mensuel 2026-08 = 2 371 635 M$ enchaînés 2017 (diffusé le 2026-10-30) ; EPA jusqu'à 2026-10 (diffusée le 2026-11-06) ; mises en chantier jusqu'à 2026-09 (diffusées le 2026-10-19) ; commerce jusqu'à 2026-09 (diffusé le 2026-11-04) — [getDataFromVectorsAndLatestNPeriods](https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods), [getCubeMetadata](https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata)

**Banque du Canada (Valet)**, vérifiés via [groups](https://www.bankofcanada.ca/valet/lists/groups/json) et [observations](https://www.bankofcanada.ca/valet/observations/V39079,AVG.INTWO,FXUSDCAD,BD.CDN.2YR.DQ.YLD,BD.CDN.10YR.DQ.YLD,TB.CDN.90D.MID,CEER_BROADN/json?recent=1) :

| Thème | Code Valet | Libellé Valet | Fréq. |
|---|---|---|---|
| Taux directeur (cible du taux à un jour) | V39079 | Target for the overnight rate (business daily) | quotidienne ouvrable |
| CORRA | AVG.INTWO | Canadian Overnight Repo Rate Average (CORRA) | quotidienne ouvrable |
| Indice composé CORRA | groupe `CORRA_COMPOUNDED_INDEX` | CORRA Compounded Index | quotidienne |
| Bons du Trésor 1, 2, 3, 6 et 12 mois | TB.CDN.30D.MID, TB.CDN.60D.MID, TB.CDN.90D.MID, TB.CDN.180D.MID, TB.CDN.1Y.MID | Treasury bills, 1-month … 1-year | quotidienne ouvrable |
| Obligations de référence 2, 3, 5, 7 et 10 ans, long terme | BD.CDN.2YR.DQ.YLD, BD.CDN.3YR.DQ.YLD, BD.CDN.5YR.DQ.YLD, BD.CDN.7YR.DQ.YLD, BD.CDN.10YR.DQ.YLD, BD.CDN.LONG.DQ.YLD | Benchmark bond yield, … | quotidienne ouvrable |
| Obligations à rendement réel (long terme) | BD.CDN.RRB.DQ.YLD | Real Return Bonds yield, long-term | quotidienne ouvrable |
| Rendements moyens par tranche | CDN.AVG.1YTO3Y.AVG, CDN.AVG.3YTO5Y.AVG, CDN.AVG.5YTO10Y.AVG, CDN.AVG.OVER.10.AVG | Marketable bonds average yield, … | quotidienne ouvrable |
| USD/CAD (et 26 autres paires) | FXUSDCAD, FXEURCAD, FXJPYCAD, FXCNYCAD, FXMXNCAD… | USD/CAD … | quotidienne ouvrable (16 h 30 HE) |
| Taux de change effectif (TCEC/CEER) nominal | CEER_BROADN | Daily nominal Canadian effective exchange rates | quotidienne ouvrable |
| IPPB total, sans énergie, énergie, métaux, agriculture, forêt, pêche | M.BCPI, M.BCNE, M.ENER, M.MTLS, M.AGRI, M.FOPR, M.FISH (et W.BCPI hebdomadaire) | Monthly BCPI Total – v52673496 … | mensuelle / hebdomadaire |
| IPC-tronq / IPC-méd / IPC-comm | CPI_TRIM, CPI_MEDIAN, CPI_COMMON | CPI-trim … | mensuelle |
| IPCX-AE (CPIXFET) a/a | STATIC_CPIXFET | CPI-XFET, percentage change year-over-year | mensuelle |
| Indicateur d'activité / de prix de l'EPE | BOS_ACTIVITY_INDICATOR, BOS_PRICE_INDICATOR | Activity indicator / Price indicator | trimestrielle |
| Attentes d'inflation des ménages à 1, 2 et 5 ans | CES_C1_SHORT_TERM, CES_C1_MID_TERM, CES_C1_LONG_TERM | 1-/2-/5-year-ahead inflation expectations | trimestrielle |
| Taux préférentiel ; hypothèque ordinaire 5 ans | V80691311 ; V80691335 | Prime rate ; Conventional mortgage, 5-year | hebdomadaire (mercredi) |

### Inferences
- Pour l'IPC, les attentes et les taux, Valet est plus pratique (codes lisibles, regroupements). Pour tout ce qui est publié par StatCan (IPC, PIB, EPA, détail, commerce, mises en chantier), il vaut mieux prendre la **source primaire WDS**, qui fournit `releaseTime` et des tableaux temps réel. Valet ne sert alors qu'à recouper.
- Panier minimal suggéré pour A5 :
  - **Taux** : V39079, AVG.INTWO, TB.CDN.90D.MID, BD.CDN.2YR/5YR/10YR/LONG.DQ.YLD, BD.CDN.RRB.DQ.YLD (point mort d'inflation implicite).
  - **Inflation** : v41690973, CPI_TRIM, CPI_MEDIAN, CES_C1_*.
  - **Activité** : v65201210 + 36-10-0491 (millésimes), v62305752 + 36-10-0431.
  - **Emploi** : v2062815, v2062811.
  - **Logement** : v52300157, v111955442.
  - **Consommation et commerce** : v1446859483, v87008984.
  - **Change et produits de base** : FXUSDCAD, CEER_BROADN, M.BCPI, M.ENER.
  - **Sentiment** : BOS_ACTIVITY_INDICATOR.

### Gaps
- Je n'ai pas vérifié de vecteurs pour : le salaire horaire moyen de l'EPA, le PIB nominal, le compte courant (36-10-0018), les permis de bâtir, les prix à la production (IPPI/IPMB) et l'emploi de l'EERH.
- La série 14-10-0383 (chômage par RMR) est probablement une moyenne mobile de 3 mois ; la nature exacte n'est pas vérifiée.
- Les rendements GdC par échéance au-delà des points de référence (courbe zéro-coupon de la BdC) n'ont pas été cherchés dans Valet. La courbe zéro-coupon est publiée par la BdC en fichier, mais je ne l'ai pas vérifié dans cette session.
