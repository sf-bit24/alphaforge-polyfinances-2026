# Sources gratuites ESG, émissions, controverses et classifications sectorielles (état au 14 novembre 2026)

> Notes de recherche pour AlphaForge AI (PolyFinances 2026, BN + AWS), agent A5 (collecte), persona Mateo (ESG élevé ; exclure ENB.TO, CNQ.TO, XOM sauf justification ; comparer ESGV à SPY).
> Convention : « (vérifié API 2026-11-14) » = constaté par appel direct à l'API ou au fichier, sans clé, le 14 novembre 2026. « (non revérifié nov. 2026) » = fait connu ou issu d'une page plus ancienne, pas reconfirmé.
> Méthode : pages officielles (portails gouvernementaux, pages de licence, conditions d'utilisation) + sondages directs des API (Climate TRACE v7, EPA Envirofacts, SEC EDGAR, Banque mondiale, MSC GeoMet, datamart ECCC). Deux actions ont été refusées par le classificateur de permissions de l'environnement : l'appel direct à l'endpoint Yahoo `quoteSummary` (contournement cookie/crumb) et une recherche web sur le scraping MSCI. Elles n'ont pas été contournées. C'est en soi un signal : l'accès Yahoo ESG passe par un mécanisme non autorisé par Yahoo.

---

## 1. Émissions par installation et par entreprise (Canada, États-Unis, UE, mondial)

### Takeaway
Les meilleures sources gratuites et légalement réutilisables pour l'univers de Mateo sont **le GHGRP canadien (ECCC, Licence du gouvernement ouvert – Canada)**, qui donne les émissions 2004–2024 par installation avec la dénomination sociale de la société déclarante, et **Climate TRACE (CC BY 4.0, API v7 sans clé)**. Mais l'attribution « installation → société mère → ticker » reste le maillon faible : Climate TRACE n'attribue que ~1,76 Mt CO2e à Canadian Natural en 2024, contre ~18,6 Mt au GHGRP. Côté américain, le GHGRP de l'EPA est figé à l'année 2023 dans Envirofacts, et un projet d'abrogation est pendant.

### Cited Findings

#### Fiche — GHGRP Canada (Programme de déclaration des gaz à effet de serre, ECCC)
- Jeu de données « Greenhouse Gas Reporting Program (GHGRP) – Greenhouse Gas Emissions Data by Facility », éditeur ECCC, licence **Open Government Licence – Canada**, mise à jour annuelle ; seuil de déclaration de 10 kt CO2e/an ; deux fichiers (émissions par gaz 2004→présent ; émissions par source 2022→présent), en CSV et XLSX — [open.canada.ca](https://open.canada.ca/data/en/dataset/a8ba14b7-7f23-462a-bdbb-83b0ef629823)
- Métadonnées CKAN : `metadata_modified` 2026-05-27, licence « Open Government Licence - Canada » — [API CKAN open.canada.ca](https://open.canada.ca/data/api/action/package_show?id=a8ba14b7-7f23-462a-bdbb-83b0ef629823) (vérifié API 2026-11-14)
- Fichiers sur le datamart ECCC (modifiés le 2026-07-24) : `PDGES-GHGRP-GHGEmissionsGES-2004-Present.csv` (10 MiB), `PDGES-GHGRP-GHGEmissionsSourcesGES-2022-Present.csv` (9 MiB), versions XLSX et `PDGES-GHGRP-Tableaux-Donnees-Data-Tables-2024.xlsx`. Le datamart est une application JavaScript ; les listes de fichiers passent par `https://data-donnees.az.ec.gc.ca/api/path_contents?path=...` et les téléchargements par `.../api/file?path=...` — [datamart ECCC](https://data-donnees.ec.gc.ca/data/substances/monitor/greenhouse-gas-reporting-program-ghgrp-facility-greenhouse-gas-ghg-data/) (vérifié API 2026-11-14)
- Le CSV compte **82 colonnes**, dont : GHGRP ID, année de référence, nom et lat/long de l'installation, **Facility NPRI ID**, **code SCIAN (NAICS) de l'installation**, **dénomination sociale de la société déclarante** (Reporting Company Legal Name), nom commercial, **numéro d'entreprise (BN)**, **numéro DUNS**, émissions par gaz, et « Total Emissions (tonnes CO2e) – excl. CO2bio ». Années présentes : jusqu'à **2024** ; 1 879 enregistrements d'installations pour 2024 ; total de ces installations en 2024 ≈ 291,7 Mt CO2e — [fichier CSV ECCC](https://data-donnees.ec.gc.ca/data/substances/monitor/greenhouse-gas-reporting-program-ghgrp-facility-greenhouse-gas-ghg-data/) (vérifié par téléchargement 2026-11-14)
- Agrégats 2024 calculés sur ce fichier par correspondance de texte sur la dénomination sociale : Suncor 32,15 Mt (10 installations) ; **Canadian Natural 18,57 Mt (92 installations ; principale : Horizon Oil Sands Processing Plant and Mine, 6,02 Mt)** ; Cenovus 13,98 Mt (47) ; **Imperial Oil 13,57 Mt (8)** ; **Enbridge 0,75 Mt (3)** ; « Exxon » 0,44 Mt (1) — [fichier CSV ECCC](https://data-donnees.ec.gc.ca/data/substances/monitor/greenhouse-gas-reporting-program-ghgrp-facility-greenhouse-gas-ghg-data/) (calcul de l'auteur, 2026-11-14)
- Fiches officielles de synthèse par installation (HTML EN/FR) — [climate-change.canada.ca/facility-emissions](https://climate-change.canada.ca/facility-emissions/?GoCTemplateCulture=en-CA)

#### Fiche — INRP / NPRI (Inventaire national des rejets de polluants)
- « Bulk data files for all years – releases, disposals, transfers and facility locations » ; ECCC ; couverture 1993-01-01 → **2024-12-31** ; publié le 2026-03-26, modifié le 2026-05-01 ; mise à jour annuelle ; CSV (rejets, éliminations, transferts, géolocalisation, commentaires) ; **Open Government Licence – Canada** ; contient des thèmes SCIAN/NAICS et secteur — [open.canada.ca NPRI](https://open.canada.ca/data/en/dataset/40e01423-7728-429c-ac9d-2954385ccdfb)
- Le GHGRP contient la colonne « Facility NPRI ID », ce qui permet de joindre GHGRP et INRP au niveau de l'installation — [CSV GHGRP ECCC](https://data-donnees.ec.gc.ca/data/substances/monitor/greenhouse-gas-reporting-program-ghgrp-facility-greenhouse-gas-ghg-data/) (vérifié 2026-11-14)

#### Fiche — Rapport d'inventaire national (RIN/NIR) du Canada, édition 2026
- NIR 1990–2024 soumis à la CCNUCC (soumission conjointe avec le 2e rapport biennal de transparence). Émissions 2024 hors UTCATF : **685 Mt CO2e**, soit -10 % (-78 Mt) par rapport à 2005 ; +12,6 % depuis 1990 ; pétrole et gaz +1,8 % en 2024 vs 2023 et +76 % depuis 1990 — [Sommaire 2026 ECCC](https://www.canada.ca/en/environment-climate-change/services/climate-change/greenhouse-gas-emissions/sources-sinks-executive-summary-2026.html) ; [page principale de l'inventaire](https://www.canada.ca/ghg-inventory)
- Granularité : nationale, provinciale et sectorielle (GIEC / secteurs économiques), **pas par entreprise** — [Aperçu 1990–2024](https://www.canada.ca/en/environment-climate-change/services/climate-change/greenhouse-gas-emissions/inventory/preliminary-emissions-1990-2024.html)

#### Fiche — EPA GHGRP (États-Unis) : Envirofacts API, FLIGHT, statut réglementaire
- API Envirofacts sans clé, format `https://data.epa.gov/efservice/{table}/{colonne}/{op}/{valeur}/rows/{a}:{b}/JSON`. La table `pub_dim_facility` contient `parent_company` **avec pourcentages de détention** (ex. Prudhoe Bay : « ExxonMobil Corporation (36.4%); ConocoPhillips Alaska, Inc (36.1%); BP America Inc. (26.4%)… »), `naics_code`, `frs_id`, lat/long et année — [Envirofacts pub_dim_facility](https://data.epa.gov/efservice/pub_dim_facility/parent_company/CONTAINING/EXXON/rows/0:2/JSON) (vérifié API 2026-11-14)
- Les requêtes `year = 2024` et `year = 2025` renvoient `[]`, alors que `2023` renvoie des données. **Année la plus récente dans Envirofacts : RY2023** — [Envirofacts année 2024](https://data.epa.gov/efservice/pub_dim_facility/year/=/2024/rows/0:0/JSON) (vérifié API 2026-11-14)
- La page « Data Sets » de l'EPA (mise à jour le 30 juillet 2026) propose comme jeu le plus récent « 2023 Data Summary Spreadsheets » et ne mentionne pas de publication RY2024 — [EPA GHGRP Data Sets](https://www.epa.gov/ghgreporting/data-sets)
- La publication RY2023 date du 15 octobre 2024 — [EPA news release](https://www.epa.gov/newsreleases/epa-releases-2023-data-collected-under-greenhouse-gas-reporting-program)
- Statut : l'EPA a proposé en septembre 2025 de supprimer les obligations de déclaration pour la plupart des catégories de sources. Au 9 juillet 2026, aucune règle finale : « EPA has not yet issued a final rule… There is no deadline for EPA action on revocation. » Échéance RY2025 repoussée du 31 mars au 30 octobre 2026 — [Beveridge & Diamond, 2026-07-09](https://www.bdlaw.com/publications/with-federal-greenhouse-gas-reporting-in-limbo-states-expand-ghg-reporting/) ; [communiqué EPA sur la proposition](https://www.epa.gov/newsreleases/epa-releases-proposal-end-burdensome-costly-greenhouse-gas-reporting-program-saving-24)
- Une règle finale intérimaire reporterait l'échéance RY2025 au **10 mars 2027**, et l'administrateur Zeldin aurait indiqué en octobre 2026 ne pas avoir arrêté la portée de la règle finale (rapporté par des sources secondaires) — [CRS R49348](https://www.congress.gov/crs-product/R49348) ; [Federal Register public inspection 2026-20982](https://public-inspection.federalregister.gov/2026-20982.pdf) (date exacte non revérifiée)
- FLIGHT (outil cartographique) — [ghgdata.epa.gov](https://ghgdata.epa.gov/ghgp/main.do)

#### Fiche — EPA TRI (Toxics Release Inventory)
- La table Envirofacts `tri_facility` comporte `parent_co_name`, `standardized_parent_company`, `parent_co_db_num` (D&B), `foreign_parent_co_name` et `standardized_foreign_parent_company`, ce qui permet un lien installation → société mère, y compris étrangère (utile pour Imperial/Exxon ou les filiales US d'Enbridge) — [Envirofacts tri_facility](https://data.epa.gov/efservice/tri_facility/state_abbr/=/TX/rows/0:0/JSON) (vérifié API 2026-11-14)

#### Fiche — Climate TRACE (coalition ; API v7)
- Licence : données d'émissions et métadonnées sous **CC BY 4.0**, sauf jeux externes listés (EDGAR, FAOSTAT, CEDS au niveau pays, et données source « other manufacturing » issues de l'E-PRTR européen, d'EPA FLIGHT et du PRTR israélien). « Climate TRACE® » et le logo sont des marques de WattTime. Aucune clause sur l'API ni sur les limites de débit — [climatetrace.org/terms](https://climatetrace.org/terms)
- Réutilisation commerciale autorisée avec attribution et mention des modifications ; citation suggérée « Climate TRACE (2026) » — [recherche : Terms + about the data](https://media.climatetrace.org/about_the_data_latest_b6e7b8d419.pdf)
- API : documentation Scalar à `https://api.climatetrace.org/` ; spécification OpenAPI 3.1 (`/v7/docs/openapi.json`, servie en YAML), **version 7.3.0**. Endpoints : `/v7/owners?name=`, `/v7/sources?ownerIds=&year=&sectors=`, `/v7/sources/:id`, `/v7/sources/emissions` (agrégats), `/v7/rankings/countries`, `/v7/admins`, `/v7/cities`, `/v7/definitions/*`, `/v7/metadata`. Pas d'authentification requise — [API Climate TRACE](https://api.climatetrace.org/) (vérifié API 2026-11-14)
- Métadonnées de version : `dataVersion v5.12.0`, `releaseDate 2026-10-28`, couverture **mensuelle de 2015-01 à 2026-08** — [/v7/metadata](https://api.climatetrace.org/v7/metadata) (vérifié API 2026-11-14)
- Certains champs (activité, capacité, facteur d'émission de sources pétrole et gaz) sont renvoyés comme **« license restricted »**. Les données sous-jacentes ne sont donc pas toutes ouvertes — [/v7/sources](https://api.climatetrace.org/v7/sources?limit=2) (vérifié API 2026-11-14)
- Propriété : `/v7/owners?name=Canadian Natural` renvoie `E100000000105 – Canadian Natural Resources Ltd`, mais seulement **3 sources lui sont attribuées en 2024** (Horizon Mine power station, Sturgeon Refinery de North West Redwater Partnership, Primrose South power plant), pour un total agrégé de **1,76 Mt CO2e**. Aucun propriétaire « Enbridge » n'est trouvé. Exxon apparaît sous plusieurs entités distinctes (Exxon Mobil Corp, ExxonMobil Oil Corp, ExxonMobil Production Deutschland GmbH, Exxon Mobil Production Co), sans consolidation visible vers la société mère — [/v7/owners](https://api.climatetrace.org/v7/owners?name=Exxon) ; [/v7/sources/emissions?ownerIds=E100000000105](https://api.climatetrace.org/v7/sources/emissions?ownerIds=E100000000105&year=2024&gas=co2e_100yr) (vérifié API 2026-11-14)
- Dépôts Zenodo versionnés de l'inventaire — [Zenodo Climate TRACE](https://zenodo.org/records/17179606/latest)

#### Fiche — EU ETS / Union Registry / EUTL
- Le registre de l'Union expose une section « Data Download » (fichiers « Operators Daily », etc.) ; l'AEE republie un jeu « Union Registry, v2.0 Sep. 2025 » couvrant 2005–2024 (CSV/TXT/SQL) — [AEE, téléchargement EU ETS](https://www.eea.europa.eu/data-and-maps/data/european-union-emissions-trading-scheme-16/eu-ets-data-download-latest-version) ; [note qualité ETC-CM sept. 2025](https://sdi.eea.europa.eu/catalogue/api/records/49d0cf8e-7aff-4129-9e88-7353ddc8f2b6/attachments/ETC-CM%20EU-ETS%20data%20quality%20September_2025.pdf)
- Les émissions vérifiées 2025 ont été publiées en avril 2026 (7 064 installations fixes, 206 exploitants aériens, 1 745 exploitants maritimes), avec -1,3 % selon la Commission — [Carbon Pulse](https://carbon-pulse.com/501135/) ; [Marine Link](https://www.marinelink.com/news/eu-emissions-trading-system-sustains-537952)
- Pertinence : faible pour les noms canadiens ; utile pour les installations européennes de XOM. Le lien vers la société mère passe par le nom du titulaire de compte (non vérifié).

#### Fiche — Carbon Majors (InfluenceMap)
- Trois CSV (granularité basse : année, entité, type d'entité, **LEI**, émissions totales ; moyenne : + produit et production ; haute : + entité déclarante, source, émissions opérationnelles torchage/évent/consommation propre/méthane fugitif) + dictionnaire et README PDF. Publication du **21/01/2026, données jusqu'à 2024**, mise à jour annuelle en novembre. **Usage non commercial uniquement**, soumis aux conditions générales d'InfluenceMap — [carbonmajors.org/Downloads](https://carbonmajors.org/Downloads)

#### Fiche — Global Energy Monitor (GEM) trackers
- La majorité des données des trackers est sous **CC BY 4.0** sauf mention contraire. Exception : les panaches (« Plumes ») du Methane Emitters Tracker issus de Carbon Mapper sont sous CC BY-NC-SA 4.0. Il existe un formulaire de demande d'« exemption commerciale » — [GEM Methane Emitters Tracker – download](https://globalenergymonitor.org/projects/global-methane-emitters-tracker/download-data/) (via résultat de recherche ; page de licence générale introuvable, 404)
- Global Oil and Gas Extraction Tracker : publication la plus récente en **mars 2026**, fichier .xls, couvre localisation, **propriété**, production et réserves. La page ne précise ni la licence ni les champs de propriété — [GEM GOGET download](https://globalenergymonitor.org/projects/global-oil-gas-extraction-tracker/download-data/)

#### Fiche — OS-Climate (désormais FINOS)
- La Linux Foundation a fusionné FINOS et OS-Climate le 26 juin 2024 ; les projets passent sous la gouvernance FINOS — [FINOS OS-Climate](https://www.finos.org/os-climate) ; [GitHub physrisk](https://github.com/os-climate/physrisk)
- L'idée d'un « data commons » ouvert est d'origine, mais aucune mise à jour de statut 2025–2026 n'a été trouvée — [BusinessGreen](https://www.businessgreen.com/news/4019603/climate-risk-amazon-allianz-microsoft-global-join-open-initiative)

### Inferences
- Chaîne de liaison recommandée pour les noms canadiens : GHGRP (dénomination sociale + BN + DUNS) → table de correspondance maison « société déclarante → émetteur coté » (ex. Imperial Oil Ltd → IMO.TO, détenu majoritairement par XOM) → ticker. Les émissions canadiennes de XOM sont surtout déclarées sous Imperial Oil (13,57 Mt en 2024), et non sous « Exxon ». Sans table de propriété, on sous-estime XOM au Canada.
- L'écart d'un facteur 10 entre Climate TRACE (1,76 Mt) et le GHGRP (18,57 Mt) pour CNQ montre que l'attribution par propriétaire de Climate TRACE est incomplète pour les sables bitumineux. Il faut privilégier le GHGRP pour le Canada et réserver Climate TRACE aux actifs hors Canada et au contexte sectoriel et pays.
- Le GHGRP agrège des émissions de **scope 1 au niveau des installations** au-dessus de 10 kt. Il ne couvre ni le scope 3 (dominant pour les producteurs pétroliers, via la combustion des produits vendus) ni les installations sous le seuil. Les ~292 Mt des installations déclarantes représentent environ 43 % des 685 Mt nationales (calcul de l'auteur).
- Pour les États-Unis, dans une démo de novembre 2026, il faut dater explicitement les valeurs EPA « RY2023 (dernière année publiée) » et signaler l'incertitude réglementaire.

### Gaps
- La « Open Sustainability Index » n'a pas été recherchée (manque de temps). Statut, licence et couverture inconnus.
- Date et contenu exacts de la règle finale intérimaire EPA (2026-20982) non confirmés sur le Federal Register.
- Conditions générales InfluenceMap (Carbon Majors) non lues ; on ignore si un datathon commandité par une banque est « non commercial ».
- Licence générale GEM (la page dédiée renvoie 404) : CC BY 4.0 confirmé seulement via la page du tracker méthane et des extraits de FAQ.
- Licence de réutilisation des données du registre de l'Union (EU ETS) non vérifiée.

---

## 2. Engagements climat, trajectoires de transition et listes d'exclusion d'ONG (Net Zero Tracker, SBTi, CDP, TPI, InfluenceMap, Urgewald)

### Takeaway
La plupart des jeux d'ONG « gratuits » sont **non commerciaux** (Net Zero Tracker CC BY-NC 4.0 depuis décembre 2024, Carbon Majors, TPI) ou **interdisent tout partage hors de l'organisation** (Urgewald GOGEL). Le Target Dashboard de la SBTi (XLSX hebdomadaire avec ISIN/LEI) est le plus exploitable, mais sa licence n'est pas explicitée.

### Cited Findings

#### Fiche — Net Zero Tracker (ECIU, Data-Driven EnviroLab, NewClimate, Oxford Net Zero)
- Les jeux actuels sont sous **CC BY-NC 4.0** ; l'ancien « Current Snapshot » n'était sous CC BY 4.0 que jusqu'au 2 décembre 2024. Le nouveau Current Snapshot (depuis le 3 décembre 2024) est mis à jour **toutes les quatre heures**. Usage commercial interdit sans permission (hello@zerotracker.net) ; aucune API mentionnée — [zerotracker.net/data-terms-of-use](https://zerotracker.net/data-terms-of-use)
- Couvre pays, régions, villes et « les plus grandes entreprises » — [zerotracker.net/about](https://zerotracker.net/about)

#### Fiche — SBTi Target Dashboard
- Téléchargements XLSX : `https://files.sciencebasedtargets.org/production/files/companies-excel.xlsx` et `.../targets-excel.xlsx`, plus un dictionnaire de données. Champs : nom, **ISIN**, **LEI**, région et siège, secteur, type et statut d'engagement, échéance, texte de la cible, scopes, année de base et année cible, alignement de température. **Mise à jour chaque jeudi** ; retraits mensuels ; pause en fin d'année. Aucune licence de réutilisation explicite sur la page ; avertissement : « The SBTi accepts no responsibility for how third parties use, present or rely on the information » — [sciencebasedtargets.org/target-dashboard](https://sciencebasedtargets.org/target-dashboard)

#### Fiche — TPI Centre (LSE)
- Usages libres sans licence : académique (enseignement supérieur), personnel et informationnel, propriétaires d'actifs, usage interne non commercial « solely for exploratory, illustrative or validation purposes » comme intrant secondaire, engagement actionnarial, médias. Exigent une autorisation écrite ou une licence : redistribution liée à des revenus, œuvres dérivées et analytics générant des revenus, **« Use of any automated tools (including bots, scrapers, or spiders) »**, création d'indices ou de fonds. Reproduction limitée à une « portion non substantielle ». Attribution obligatoire ; les données Management Quality relèvent de LSEG (tpimqaccess@lseg.com) — [TPI, use of the Centre's data](https://transitionpathwayinitiative.org/use-of-the-centre-s-data)

#### Fiche — CDP
- Données des entreprises : CDP « reserves all rights » ; une licence (extrait Excel) se demande auprès de CDP ; les réponses 2024 ne seraient pas disponibles — [cdp.net/responses](https://cdp.net/ja/responses) (extrait de recherche)
- Les données des villes sont diffusées via des jeux étiquetés « CDP Open Database License » pour certaines années (d'autres années indiquent une licence inconnue) — [Open Net Zero, CDP 2020 cities](https://opennetzero.org/cdp/2020-full-cities-dataset33)
- Le Corporate Environmental Action Tracker est limité à l'usage non commercial, avec mention « Powered by CDP Data » — [CDP terms of use](https://classic.cdp.net/id/data/corporate-environmental-action-tracker/terms-of-use)

#### Fiche — InfluenceMap LobbyMap
- Couvre 1 000 entreprises et 330 associations professionnelles ; scores consultables, données sous connexion — [LobbyMap Scores](https://lobbymap.org/KR/LobbyMapScores) ; [data.influencemap.org](https://data.influencemap.org/LobbyMapScores)
- La méthodologie qualifie le contenu de « open source and free to view and use » et renvoie aux conditions — [LobbyMap Methodology](https://influencemap.org/briefing/LobbyMap-Methodology-24422)

#### Fiche — Urgewald GOGEL (Global Oil & Gas Exit List) 2026
- GOGEL 2026 publiée le **10 novembre 2026** ; ~1 900 entreprises (amont, intermédiaire, électricité) ; accès sur inscription ; version avec identifiants financiers « sur demande » — [gogel.org](https://gogel.org/)
- Conditions : licence libre de redevance **limitée à la recherche interne, non commerciale** ; **partage hors de l'organisation interdit** ; distribution et partage en masse, sous-licence et publication interdits sans permission écrite ; les utilisateurs commerciaux (institutions financières, consultants) doivent obtenir une licence ; attribution « Urgewald » obligatoire ; les dérivés restent propriété d'Urgewald — [GOGEL Terms & Conditions](https://gogel.org/terms-conditions-without-identifiers)

#### Fiche — Urgewald GCEL (Global Coal Exit List) 2026
- Près de 2 700 entreprises (~1 500 sociétés mères et leurs filiales) ; téléchargement complet après connexion gratuite ; version avec identifiants de sociétés et de titres sur demande pour les institutions financières — [coalexit.org](https://www.coalexit.org/)

### Inferences
- GOGEL et GCEL sont pertinentes pour Mateo (CNQ et XOM y figurent très probablement en tant que producteurs pétroliers et gaziers, ce qui n'a pas été vérifié ligne à ligne). Mais leurs conditions interdisent de les verser dans une base de connaissances partagée : au mieux, un drapeau « figure dans GOGEL 2026 » avec attribution, et seulement après confirmation écrite d'Urgewald.
- Le Target Dashboard SBTi (ISIN/LEI inclus) est la source la plus directement « tickerisable » pour un critère « cible validée 1,5 °C / net zéro ».

### Gaps
- Conditions d'utilisation du site SBTi (/about-us/website-terms-of-use) non lues : redistribution non confirmée.
- Conditions GCEL non lues (probablement proches de celles de GOGEL, non vérifié).
- Prix des licences commerciales Urgewald, CDP, TPI et InfluenceMap : non publiés.

---

## 3. Scores ESG d'entreprise : existe-t-il une API gratuite et légalement utilisable ?

### Takeaway
**Non.** Aucune source gratuite de *scores* ESG d'entreprise n'est à la fois automatisable et redistribuable. Yahoo/Sustainalytics (via yfinance) est interdit d'usage commercial et d'accès automatisé par les CGU de Yahoo. MSCI interdit explicitement « AI agents, MCP servers or connectors » (CGU du 15 juillet 2026). LSEG exige une approbation écrite même pour une publication non commerciale. Finnhub et FMP placent l'ESG derrière des offres payantes. ESG Book a fusionné avec EthiFinance en juillet 2026.

### Cited Findings

#### Fiche — Yahoo Finance / Sustainalytics via yfinance
- yfinance 1.8.0 (2026-11-03, Apache-2.0) conserve la propriété `Ticker.sustainability`, qui appelle le module Yahoo `esgScores` — [PyPI yfinance](https://pypi.org/pypi/yfinance/json) ; [source quote.py](https://raw.githubusercontent.com/ranaroussi/yfinance/main/yfinance/scrapers/quote.py) (vérifié 2026-11-14)
- README yfinance : « not affiliated, endorsed, or vetted by Yahoo » ; « intended for research and educational purposes » ; « the Yahoo! finance API is intended for personal use only » — [GitHub yfinance](https://github.com/ranaroussi/yfinance)
- CGU Yahoo : « you may not access or reuse the Services, or any portion thereof, for any commercial purpose » ; robots, spiders, scrapers et outils de data mining interdits sans « express, prior permission » ; interdiction de créer « any database, archive… data feed » concurrent ; au Canada, Yahoo Finance est fourni par Yahoo Finance ULC — [Yahoo Terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html)
- Historique : Sustainalytics fournit des notes ESG publiques via Yahoo Finance depuis février 2018 — [Davis Polk](https://www.davispolk.com/insights/client-update/sustainalytics-esg-ratings-publicly-available-company-yahoo-finance-page). Depuis juillet 2020, il publie sur son site des notes de risque ESG de haut niveau pour plus de 4 000 sociétés — [Sustainalytics 2020](https://www.sustainalytics.com/esg-news/news-details/2020/07/22/sustainalytics-makes-its-esg-ratings-and-data-on-more-than-4-000-companies-publicly-accessible-on-its-website)
- Méthodologie : depuis le 1er juillet 2025, Sustainalytics n'accepte plus d'informations non publiques des émetteurs (~1 % des notes affectées) — [Sustainalytics blog](https://www.sustainalytics.com/esg-research/resource/investors-esg-blog/improving-transparency-for-investors--ending-the-acceptance-of-non-public-information-for-esg-risk-ratings)
- L'appel direct à `query2.finance.yahoo.com/v10/finance/quoteSummary` avec contournement cookie/crumb a été **refusé par le classificateur de permissions** de notre environnement (catégorie « Unauthorized Access ») : la disponibilité actuelle des scores pour XOM, ENB.TO, CNQ.TO et ESGV n'a donc pas pu être testée.

#### Fiche — MSCI ESG Ratings (outil de recherche public)
- La page de l'outil « ESG Ratings and Climate Search Tool » renvoie désormais vers MSCI ONE : « MSCI clients can access sustainability and climate data on over 10,000 companies through our MSCI ONE platform » — [MSCI](https://www.msci.com/data-and-analytics/sustainability-solutions/esg-ratings-climate-search-tool)
- CGU MSCI (mises à jour le **15 juillet 2026**) : hors bon de commande, usage « only internally for non-production purposes » ; interdiction d'« use unauthorized bots, scrapers, crawlers, **AI agents, MCP servers or connectors** » ; interdiction de redistribuer, de créer des œuvres dérivées et de développer un « MSCI-Related Product » (indices inclus) ; supplément IA séparé — [MSCI Terms of Use](https://www.msci.com/legal/terms-of-use)

#### Fiche — LSEG (ex-Refinitiv) ESG Scores
- « ESG Scores Finder » par société ; 16K+ sociétés, 99 % du FTSE All World (données à mars 2026) ; les scores peuvent être « referenced and published for non-commercial purposes **with written approval** » ; « Any commercial use, redistribution, or systematic reproduction of the data requires a licence » — [LSEG ESG scores](https://www.lseg.com/en/data-analytics/sustainable-finance/esg-scores) ; [CGU PDF](https://www.lseg.com/content/dam/data-analytics/en_us/documents/policies/lseg-esg-website-terms-of-use.pdf)

#### Fiche — Finnhub ESG
- Le client officiel expose `company_esg_score("AAPL")` — [README finnhub-python](https://raw.githubusercontent.com/Finnhub-Stock-API/finnhub-python/master/README.md) ; finnhub-python 2.4.30 (2026-11-05) — [PyPI](https://pypi.org/pypi/finnhub-python/json)
- La page de tarifs range « ESG Scores » parmi les données alternatives. Prix « All-In-One » contradictoires : 3 500 $/mois facturé annuellement selon ROIC.AI, contre 1 000 $/mois selon TrustRadius — [finnhub.io/pricing](https://finnhub.io/pricing) ; [ROIC.AI](https://www.roic.ai/blog/finnhub-alternative-roic-ai-vs-finnhub-api) ; [TrustRadius](https://tr-web.dev.trustradius.com/products/finnhub-stock-apis/pricing)

#### Fiche — Financial Modeling Prep (FMP) ESG
- Endpoint actuel `https://financialmodelingprep.com/stable/esg-ratings?symbol=AAPL` (l'ancien est marqué « legacy ») ; plan gratuit à 250 requêtes/jour — [FMP docs esg-ratings](https://site.financialmodelingprep.com/developer/docs/stable/esg-ratings) ; [FMP FAQ](https://site.financialmodelingprep.com/faqs?code=ESG) (extraits de recherche, site en 403 pour l'outil de lecture)
- Prix tiers (non officiels, divergents) : Starter 22–29 $, Premium 59 $, Ultimate 139–149 $/mois (vérifié par QVeris le 30 juillet 2026) ; produit ESG à partir de 300 $/mois selon Datarade — [QVeris](https://api.qveris.ai/guides/financial-modeling-prep-api) ; [Datarade](https://datarade.ai/data-products/esg-data-environmental-social-and-governance-ratings-financial-modeling-prep)

#### Fiche — ESG Book (désormais EthiFinance)
- Fusion EthiFinance–ESG Book signée le 8 juillet 2026 et annoncée le 9 juillet 2026, sous la marque EthiFinance ; ESG Book couvre plus de 75 000 sociétés — [Reed Smith](https://www.reedsmith.com/news/reed-smith-advises-ethifinance-on-its-business-combination-with-esg-book/) ; [ESG Today](https://www.esgtoday.com/ethifinance-esg-book-merge-to-form-european-sustainability-and-credit-rating-champion/)
- `https://www.esgbook.com/access` redirige (301) vers `https://www.ethifinance.com/` — [esgbook.com/access](https://www.esgbook.com/access) (constaté 2026-11-14)
- Historiquement : profils gratuits sur inscription, sans export Excel — [Tufts research guide](https://researchguides.library.tufts.edu/impact-esg)

### Inferences
- Pour un projet présenté à une banque commanditaire, intégrer des scores Sustainalytics (Yahoo), MSCI ou LSEG dans la base de connaissances partagée exposerait l'équipe à une violation des CGU. Le choix des organisateurs de ne fournir aucun score ESG est cohérent avec ce constat.
- Alternative défendable : construire un **profil ESG « factuel » à partir de sources ouvertes** (émissions GHGRP/Climate TRACE, intensité carbone, présence dans les listes d'exclusion publiques, cibles SBTi, sanctions, controverses GDELT, règles d'exclusion de l'indice ESGV) plutôt qu'un « score » propriétaire. C'est aussi plus explicable.

### Gaps
- Inclusion de l'ESG dans le plan gratuit Finnhub ou FMP : non confirmée sur les pages officielles (403 ou contenu JavaScript).
- Conditions actuelles d'accès gratuit d'ESG Book après la fusion : inconnues.
- CGU spécifiques au site public de Sustainalytics (legal-disclaimers) non lues.

---

## 4. Controverses, sanctions et exclusions (NBIM, OFAC, Canada, OpenSanctions, BHRRC, RepRisk, GDELT)

### Takeaway
La liste d'exclusion de NBIM (fonds souverain norvégien) est le signal public le plus fort pour Mateo : CNQ, Cenovus, Imperial et Suncor y sont exclues pour « émissions de GES inacceptables », alors qu'Enbridge et Exxon n'y figurent pas. La liste est figée par des lignes directrices intérimaires et n'est pas téléchargeable en CSV. Les listes de sanctions (OFAC, Canada) sont gratuites et du domaine public, mais peu pertinentes pour des grandes capitalisations. OpenSanctions est CC BY-NC 4.0. GDELT DOC 2.0 est gratuit, mais limité à une fenêtre glissante de 3 mois.

### Cited Findings

#### Fiche — NBIM / Conseil d'éthique norvégien
- 201 sociétés listées (183 exclusions, 18 sous observation) ; « last updated on 11 August 2026 », reflétant les décisions « as at November 2025 ». Sous les **lignes directrices intérimaires**, Norges Bank « shall not decide on observation or exclusion, but may revoke previous decisions ». Critères par produit (charbon, tabac, armes nucléaires, cannabis) et par conduite (« Unacceptable greenhouse gas emissions », droits humains, dommages environnementaux graves, corruption). Canadian Natural, Cenovus, Imperial Oil et Suncor sont exclues pour « Unacceptable greenhouse gas emissions » ; Toronto-Dominion Bank est sous observation (corruption ou criminalité financière) ; **Enbridge et Exxon n'apparaissent pas**. Pas de téléchargement CSV ni d'API sur la page — [NBIM exclusion of companies](https://www.nbim.no/en/responsible-investment/ethical-exclusions/exclusion-of-companies/)

#### Fiche — OFAC Sanctions List Service (Trésor américain)
- SDN List, Non-SDN Consolidated List, outil de jeu personnalisé et archive des fichiers delta ; « Advanced Data Format » (modèle Advanced Sanctions Data) et formats hérités ; téléchargement immédiat sans authentification mentionnée — [OFAC SLS](https://ofac.treasury.gov/sanctions-list-service) ; [sanctionslist.ofac.treas.gov](https://sanctionslist.ofac.treas.gov/Home/index.html)

#### Fiche — Liste consolidée des sanctions autonomes canadiennes (Affaires mondiales Canada)
- Formats HTML, PDF et **XML** ; couvre la LMES (SEMA) et la loi Magnitsky canadienne (JVCFOA) ; liste « à des fins administratives », qui n'est pas un règlement — [international.gc.ca](https://www.international.gc.ca/world-monde/international_relations-relations_internationales/sanctions/consolidated-consolide.aspx?lang=eng)

#### Fiche — OpenSanctions
- Données sous **CC BY-NC 4.0** ; offres payantes : Screening API facturée à la requête (crédits gratuits à l'inscription), licence de screening à forfait (usage interne), licence revendeur ; prix sur devis — [opensanctions.org/licensing](https://www.opensanctions.org/licensing/)
- Republie la liste canadienne SEMA — [OpenSanctions ca_dfatd_sema_sanctions](https://www.opensanctions.org/datasets/ca_dfatd_sema_sanctions)
- Bibliothèques : followthemoney 4.11.3 (MIT, 2026-11-07) et nomenklatura 4.17.6 (2026-11-06) — [PyPI followthemoney](https://pypi.org/pypi/followthemoney/json) ; [PyPI nomenklatura](https://pypi.org/pypi/nomenklatura/json)

#### Fiche — Business & Human Rights Resource Centre
- Tableaux de bord enrichis : 275 marques d'habillement, **142 entreprises extractives**, 35 hôteliers, 121 sociétés tech ; base d'allégations par entreprise mise à jour en continu — [BHRRC technology company dashboards](https://www.bhrrc.org/en/big-issues/technology-human-rights/technology-company-dashboards/) ; [BHRRC companies](https://business-humanrights.org/en/companies)

#### Fiche — GDELT DOC 2.0 API
- Endpoint `https://api.gdeltproject.org/api/v2/doc/doc` ; opérateurs : phrase exacte, OR, exclusion, `domain`, `sourcecountry`, `sourcelang`, **`tone`**, **`theme:`** (thèmes GKG), `near`, `repeat` ; **fenêtre des 3 derniers mois** ; sorties HTML, CSV, JSON, RSS ; MAXRECORDS par défaut 75, jusqu'à 250 — [GDELT blog DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
- Client Python gdeltdoc 1.12.0 (2025-04-03) — [PyPI gdeltdoc](https://pypi.org/pypi/gdeltdoc/json)

### Inferences
- Pour justifier une exclusion de CNQ auprès de Mateo, la décision de NBIM (critère GES) est une **preuve citable et explicable**. Comme ENB et XOM n'y figurent pas, leur exclusion doit reposer sur d'autres règles (ex. règles FTSE Choice de l'ESGV, voir section 6).
- La page NBIM n'offrant pas de CSV, l'agent A5 devrait capturer et dater un instantané HTML et versionner la liste.
- GDELT convient comme « radar de controverses récentes » (tonalité négative + thèmes environnementaux par nom de société), pas comme historique. Il faut un stockage local pour construire un historique.

### Gaps
- RepRisk : payant, prix non publié (non recherché en détail).
- Conditions de réutilisation du BHRRC introuvables.
- Définition d'« usage non commercial » d'OpenSanctions (pages FAQ en 404) : on ne sait pas si un datathon commandité par une banque est admissible.
- Limites de débit et licence formelle de GDELT non confirmées sur une page officielle en 2026.

---

## 5. ESG souverain (Banque mondiale, ND-GAIN, Yale EPI)

### Takeaway
Le portail ESG souverain de la Banque mondiale est la meilleure option (API sans clé, 80 indicateurs, mis à jour le 24 juin 2026, CC BY 4.0 par défaut). ND-GAIN 2026 est téléchargeable gratuitement, sans licence nommée. L'EPI 2026 de Yale est sous **CC BY-NC-SA 4.0**, avec interdiction explicite d'usage commercial.

### Cited Findings
- **Banque mondiale, source 75 « Environment, Social and Governance (ESG) Data »** : `lastupdated 2026-06-24`, **80 indicateurs** ; API `https://api.worldbank.org/v2/sources/75/indicators?format=json` — [API Banque mondiale](https://api.worldbank.org/v2/sources?format=json&per_page=100) (vérifié API 2026-11-14)
- Licence par défaut des jeux produits par la Banque mondiale : CC BY 4.0, avec exceptions possibles par jeu — [datacatalog.worldbank.org/public-licenses](https://datacatalog.worldbank.org/public-licenses) ; téléchargement en masse — [esgdata.worldbank.org/data/download](https://esgdata.worldbank.org/data/download)
- Client Python wbgapi 1.0.14 (MIT, 2026-02-27) — [PyPI wbgapi](https://pypi.org/pypi/wbgapi/json)
- **ND-GAIN** : zip `ndgain_countryindex_2026.zip`, CSV, 180+ pays, 20+ ans, mise à jour annuelle ; valeurs brutes, interpolées et normalisées ; aucune licence nommée (« free and open-access tool ») ; citation demandée — [ND-GAIN download](https://gain.nd.edu/our-work/country-index/download-data/)
- **Yale EPI 2026** : publié le 9 juillet 2026, 177 pays ; scores XLSX et données brutes en ZIP ; « released under a Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License. Neither the 2026 EPI nor the data available on our downloads page may be used for commercial purposes » (accords avec les partenaires de données) — [EPI 2026 FAQ](https://epi.yale.edu/node/51226) ; [EPI Downloads](https://epi.yale.edu/downloads) ; [communiqué](https://epi.yale.edu/downloads/epi2026pressrelease2026-07-09.pdf)

### Inferences
- Pour les ETF pays et internationaux du portefeuille (ou le risque pays des émetteurs), la Banque mondiale suffit et est redistribuable avec attribution. L'EPI ne devrait servir qu'en contexte d'affichage non commercial, voire pas du tout si le livrable est jugé commercial.

### Gaps
- Licence exacte de ND-GAIN (page copyright de Notre Dame non lue).
- Liste précise des 80 indicateurs ESG de la Banque mondiale non extraite (disponible via l'API).

---

## 6. Méthodologies ESG des ETF (Vanguard ESGV / FTSE US All Cap Choice, iShares ESGU)

### Takeaway
Les règles d'exclusion de l'indice d'ESGV (**FTSE Global Choice Index Series, Ground Rules v5.0, août 2026**) sont publiques et assez précises pour être **reproduites comme règles explicables**. Les sous-secteurs ICB « Pipelines », « Integrated Oil and Gas », « Crude Producers » et « Refining and Marketing » sont exclus, ainsi que les sociétés tirant au moins 5 % de leurs revenus des sables bitumineux. Cela exclut de fait ENB, CNQ et XOM. Les *données* sous-jacentes (Sustainalytics Product Involvement et Global Standards Screening, ICB) restent propriétaires.

### Cited Findings
- Document « FTSE Global Choice Index Series, Ground Rules **v5.0, August 2026** » ; la série inclut le **FTSE US All Cap Choice Index** (univers de départ : FTSE USA All Cap Index) — [FTSE Global Choice ground rules PDF](https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-choice-index-series-ground-rules.pdf) (texte extrait du PDF 2026-11-14)
- Exclusions par produit (Tableau 4) : **nucléaire et uranium > 0 % des revenus** ; **propriété de réserves prouvées ou probables de charbon, pétrole ou gaz (≥ 50 % de détention)** ; **sociétés classées dans les sous-secteurs ICB 60101010 Crude Producers, 60101020 Oil Refining and Marketing, 60101030 Oil Equipment & Services, 60101015 Offshore Drilling, 60101035 Pipelines, 60101000 Integrated Oil and Gas, 65102020 Gas Distribution** ; ≥ 5 % des revenus pour l'exploration, la production, le raffinage, le transport ou le stockage de pétrole et gaz, pour les services dédiés, pour l'Arctique et pour **l'extraction de sables bitumineux** ; tabac > 0 % (fabrication) ou ≥ 5 % (fourniture) ; services au jeu ≥ 10 % — [FTSE Global Choice ground rules](https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-choice-index-series-ground-rules.pdf)
- Exclusions par conduite : principes 1–10 du Pacte mondial de l'ONU (statut « non-compliant » pour les grandes et moyennes capitalisations ; « watchlist ou non-compliant » pour les petites) ; liste UFLPA ; diversité (femmes au conseil, politiques et systèmes de gestion de la diversité) ; armes (chimiques, biologiques, à sous-munitions, mines, nucléaires, conventionnelles, armes à feu civiles) ; vice (divertissement adulte, alcool, jeu, tabac, cannabis). « **Companies with incomplete product and conduct involvement data are excluded from the index** » — [FTSE Global Choice ground rules](https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-choice-index-series-ground-rules.pdf)
- Données utilisées : « Sustainalytics Product Involvement data » pour les produits, « Sustainalytics Global Standards Screening (GSS) » pour la conduite, listes d'exclusion FTSE pour la diversité — [FTSE Global Choice ground rules](https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-choice-index-series-ground-rules.pdf)
- FTSE indique que le FTSE US All Cap Choice Index sert de référence à un ETF Vanguard coté aux États-Unis — [FTSE Global Choice](https://www.lseg.com/en/ftse-russell/indices/global-choice)
- **iShares ESGU** : suit le MSCI USA Extended ESG Focus Index ; exclusions : armes à feu civiles, armes controversées, tabac, **charbon thermique et sables bitumineux** ; frais 0,15 % ; optimisation vers les sociétés les mieux notées par MSCI (source secondaire) — [iShares ESGU](https://www.ishares.com/us/products/286007/ESGU) ; [BlackRock ESGU](https://www.blackrock.com/us/individual/products/286007/ishares-esg-aware-msci-usa-etf)

### Inferences
- **Règle explicable pour Mateo** : « Exclu, car l'indice de l'ESGV (FTSE US All Cap Choice v5.0) exclut tout le sous-secteur Pipelines (ENB), Integrated Oil & Gas (XOM) et les producteurs de brut ou d'exploitation de sables bitumineux (CNQ) ». C'est une citation de méthodologie publique, pas un score propriétaire. Le classement ICB exact est propriétaire, mais les codes SIC de la SEC (section 7) fournissent un substitut public cohérent : ENB SIC 4610 « Pipe Lines », XOM SIC 2911 « Petroleum Refining », CNQ SIC 1311 « Crude Petroleum & Natural Gas ».
- La règle d'exclusion par défaut des sociétés aux données incomplètes signifie que l'absence d'un titre dans ESGV n'implique pas toujours une controverse. A5 doit le documenter comme limite.
- Comparer ESGV à SPY revient en pratique à mesurer l'effet de ces exclusions (énergie, nucléaire, vice, armes). Un écart de rendement est attribuable surtout au poids du secteur énergie et des grandes valeurs exclues (inférence à valider avec les avoirs).

### Gaps
- La page produit Vanguard d'ESGV (benchmark, nombre de titres, fichier d'avoirs) n'a pas pu être lue (contenu JavaScript). Le lien ESGV ↔ FTSE US All Cap Choice repose sur la mention FTSE « un ETF Vanguard » et sur des connaissances générales (non revérifié nov. 2026).
- Le document de méthodologie MSCI de l'indice d'ESGU (seuils exacts) n'a pas été lu.
- Conditions d'utilisation des fichiers d'avoirs Vanguard et iShares non vérifiées.

---

## 7. Classification sectorielle et industrielle (GICS, SIC, NAICS/SCIAN, ICB, TRBC, Yahoo, FinanceDatabase)

### Takeaway
GICS (MSCI/S&P) et ICB (FTSE Russell) sont **propriétaires et sous licence**. Les alternatives gratuites et réutilisables sont les **codes SIC de la SEC** (API EDGAR `submissions`, sans clé), le **SCIAN/NAICS Canada 2022** (Statistique Canada, licence ouverte ; version 2027 annoncée pour janvier 2027), les codes NAICS présents dans le GHGRP et l'EPA, et **FinanceDatabase** (MIT, taxonomie « indépendante » à 11 secteurs).

### Cited Findings
- **GICS** : « exclusive property of MSCI and S&P Dow Jones Indices », marque de service ; les conditions vendeur interdisent la redistribution à des tiers et l'usage de GICS pour créer des produits ou indices sans licence — [MSCI GICS Overview](https://www.msci.com/downloads/documents/indexes/gics/MSCI%20GICS%20Overview.pdf) ; [Octus GICS terms (oct. 2024)](https://octus.com:443/terms-gics) ; [FIS GICS Third-Party Data Terms](https://www.fisglobal.com/-/media/fisglobal/files/PDF/policy/third-party-terms/GICS-Service-Third-Party-Data-Terms.pdf?sc_lang=en)
- Consultation S&P DJI / MSCI annoncée le 17 juillet 2026 sur de possibles changements à la structure GICS — [S&P Global press](https://press.spglobal.com/2026-07-17-S-P-DOW-JONES-INDICES-AND-MSCI-ANNOUNCE-CONSULTATION-ON-POTENTIAL-CHANGES-TO-THE-GLOBAL-INDUSTRY-CLASSIFICATION-STANDARD-GICS-R)
- **SEC SIC via EDGAR** : `https://data.sec.gov/submissions/CIK##########.json` → ENBRIDGE INC SIC 4610 « Pipe Lines (No Natural Gas) », tickers incluant ENB (NYSE) ; EXXON MOBIL CORP SIC 2911 « Petroleum Refining » (champ tickers vide dans ce JSON) ; CANADIAN NATURAL RESOURCES Ltd SIC 1311 « Crude Petroleum & Natural Gas », ticker CNQ (NYSE) ; ownerOrg « 01 Energy & Transportation » — [EDGAR submissions ENB](https://data.sec.gov/submissions/CIK0000895728.json) ; [XOM](https://data.sec.gov/submissions/CIK0000034088.json) ; [CNQ](https://data.sec.gov/submissions/CIK0001017413.json) (vérifié API 2026-11-14)
- **SCIAN/NAICS Canada 2022 v1.0** : 20 secteurs, 99 sous-secteurs, 323 groupes, 695 industries, 922 industries canadiennes ; CSV (structure et éléments) ; **Licence ouverte de Statistique Canada** (identifiant ca-ogl-lgo sur le miroir) ; **SCIAN Canada 2027 v1.0 prévu en janvier 2027** — [open.canada.ca NAICS 2022](https://open.canada.ca/data/en/dataset/980d598c-73c9-4003-b6e1-78a9a3081b6c) ; [StatCan NAICS 2022](https://www.statcan.gc.ca/eng/subjects/standard/naics/2022/v1/index) ; [consultation 2027](https://www.statcan.gc.ca/en/consultation/2023/naics/revising)
- **FinanceDatabase** (Jeroen Bouma) : 121 626 actions et 32 138 ETF (303 507 symboles) ; champs sector, industry_group, industry, country, isin, cusip, figi ; « All categorizations in the database are independently developed and can be freely modified » ; sources : annuaires de bourses, OpenFIGI, SEC EDGAR, etc. ; mises à jour automatiques chaque dimanche ; **licence MIT** ; version 2.5.2 du 2026-11-14 — [GitHub FinanceDatabase](https://github.com/JerBouma/FinanceDatabase) ; [PyPI](https://pypi.org/pypi/financedatabase/json)
- **ICB** : utilisé par FTSE Choice pour les exclusions (codes de sous-secteurs à 8 chiffres) — [FTSE Global Choice ground rules](https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-choice-index-series-ground-rules.pdf)
- **Yahoo sector/industry** : soumis aux CGU Yahoo (usage commercial et automatisé interdits sans permission) — [Yahoo Terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html)

### Inferences
- Classification recommandée pour la base de connaissances : NAICS (installations, via GHGRP, INRP et EPA) + SIC (émetteurs SEC) + secteur FinanceDatabase (MIT) pour les tickers TSX sans dépôt SEC. Il ne faut **jamais stocker de codes GICS**, même ceux affichés gratuitement sur des sites tiers.
- Pour les titres TSX sans formulaire SEC (beaucoup de petites capitalisations canadiennes), le SIC n'existe pas. FinanceDatabase ou une classification SCIAN attribuée manuellement est alors nécessaire.

### Gaps
- Licence et accès de TRBC (LSEG) : non recherchés (probablement sous licence, non vérifié).
- Politique d'« accès équitable » EDGAR (limite d'environ 10 requêtes/s, User-Agent déclaré) : non revérifiée en nov. 2026 — [SEC accessing EDGAR data](https://www.sec.gov/os/accessing-edgar-data).
- Licence des listes de sous-secteurs ICB : non vérifiée.

---

## 8. Données climatiques et risque physique (ECCC MSC GeoMet, Régie de l'énergie du Canada, NOAA, OS-Climate physrisk)

### Takeaway
Le Canada est bien servi : l'API OGC `api.weather.gc.ca` (104 collections : observations climatiques, normales, AHCCD, projections CMIP5, hydrométrie) est sous une licence ECCC qui autorise l'usage commercial. Les données d'incidents pipeliniers de la Régie de l'énergie du Canada (REC/CER, licence OGL) sont directement pertinentes pour Enbridge. Côté américain, la base « Billion-Dollar Disasters » de la NOAA a été retirée (aucune mise à jour au-delà de 2024).

### Cited Findings
- **MSC GeoMet – OGC API** : 104 collections, dont `climate-daily`, `climate-hourly`, `climate-monthly`, `climate-normals` (1981–2010), `ahccd-*`, `ltce-*`, `climate:cmip5:projected:*`, `hydrometric-*` — [api.weather.gc.ca/collections](https://api.weather.gc.ca/collections?f=json) (vérifié API 2026-11-14)
- **Licence** : « Environment and Climate Change Canada Data Services End-use Licence », v2.1.1 (août 2026) ; droits mondiaux et gratuits, « including for commercial purposes » ; attribution « Data Source: Environment and Climate Change Canada » ; aucune approbation officielle implicite ; alertes reproduites sans altération — [Licence MSC open data](https://eccc-msc.github.io/open-data/licence/readme_en/)
- Clients Python : owslib 0.36.0 (BSD-3, 2026-06-04) ; env-canada 0.20.5 (MIT, 2026-10-03) — [PyPI owslib](https://pypi.org/pypi/owslib/json) ; [PyPI env-canada](https://pypi.org/pypi/env-canada/json)
- **REC/CER, « Pipeline Incident Data »** : incidents (avec causes) sur les pipelines de compétence fédérale depuis 2008, CSV EN/FR + dictionnaires, licence OGL-Canada, mise à jour trimestrielle (un miroir tiers indique mensuelle, avec modification au 2026-04-01) ; pipelines provinciaux non couverts — [open.canada.ca CER incidents](https://open.canada.ca/data/dataset/7dffedc4-23fa-440c-a36d-adf5a6cc09f1) ; [Incidents at CER-regulated pipelines](https://open.canada.ca/data/en/dataset/fd17f08f-f14d-433f-91df-c90a34e1e9a6) ; [carte interactive](https://www.cer-rec.gc.ca/en/safety-environment/industry-performance/interactive-pipeline/)
- **NOAA Billion-Dollar Weather and Climate Disasters** : retrait annoncé en mai 2025, aucune mise à jour au-delà de 2024 ; archives conservées ; 403 catastrophes depuis 1980 (> 2 900 G$) — [Utility Dive](https://www.utilitydive.com/news/noaa-stops-tracking-climate-disasters-billion-dollar-database/748107/) ; [PBS](https://www.pbs.org/newshour/science/u-s-stops-tracking-costs-of-extreme-weather-disasters-fueled-by-climate-change)
- **OS-Climate physrisk** : bibliothèque Apache-2.0 ; physrisk-lib 1.11.0 (2026-11-08) ; indicateurs d'aléas hébergés sur AWS Open Data (« no restrictions on the use of this data », selon le registre) ; méthodologie d'octobre 2025 (brouillon) — [PyPI physrisk-lib](https://pypi.org/pypi/physrisk-lib/json) ; [AWS Open Data OS-Climate physrisk](https://registry.opendata.aws/os-climate-physrisk/) ; [Méthodologie](https://physrisk.readthedocs.io/en/stable/_static/PhysicalRiskMethodology.pdf)

### Inferences
- Les incidents CER fournissent une métrique de controverse opérationnelle **gratuite, officielle et propre à Enbridge** (déversements, causes). Elle est plus défendable qu'un score de controverse propriétaire.
- Les données physiques (GeoMet, physrisk) sont utiles pour du contexte ou de la démonstration, mais relier un risque physique à un ticker exige des géolocalisations d'actifs (GHGRP lat/long, Climate TRACE centroïdes).

### Gaps
- API NOAA NCEI CDO (jeton, limites de débit) non revérifiée en 2026.
- Couverture de propriété de la REC (nom de l'exploitant ↔ société mère) non examinée.

---

## 9. Clients Python et serveurs MCP utilisables par l'agent A5

### Takeaway
Les clients Python sont matures et à jour pour presque toutes les sources ouvertes (edgartools, wbgapi, owslib, financedatabase, followthemoney, gdeltdoc, physrisk-lib). Les serveurs MCP ESG existants sont tiers, peu audités ou payants. Pour Climate TRACE, Envirofacts, GHGRP et NPRI, de simples appels HTTP suffisent.

### Cited Findings
- Versions PyPI au 14 novembre 2026 : edgartools 6.1.0 (MIT, 2026-11-12) ; wbgapi 1.0.14 (MIT) ; owslib 0.36.0 ; financedatabase 2.5.2 (MIT, 2026-11-14) ; yfinance 1.8.0 (Apache-2.0) ; finnhub-python 2.4.30 ; followthemoney 4.11.3 (MIT) ; nomenklatura 4.17.6 ; gdeltdoc 1.12.0 (avril 2025) ; physrisk-lib 1.11.0 (Apache-2.0) ; env-canada 0.20.5 (MIT) ; sec-edgar-api 1.1.0 (2023, peu maintenu) — [API JSON PyPI](https://pypi.org/pypi/edgartools/json) (vérifié 2026-11-14)
- Serveurs MCP repérés : `climate-risk-mcp-server` (utilise Climate TRACE sans clé) ; plusieurs serveurs SEC EDGAR sans clé ; « ESG Supply Chain Risk MCP » sur Apify (OpenSanctions/OFAC, LEI, gouvernance Banque mondiale), **payant à 350 $ / 1 000 évaluations** ; Zei World MCP ; CSRD Compliance MCP — [PyPI climate-risk-mcp-server](https://pypi.org/project/climate-risk-mcp-server/) ; [Apify ESG Supply Chain Risk MCP](https://apify.com/ryanclinton/esg-supply-chain-risk-mcp) ; [Glama zei-world-mcp](https://glama.ai/mcp/servers/mcorbe/zei-world-mcp)
- Les CGU MSCI interdisent explicitement les « MCP servers or connectors » non autorisés — [MSCI Terms of Use](https://www.msci.com/legal/terms-of-use)

### Inferences
- Pour la traçabilité exigée par le brief (origine, méthode, date, traitement, licence), il vaut mieux qu'A5 appelle directement les API officielles avec un module maison léger. Chaque enregistrement Open Knowledge Format (OKF) porterait alors `source_url`, `retrieved_at`, `data_version` (ex. Climate TRACE v5.12.0), `licence` et `redistribution`, plutôt que de passer par des MCP tiers opaques.

### Gaps
- Fiabilité et licence des serveurs MCP tiers non auditées.

---

## 10. Évaluation honnête : ce que les données ESG gratuites permettent, ou non, pour Mateo

### Takeaway
Les sources gratuites permettent un **filtrage ESG factuel, explicable et sourcé** : émissions de scope 1 par installation au Canada, appartenance à des listes d'exclusion publiques (NBIM), reproduction des règles d'exclusion de l'ESGV, cibles SBTi, incidents CER, sanctions, radar GDELT. Elles **ne permettent pas** de produire légalement un *score ESG* comparable à MSCI ou Sustainalytics, ni d'obtenir le scope 3, ni une attribution complète installation → société mère. Plusieurs jeux d'ONG sont NC ou à partage interdit, ce qui est risqué dans un datathon commandité par une banque.

### Cited Findings
- Contexte réglementaire canadien : les ACVM ont suspendu le 23 avril 2025 les travaux sur le règlement de divulgation climatique NI 51-107 (pas en vigueur) ; les normes CSDS 1 et 2 du CCNID (CSSB) restent volontaires ; un guide d'août 2026 indique la pause toujours en place — [Torys, avril 2025](https://www.torys.com/en/our-latest-thinking/publications/2025/04/csa-climate-disclosure-rule-on-hold) ; [Cassels](https://cassels.com/insights/csa-pauses-climate-related-and-diversity-related-disclosure-projects/) ; [OneStopESG](https://onestopesg.com/esg-resources/canada-csa-climate-disclosure-issuers). Des pages tierces (greenplaces.com) affirmant l'inverse sont contredites par ces sources — [greenplaces](https://greenplaces.com/regulations/national-instrument-51-107)
- Contexte américain : GHGRP en suspens (section 1) ; base NOAA Billion-Dollar retirée (section 8).
- Matrice de licences (synthèse des fiches ci-dessus) :

| Source | Licence / conditions | Usage commercial | Redistribution dans la base partagée | Source |
|---|---|---|---|---|
| GHGRP Canada, INRP, RIN | OGL-Canada | Oui | Oui, avec attribution | [open.canada.ca](https://open.canada.ca/data/en/dataset/a8ba14b7-7f23-462a-bdbb-83b0ef629823) |
| MSC GeoMet | Licence ECCC v2.1.1 | Oui | Oui, avec attribution | [licence MSC](https://eccc-msc.github.io/open-data/licence/readme_en/) |
| CER incidents | OGL-Canada | Oui | Oui | [open.canada.ca](https://open.canada.ca/data/dataset/7dffedc4-23fa-440c-a36d-adf5a6cc09f1) |
| SCIAN/NAICS Canada | Licence ouverte StatCan | Oui | Oui | [open.canada.ca](https://open.canada.ca/data/en/dataset/980d598c-73c9-4003-b6e1-78a9a3081b6c) |
| Climate TRACE | CC BY 4.0 (sauf jeux externes ; champs « license restricted ») | Oui | Oui, avec attribution | [terms](https://climatetrace.org/terms) |
| Banque mondiale ESG | CC BY 4.0 (défaut) | Oui | Oui | [public licenses](https://datacatalog.worldbank.org/public-licenses) |
| GEM trackers | CC BY 4.0 (majorité ; exceptions) | Oui (formulaire d'exemption mentionné) | Oui, avec attribution | [GEM](https://globalenergymonitor.org/projects/global-methane-emitters-tracker/download-data/) |
| FinanceDatabase | MIT | Oui | Oui | [GitHub](https://github.com/JerBouma/FinanceDatabase) |
| Net Zero Tracker | CC BY-NC 4.0 | Non | Risqué | [data terms](https://zerotracker.net/data-terms-of-use) |
| OpenSanctions | CC BY-NC 4.0 | Non (licence payante) | Risqué | [licensing](https://www.opensanctions.org/licensing/) |
| Carbon Majors | Non commercial (CG InfluenceMap) | Non | Risqué | [carbonmajors](https://carbonmajors.org/Downloads) |
| Yale EPI 2026 | CC BY-NC-SA 4.0 | Non | Risqué | [EPI FAQ](https://epi.yale.edu/node/51226) |
| TPI | Usages limités ; bots interdits | Non sans licence | Portion non substantielle seulement | [TPI](https://transitionpathwayinitiative.org/use-of-the-centre-s-data) |
| Urgewald GOGEL | Recherche interne NC ; pas de partage externe | Non | **Non** | [GOGEL T&C](https://gogel.org/terms-conditions-without-identifiers) |
| Yahoo / Sustainalytics | CGU Yahoo : pas d'usage commercial ni de robots | Non | **Non** | [Yahoo Terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) |
| MSCI ESG | Interne non productif ; agents IA et MCP interdits | Non | **Non** | [MSCI ToU](https://www.msci.com/legal/terms-of-use) |
| LSEG ESG | Approbation écrite même en NC | Non sans licence | **Non** | [LSEG](https://www.lseg.com/en/data-analytics/sustainable-finance/esg-scores) |
| GICS | Propriété MSCI/S&P, sous licence | Non sans licence | **Non** | [Octus GICS terms](https://octus.com:443/terms-gics) |

### Inferences
- **Ce qui est faisable et défendable pour Mateo** :
  1. Règle d'exclusion « style ESGV » sur SIC/NAICS publics (ENB 4610, XOM 2911, CNQ 1311), citant les Ground Rules FTSE v5.0 comme justification méthodologique.
  2. Preuve externe pour CNQ : exclusion NBIM pour émissions de GES inacceptables.
  3. Intensité et volume de scope 1 au Canada via le GHGRP 2024 (CNQ 18,57 Mt ; Imperial 13,57 Mt comme proxy de l'empreinte canadienne de XOM ; Enbridge 0,75 Mt sous son propre nom).
  4. Statut des cibles SBTi (ISIN/LEI).
  5. Incidents pipeliniers CER pour ENB.
  6. Radar de controverses GDELT sur 3 mois.
  7. Comparaison ESGV/SPY expliquée par les exclusions.
- **Ce qui n'est pas faisable légalement ou proprement** : un score ESG agrégé type Sustainalytics, MSCI ou LSEG ; le scope 3 (non publié dans les registres) ; une consolidation fiable installation → société mère sans table de propriété maison (le GHGRP donne le déclarant, pas la société mère ; Climate TRACE attribue incomplètement) ; des données américaines plus récentes que 2023 (EPA).
- **Ambiguïté « non commercial »** : la PolyFinances est une compétition étudiante, mais commanditée par une banque et AWS, et le livrable pourrait être réutilisé. Il est prudent de traiter les sources NC comme « consultation et démonstration, sans versement en masse » : stocker seulement des drapeaux dérivés avec attribution, ou obtenir une permission écrite. GOGEL doit être exclue de la base partagée.
- Chaque fait ESG dans la base OKF devrait porter `as_of` (ex. GHGRP « année de référence 2024, fichier du 2026-07-24 » ; Climate TRACE « v5.12.0, 2026-10-28 » ; NBIM « liste du 11 août 2026, décisions à novembre 2025, lignes directrices intérimaires »), car plusieurs sources sont figées ou en suspens.

### Gaps
- Statut de la règle climat de la SEC en 2026 : non recherché.
- SEDAR+ : CGU inaccessibles (403) ; existence d'une API ou d'un flux en masse et conditions d'accès automatisé non vérifiées. Recommandation par défaut : téléchargement manuel des rapports de durabilité et notices annuelles, sans robot.
- Aucune étude académique récente (2025–2026) sur les limites des données ESG gratuites n'a été recherchée, faute de temps.
