# Les API officielles portent la base générale

La base générale d'AlphaForge peut reposer presque entièrement sur des API publiques officielles, gratuites, le plus souvent sans clé et redistribuables avec attribution. On y trouve la Banque du Canada (Valet), Statistique Canada (WDS, SDMX, calendrier JSON), FRED/ALFRED, SEC EDGAR, le Trésor américain, la Fed de New York, la BCE, le FMI, l'OCDE, la BRI et la Banque mondiale, ainsi que les registres d'émissions (GHGRP, Climate TRACE) et les flux RSS des banques centrales et des gouvernements. Environ deux cents sources ont été passées en revue au 14 novembre 2026, et c'est la licence qui décide, pas le quota. Comme la base est commune à tous les utilisateurs, toute donnée qu'A5 y verse par A6 est de fait redistribuée. Or presque tous les paliers gratuits commerciaux limitent l'usage au personnel ou à l'interne et interdisent la redistribution : Yahoo/yfinance, Alpha Vantage, EODHD, Tiingo, Finnhub, Twelve Data, Massive, CoinPaprika et les agrégateurs de nouvelles ([Tiingo](https://www.tiingo.com/about/pricing) ; [Finnhub](https://finnhub.io/terms-of-service)). Quatre trous restent ouverts au gratuit. Pour les prix TSX, il n'y a que yfinance, qui est non officiel et freiné depuis les IP cloud. Pour les fondamentaux des sociétés canadiennes non intercotées, SEDAR+ interdit toute automatisation, et ATD comme CSU sont absents d'EDGAR. Les avoirs des FNB canadiens ne sont publiés que dans des fichiers d'émetteurs non redistribuables. Enfin, aucune source gratuite et légale ne fournit de scores ESG. Pour le point-in-time, seules quelques sources donnent des millésimes natifs : ALFRED, les tableaux « temps réel » de StatCan, les millésimes du FMI, de l'OCDE et de la BCE, la Philly Fed et les dates de dépôt EDGAR. Ailleurs, A5 doit horodater et archiver chaque collecte dès maintenant, car un historique de révisions qu'on n'a pas archivé à temps ne se rattrape pas.

## La licence, et non le quota, décide de ce qui entre dans la base commune

Le fait que la base soit partagée change l'ordre des priorités. Les quotas des sources officielles sont larges, voire absents : Statistique Canada tolère 25 requêtes par seconde par IP, et Frankfurter annonce « no monthly or daily caps » ([Guide WDS](https://www.statcan.gc.ca/en/developers/wds/user-guide) ; [Frankfurter](https://frankfurter.dev/)). À l'inverse, les licences des paliers gratuits commerciaux bloquent presque toutes la redistribution. Les conditions lues le 14 novembre 2026 se rangent en trois régimes, et chacun appelle un traitement différent par A6.

**Premier régime : réutilisation ouverte, y compris commerciale, avec attribution.**

- La Licence ouverte de Statistique Canada permet de « use, reproduce, publish, freely distribute, or sell » l'information. Elle impose une mention du type « Source: Statistics Canada, name of product, reference date » ([Licence ouverte StatCan](https://www.statcan.gc.ca/en/terms-conditions/open-licence)).
- L'OGL–Canada 2.0, qui couvre Finances Canada, le BSIF, la SCHL, la REC et ISDE sur le portail fédéral, vaut « including for commercial purposes » ([OGL–Canada 2.0](https://open.canada.ca/en/open-government-licence-canada)).
- La Banque du Canada permet de « freely use, copy, distribute and transmit » son contenu, à condition de la citer et de signaler les modifications. Le contenu de tiers est exclu ([Conditions BdC](https://www.bankofcanada.ca/terms/)).
- Le Fiscal Data du Trésor est « free, without restriction » ([Fiscal Data](https://fiscaldata.treasury.gov/api-documentation/)), et le contenu de la Fed Board relève du domaine public ([Fed disclaimer](https://www.federalreserve.gov/disclaimer.htm)).
- La BCE autorise l'usage commercial si la source est citée et les données ne sont pas modifiées ([politique SEBC](https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html)).
- La Banque mondiale est sous CC BY 4.0 ([Banque mondiale](https://data.worldbank.org/summary-terms-of-use)), tout comme l'OCDE pour ses contenus publiés depuis le 1er juillet 2024 ([OCDE](https://www.oecd.org/en/about/news/press-releases/2024/07/oecd-data-publications-and-analysis-become-freely-accessible.html)).

**Deuxième régime : ouvert, mais sous conditions qui touchent l'interface autant que la base.**

- FRED exige d'afficher « This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis ». Il interdit de répliquer l'expérience de FRED et renvoie au propriétaire d'origine pour toute série étiquetée « Copyrighted » ([Conditions FRED](https://fred.stlouisfed.org/docs/api/terms_of_use.html)).
- Census et NASS imposent une mention de non-endorsement comparable ([Census](https://www.census.gov/data/developers/about/terms-of-service.html) ; [NASS](https://quickstats.nass.usda.gov/api)).
- La Banque du Japon exige une notification par courriel et une mention de crédit ([BoJ](https://www.stat-search.boj.or.jp/info/api_notice_en.pdf)).
- Le FMI demande d'écrire à copyright@imf.org pour tout usage commercial. Il « prohibits bulk download of information by automated technology without explicit permission » ([FMI](https://www.imf.org/en/about/copyright-and-terms)).
- Eurostat interdit l'usage commercial de ses données d'origine non européenne ([Eurostat](https://ec.europa.eu/eurostat/help/copyright-notice)).
- Canada.ca ne permet que la reproduction non commerciale ([Canada.ca](https://www.canada.ca/en/transparency/terms.html)).

**Troisième régime : usage personnel ou interne.**

- yfinance rappelle que l'API Yahoo est « intended for personal use only » ([yfinance](https://pypi.org/project/yfinance/)). Les conditions Yahoo interdisent d'accéder aux services ou de les réutiliser « for any commercial purpose », ainsi que les robots non autorisés ([CGU Yahoo](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html)).
- Twelve Data exige un plan Business de toute organisation, « even if the data is only used internally » ([Twelve Data](https://twelvedata.com/pricing-business)).
- Finnhub interdit de partager « data or derived results » sans accord écrit ([Finnhub](https://finnhub.io/terms-of-service)).
- MSCI interdit, depuis le 15 juillet 2026, les « AI agents, MCP servers or connectors » non autorisés ([MSCI](https://www.msci.com/legal/terms-of-use)).

| Régime | Sources typiques | Ce que la base générale peut contenir |
|---|---|---|
| Ouvert, redistribuable | BdC, StatCan, OGL–Canada, Fed Board, Trésor, BCE, Banque mondiale, OCDE, SEC, GHGRP, Climate TRACE, GDELT (métadonnées) | Séries brutes et textes publics, avec la licence et l'attribution en front-matter YAML |
| Ouvert, conditionnel | FRED, Census, NASS, BLS, FMI, Eurostat, BoJ, Canada.ca | Séries brutes, avec les mentions obligatoires affichées dans l'interface et une vérification de l'étiquette de droits de chaque série |
| Personnel ou interne | Yahoo, Alpha Vantage, EODHD, Tiingo, Twelve Data, Finnhub, Massive, CoinPaprika, API de nouvelles, fichiers d'avoirs des émetteurs de FNB | Cache isolé hors de la base ; seuls des signaux dérivés agrégés et des liens y entrent |

Concrètement, chaque fiche OKF doit porter un champ `redistribution` (oui, non ou inconnu), et A6 doit refuser toute fiche marquée « non » dans la base générale. Il reste une ambiguïté sur le statut du datathon. C'est une compétition étudiante, mais elle est commanditée par la Banque Nationale et AWS, et les notes jugent prudent de traiter les clauses « non commercial » comme « démonstration sans versement en masse ». Une piste concrète : Alpha Vantage annonce un accès illimité pour les projets open source ou éducatifs vérifiés, au lieu de 25 requêtes par jour ([Alpha Vantage support](https://www.alphavantage.co/support/)). Il faut le demander. Les mentions de FRED, Census, NASS, BLS (« BLS.gov cannot vouch for the data… ») et BoJ doivent figurer dans le pied de page d'AlphaForge, pas seulement dans les métadonnées ([BLS ToS](https://www.bls.gov/developers/termsOfService.htm)).

Le second risque transversal est l'adresse IP. A5 tourne sur Bedrock/AgentCore, donc depuis des IP AWS.

- yfinance renvoie des 429 (`YFRateLimitError`) plus fréquents depuis les IP cloud partagées. Une issue TradingAgents montre qu'un 429 peut être interprété à tort comme un symbole radié ([PythonAnywhere](https://www.pythonanywhere.com/forums/topic/36371/) ; [TradingAgents #1386](https://github.com/TauricResearch/TradingAgents/issues/1386)).
- Binance répond 451 aux instances EC2 situées aux États-Unis ([forum Binance](https://dev.binance.vision/t/api-error-451-unavailable-for-legal-reasons/13828)).
- La SEC renvoie 403 à toute requête sans User-Agent déclaré ([SEC](https://www.sec.gov/about/webmaster-frequently-asked-questions)).
- Aucun blocage n'est documenté pour Valet ni WDS, mais ils n'ont pas été testés depuis AWS.

Il faut donc un test de fumée depuis l'environnement AgentCore, avant toute démonstration.

## Valet et WDS couvrent la macroéconomie canadienne sans clé ni frais

**Valet (Banque du Canada).** Valet expose **2 616 groupes et 16 380 séries**, en JSON, CSV ou XML. La Banque précise : « No registration is required… You do not need an access key » et « There is no cost » ([Valet groups](https://www.bankofcanada.ca/valet/lists/groups/json) ; [guide Valet](https://www.bankofcanada.ca/valet-api-how-to/)). Aucune limite de débit n'est chiffrée, mais les conditions interdisent de contourner les limites que la Banque impose ([Conditions BdC](https://www.bankofcanada.ca/terms/)). Le guide recommande un back-off et la mise en cache des données quotidiennes ([guide Valet](https://www.bankofcanada.ca/valet-api-how-to/)). Les taux de change quotidiens sont publiés « once each business day by 16:30 ET » ([spécification Valet](https://www.bankofcanada.ca/valet/static/swagger/api-en.yml)).

Au-delà du jeu de départ (USD/CAD, 2 et 10 ans, taux directeur), Valet couvre :

- CORRA, avec 14 séries : volumes, centiles, statut de publication et un groupe `CORRA_TRANSPARENCY` qui résume les erreurs détectées après publication ;
- les bons du Trésor de 1 mois à 1 an ;
- les rendements de référence de 2 ans à long terme et les obligations à rendement réel ;
- les adjudications `AUC_*` ;
- l'IPPB (BCPI) ;
- l'Enquête sur les perspectives des entreprises ;
- les attentes d'inflation des ménages (CSCE) ;
- l'enquête auprès des responsables du crédit ;
- les taux administrés des banques à charte ([Valet groups](https://www.bankofcanada.ca/valet/lists/groups/json)).

Valet a une faiblesse pour le point-in-time : une observation ne contient que `{"d": date de référence, "v": valeur}`, sans date de publication. L'IPC y est daté du premier jour du mois de référence (2026-09-01), alors que StatCan l'a diffusé le 19 octobre ([observations IPC](https://www.bankofcanada.ca/valet/observations/CPI_TRIM,CPI_MEDIAN,CPI_COMMON,V41690973/json?recent=2)). Les groupes publiés par édition servent toutefois de millésimes de fait : `MPR_2024M04_*` à `MPR_2026M10_*` pour le Rapport sur la politique monétaire, `BOS_2026Q3_*`, `CSCE_2026Q3_*`, et les projections du personnel `SWP-*`, dont le dernier millésime remonte à 2019T4 ([SWP-GDP2019Q4](https://www.bankofcanada.ca/valet/observations/SWP-GDP2019Q4/json)). Enfin, les séries IPC de Valet sont « as published by Statistics Canada ». C'est du contenu de tiers au sens des conditions de la Banque : il vaut mieux citer les deux institutions, ou prendre l'IPC directement dans WDS ([Valet CPI_MONTHLY](https://www.bankofcanada.ca/valet/groups/CPI_MONTHLY/json)).

**WDS (Statistique Canada).** Le Web Data Service sert **8 282 tableaux**, sans clé, avec une limite de 50 requêtes par seconde pour le serveur et de 25 par IP. Des codes 409 peuvent apparaître entre minuit et 8 h 30 HE, pendant la mise à jour quotidienne ([liste des tableaux](https://www150.statcan.gc.ca/t1/wds/rest/getAllCubesListLite) ; [Guide WDS](https://www.statcan.gc.ca/en/developers/wds/user-guide)). Chaque point porte un `releaseTime`, mais c'est la date de la **dernière** diffusion, écrasée à chaque révision. La démonstration en direct est nette : pour le PIB mensuel (v65201210), tous les points de 2025-01 à 2026-08 portent `releaseTime = 2026-10-30T08:30`, et non leur date de première publication ([WDS PIB](https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorByReferencePeriodRange?vectorIds=%2265201210%22&startRefPeriod=2026-01-01&endReferencePeriod=2026-03-01)).

Pour reconstituer le passé, StatCan propose 19 tableaux « temps réel » qui contiennent l'historique des révisions, avec des « vintages of data as of January 2015 » ([tableaux temps réel](https://www.statcan.gc.ca/en/dai/btd/rct)). Leur état au 14 novembre 2026 :

- 36-10-0491 (PIB mensuel) : 141 millésimes ;
- 36-10-0431 (PIB en dépenses) : 56 millésimes ;
- 12-10-0165 (commerce) : 35 millésimes ;
- 18-10-0259 (IPC de base) : n'avance plus depuis mai 2026 ;
- 20-10-0081 (détail) : archivé ([getCubeMetadata](https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata)).

Deux autres outils complètent le dispositif. Le calendrier JSON « returns every release date of major economic indicators since March 14, 2012 » ; il comptait 2 882 entrées, dont 79 dates futures, comme l'IPC d'octobre le 16 novembre et le PIB du T3 le 30 novembre 2026 ([calendrier JSON](https://www150.statcan.gc.ca/n1/dai-quo/ssi/homepage/schedule-key_indicators-eng.json)). Le Delta File quotidien contient « all data and metadata released by Statistics Canada each business day », mais seuls les fichiers des deux derniers mois environ restaient téléchargeables ([Delta File](https://www.statcan.gc.ca/en/developers/df)). Il faut donc l'archiver dès maintenant.

Deux pièges techniques s'ajoutent. Les horodatages mélangent l'UTC (`Z`) et l'heure de l'Est sans décalage. Et `getSeriesInfoFromVector` renvoie un objet `null` au lieu d'une erreur pour un vecteur inexistant ([getSeriesInfoFromVector](https://www150.statcan.gc.ca/t1/wds/rest/getSeriesInfoFromVector)).

**Le reste du fédéral et les provinces.** Tout le reste passe par l'API CKAN du portail fédéral, lisible sans clé ([CKAN open.canada.ca](https://open.canada.ca/data/api/3/action/help_show?name=package_search)).

- Le BSIF publie ses bilans bancaires mensuels le 15 de chaque mois. La ressource M4, interrogeable par `datastore_search`, compte 1 571 487 lignes ([BSIF](https://www.osfi-bsif.gc.ca/en/data-forms/open-government-osfi-financial-data/working-open-government-data) ; [DataStore M4](https://open.canada.ca/data/api/3/action/datastore_search?resource_id=d0f6040e-671c-4301-a235-e9e7ba164604&limit=2)).
- Finances Canada publie la Revue financière en ZIP mensuels. Les dates CKAN ne sont pas des dates de publication : les fichiers de janvier à mars 2026 ont tous été ajoutés le 15 juin ([Revue financière 2026](https://open.canada.ca/data/api/3/action/package_show?id=f5f4327b-2a09-484a-a518-64ca26405386)).
- Les mises en chantier de la SCHL sont plus propres via le tableau StatCan 34-10-0158, qui donne un `releaseTime`. Le portail HMIP n'est accessible que par un endpoint non documenté, celui qu'utilise le paquet R `cmhc` ([cmhc R](https://github.com/mountainMath/cmhc/blob/master/R/cmhc.R)).
- Côté provinces, il y a des portails CKAN pour l'Ontario, la Colombie-Britannique, l'Alberta et le Québec, et une API JSON sans clé pour le tableau de bord économique de l'Alberta (PIB depuis 1981) ([Alberta](https://economicdashboard.alberta.ca/dashboard/gdp-at-market-prices/)).
- L'ISQ ne publie que 7 jeux sur Données Québec et n'a pas d'API ([Données Québec](https://www.donneesquebec.ca/recherche/api/3/action/organization_list?all_fields=true&limit=200)).
- L'ACI/CREA n'offre que du XLSX. D'après des extraits de ses conditions, tout usage commercial est interdit sans autorisation écrite. Le NHPI de StatCan (v111955442) est le substitut redistribuable ([CREA](https://www.crea.ca/housing-market-stats/mls-home-price-index/)).

| Source | Accès | Limites | Couverture, historique, fréquence | Licence et réutilisation | Point-in-time |
|---|---|---|---|---|---|
| [BdC Valet](https://www.bankofcanada.ca/valet/docs) | Sans clé ; JSON, CSV, XML | Non chiffrées ; contournement interdit | Canada ; 16 380 séries ; quotidienne à annuelle | Conditions BdC : copie et distribution avec attribution ; contenu de tiers exclu | Date de référence seule ; millésimes de fait par édition (RPM, EPE, CSCE, SWP) |
| [StatCan WDS](https://www.statcan.gc.ca/en/developers/wds/user-guide) | Sans clé ; REST JSON | 50 req/s serveur, 25 req/s par IP ; 409 de 0 h à 8 h 30 HE | Canada et provinces ; 8 282 tableaux (EPA depuis 1976, IPC de base depuis 1949) ; diffusion à 8 h 30 HE | Licence ouverte StatCan, vente permise, mention obligatoire | `releaseTime` écrasé par les révisions ; 19 tableaux temps réel depuis 2015 |
| [StatCan SDMX](https://www.statcan.gc.ca/en/developers/sdmx/user-guide) | Sans clé ; SDMX-ML, SDMX-JSON | Comme WDS | Comme WDS | Licence ouverte StatCan | Comme WDS |
| [Delta File](https://www.statcan.gc.ca/en/developers/df) | ZIP quotidien sans clé | — | Toutes les diffusions du jour ouvrable | Licence ouverte StatCan | Archive quotidienne ; rétention observée d'environ 2 mois |
| [Calendrier JSON](https://www.statcan.gc.ca/en/developers/schedule-key_indicators-eng-json) | Sans clé ; EN et FR | — | Indicateurs clés depuis le 14 mars 2012, dates futures comprises | Licence ouverte StatCan | Dates de publication passées et futures |
| [CKAN fédéral](https://open.canada.ca/data/api/3/action/help_show?name=package_search) (Finances, BSIF, SCHL, REC, ISDE) | Sans clé en lecture ; DataStore pour certaines ressources | Non documentées | BSIF mensuel ; Revue financière mensuelle ; insolvabilité depuis 1987 | OGL–Canada 2.0, usage commercial permis | `metadata_modified` n'est pas une date de publication |
| [CCEI SDMX](https://energy-information.canada.ca/en/resources/web-data-service-user-guide) | Sans clé | — | Énergie au Canada | Non vérifiée | — |
| [API Alberta](https://economicdashboard.alberta.ca/dashboard/gdp-at-market-prices/) | Sans clé ; JSON | — | Alberta, PIB depuis 1981 | Portail sous OGLA | Aucun |
| CKAN provinciaux ([ON](https://data.ontario.ca/api/3/action/package_search?q=fiscal), [C.-B.](https://catalogue.data.gov.bc.ca/api/3/action/package_search?q=fiscal), [QC](https://www.donneesquebec.ca/recherche/api/3/action/organization_list?all_fields=true&limit=200)) | Sans clé | — | 2 967, 3 364 et 1 619 jeux ; certains périmés depuis 2021 | Variable : OGL-ON, cc-by | Aucun |
| [ACI/CREA MLS HPI](https://www.crea.ca/housing-market-stats/mls-home-price-index/) | XLSX, pas d'API | — | Prix des logements | Usage commercial interdit sans permission (extraits) | — |

**Clients et panier minimal.** Ni la BdC ni StatCan ne publient de client Python officiel.

- `stats_can` 3.3.0 est mûr, mais sous GPL-3.0, une licence contaminante si le monolithe est publié ([PyPI stats-can](https://pypi.org/project/stats-can/)).
- `sdmx1` inclut une source StatCan ([sdmx1](https://pypi.org/project/sdmx1/)).
- Le serveur MCP communautaire le plus suivi, `ReyemTech/mcp-canada` (MIT, 62 étoiles, 295 outils), n'est pas officiel ([mcp-canada](https://github.com/ReyemTech/mcp-canada)).

Un client `httpx` maison de quelques dizaines de lignes reste le plus auditable.

Le panier minimal vérifié pour A5 :

| Thème | Séries |
|---|---|
| Taux | `V39079`, `AVG.INTWO`, `TB.CDN.90D.MID`, `BD.CDN.2YR/5YR/10YR/LONG.DQ.YLD`, `BD.CDN.RRB.DQ.YLD` |
| Inflation | v41690973, `CPI_TRIM`, `CPI_MEDIAN`, `CES_C1_*` |
| Activité | v65201210 avec 36-10-0491 ; v62305752 avec 36-10-0431 |
| Emploi | v2062815 |
| Logement | v52300157, v111955442 |
| Consommation et commerce | v1446859483, v87008984 |
| Change et produits de base | `FXUSDCAD`, `CEER_BROADN`, `M.BCPI` |

Tous ces identifiants ont été vérifiés en direct ([getSeriesInfoFromVector](https://www150.statcan.gc.ca/t1/wds/rest/getSeriesInfoFromVector) ; [Valet observations](https://www.bankofcanada.ca/valet/observations/V39079,AVG.INTWO,FXUSDCAD,BD.CDN.2YR.DQ.YLD,BD.CDN.10YR.DQ.YLD,TB.CDN.90D.MID,CEER_BROADN/json?recent=1)).

## ALFRED reste la seule machine à millésimes universelle

### États-Unis : FRED d'abord, les agences en contrôle croisé

**FRED et ALFRED.** FRED exige une clé gratuite de 32 caractères. Les conditions précisent que « Developers should request a distinct API key for each application » et que « All users of an application shall use their own API key » ([clés FRED](https://fred.stlouisfed.org/docs/api/api_key.html)). La lecture la plus prudente est de centraliser la collecte dans A5 (une application, une clé) et de ne jamais exposer cette clé aux sessions des utilisateurs. La limite est de **120 requêtes par minute**, au-delà de quoi l'API renvoie 429 et peut bloquer temporairement ([erreurs FRED](https://fred.stlouisfed.org/docs/api/fred/errors.html)).

ALFRED passe par la même API et c'est son vrai atout :

- `realtime_start = realtime_end = D` renvoie la valeur telle que connue à la date D ;
- `output_type=4` ne renvoie que les premières publications ;
- `vintage_dates` accepte jusqu'à 2 000 dates par requête en JSON ([series/observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)) ;
- `fred/releases/dates` avec `include_release_dates_with_no_data=true` donne aussi le calendrier des publications à venir ([releases/dates](https://fred.stlouisfed.org/docs/api/fred/releases_dates.html)).

L'API v2 (`release/observations`, jusqu'à 500 000 observations) sert au chargement en masse, mais n'expose aucun millésime ([FRED v2](https://fred.stlouisfed.org/docs/api/fred/v2/release_observations.html)). Le connecteur MCP officiel `https://mcp.stlouisfed.org` est gratuit et fonctionne sans clé API, mais demande un compte dédié ; ses cinq outils ne couvrent pas les millésimes ([connecteur MCP FRED](https://fred.stlouisfed.org/help/data/connecting-fred-to-ai-services/FRED-MCP-Connector)). Il est donc bon pour l'exploration par un agent, pas pour l'ingestion versionnée.

Deux pièges de licence tiennent aux séries tierces. Depuis avril 2026, les séries ICE BofA n'ont plus que 3 ans d'historique, et leur « Reproduction… in any form is prohibited » sans accord écrit d'ICE ([FRED BAMLC0A4CBBBEY](https://fred.stlouisfed.org/series/BAMLC0A4CBBBEY)). L'étiquette de droits de chaque série (« Public Domain: Citation Requested », « Copyrighted: Pre-approval Required ») doit être lue et stockée ([FAQ FRED](https://fred.stlouisfed.org/help/fred-faq/frequently_asked_questions/cite)).

**Le shutdown de l'automne 2025.** Le shutdown du 1er octobre au 12 novembre 2025 laisse des trous permanents dans le jeu de départ :

- L'IPC d'octobre 2025 n'existe pas. L'API BLS renvoie `"value":"-"` avec le code `X` « Data unavailable due to the 2025 lapse in appropriations » ([BLS FAQ shutdown](https://www.bls.gov/cpi/additional-resources/2025-federal-government-shutdown-impact-cpi-faq.htm) ; [test BLS](https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0?startyear=2025&endyear=2025)).
- Le BLS ne publie pas de variation sur 12 mois pour octobre 2026 ([avis BLS](https://www.bls.gov/cpi/notices/2026/12m-changes-202610.htm)).
- Le taux de chômage d'octobre 2025 ne sera jamais collecté ([Axios](https://www.axios.com/2025/11/13/government-shutdown-bls-report)).
- Le BEA a annulé l'estimation avancée du PIB du T3 2025 ([BEA](https://www.bea.gov/news/blog/2025-12-10/economic-release-schedule-updates)).

CPIAUCSL et UNRATE, deux séries du kit de départ, sont donc touchées. Les parseurs d'A5 doivent traduire `"-"` en valeur manquante motivée, sans interpolation silencieuse.

**Les agences.** Les agences donnent la provenance primaire et le contrôle croisé.

- BLS v2 permet 500 requêtes par jour, 50 séries et 20 ans par requête, avec une clé à renouveler chaque année ; la v1 sans clé plafonne à 25 requêtes par jour ([FAQ BLS](https://www.bls.gov/developers/api_faqs.htm)).
- Census exige une clé pour toute requête de données depuis le 12 mai 2026 ; sans clé, la réponse est une redirection 302 ([Census EITS](https://www.census.gov/data/developers/data-sets/economic-indicators.html) ; [annonce](https://buttondown.com/crgibbons/archive/census-data-api-to-require-api-key/)).
- La Fed Board ferme son Data Download Program. La fonction Build Your Package est retirée, les paquets préformatés disparaissent le 31 mars 2027 et la page le 1er juillet 2027, avec redirection vers FRED ([DDP H.15](https://www.federalreserve.gov/datadownload/Choose.aspx?rel=H15)). Il ne faut donc construire aucun connecteur DDP.

| Source | Accès | Limites | Couverture, historique, fréquence | Licence et réutilisation | Point-in-time |
|---|---|---|---|---|---|
| [FRED / ALFRED](https://fred.stlouisfed.org/docs/api/fred/) | Clé gratuite, une par application | 120 req/min, puis 429 | États-Unis et séries internationales ; jusqu'à 100 000 observations par requête | Domaine public sauf séries tierces « Copyrighted » ; mention de non-endorsement ; pas de clone de FRED | **Natif** : `realtime_start/end`, `vintage_dates`, `output_type=4`, calendrier `releases/dates` |
| [FRED v2](https://fred.stlouisfed.org/docs/api/fred/v2/index.html) | Clé en en-tête | `limit` 500 000, pagination par curseur | Release complète en masse | Comme FRED | Aucun (`last_updated` seul) |
| [MCP FRED](https://fred.stlouisfed.org/help/data/connecting-fred-to-ai-services/FRED-MCP-Connector) | Compte dédié, sans clé API | Non publiées | 5 outils | Comme FRED | Pas d'outil de millésime |
| [FRED-MD / FRED-QD](https://www.stlouisfed.org/research/economists/mccracken/fred-databases) | CSV | — | Bases macro mensuelle et trimestrielle | Comme FRED | Un fichier par millésime mensuel ; archives 1999–2024 |
| [BLS v2](https://www.bls.gov/developers/api_signature_v2.htm) | Clé (renouvellement annuel) ; v1 sans clé | v2 : 500 req/j, 50 séries, 20 ans ; v1 : 25 req/j ; 50 req/10 s | IPC, emploi, PPI ; 3 dernières années par défaut | Citer la date d'accès et l'avertissement BLS | Note `P` (préliminaire) seulement |
| [BEA](https://apps.bea.gov/API/docs/index.htm) | UserID gratuit | ≈ 100 req, 100 Mo et 30 erreurs par minute (source secondaire) | NIPA, régional, ITA, PIB par industrie | Domaine public, citation demandée | Aucun |
| [Census EITS](https://www.census.gov/data/developers/data-sets/economic-indicators.html) | Clé obligatoire depuis le 12 mai 2026 | Non chiffrées | Ventes au détail, mises en chantier, commerce, stocks | Mention de non-endorsement | Aucun |
| [Fiscal Data](https://fiscaldata.treasury.gov/api-documentation/) | Sans clé | Non documentées | 184 endpoints : dette, taux moyens, change, MTS, DTS | Libre, usage commercial permis | `record_date` seul |
| [NY Fed Markets](https://markets.newyorkfed.org/static/docs/markets-api.yml) | Sans clé | Non documentées | SOFR (depuis avril 2018), EFFR, OBFR, SOMA, repo | Conditions NY Fed ; SOFR et BGCR reposent sur des données DTCC | `revisionIndicator` |
| [Philly Fed RTDSM](https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-for-macroeconomists) | Fichiers Excel | — | Millésimes depuis novembre 1965 (PIB, IPC, chômage, M2…) ; mise à jour mensuelle | Non vérifiée | **Natif** : historique complet des millésimes, 1re, 2e et 3e publications |
| [SPF](https://www.philadelphiafed.org/surveys-and-data/data-files) / [GDPNow](https://www.atlantafed.org/research-and-data/data/gdpnow) / [Cleveland Fed](https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting) | Excel ; séries aussi dans FRED | — | SPF depuis 1968T4 ; archives GDPNow depuis 2011T3 ; nowcasts quotidiens d'inflation | Non vérifiée (Fed régionales) | Historique des prévisions |
| [EIA v2](https://www.eia.gov/opendata/documentation.php) | Clé gratuite passée dans l'URL | 5 000 lignes en JSON ; throttling non chiffré | Pétrole, gaz, électricité | Domaine public, citation datée | Aucun |
| [NASS](https://quickstats.nass.usda.gov/api) / [ERS](https://ers.usda.gov/developer/data-apis/arms-data-api) | Clé ; api.data.gov pour l'ERS | 50 000 lignes par requête (NASS) | Agriculture | Mention de non-endorsement (NASS) | Aucun |
| [DOL ETA-539](https://oui.doleta.gov/unemploy/csv/ar539.csv) | CSV sans clé | — | Demandes hebdomadaires d'assurance-chômage | Non vérifiée | ETA-538 avancé, ETA-539 final |
| [FHFA HPI](https://www.FHFA.gov/DataTools/Downloads/Pages/House-Price-Index-Datasets.aspx) | CSV, JSON, XML sans clé | — | Prix des logements mensuels et trimestriels | Non vérifiée | Aucun |
| [CFTC COT](https://publicreporting.cftc.gov/stories/s/r4w3-av2u) | Socrata, sans clé | Non vérifiées | Positions sur contrats à terme depuis le 15 janvier 1986 | Non vérifiée | Rapport du mardi mis en ligne le vendredi vers 15 h 30 ET |

### International : neuf API officielles sans clé, des licences inégales

**FMI, Banque mondiale, OCDE.**

- Le FMI a basculé sur SDMX 2.1 et 3.0 (`api.imf.org/external/sdmx`), sans clé. Le catalogue compte 231 dataflows (WEO, COFER, CPI, BOP, PCPS…), dont des millésimes explicites comme `WEO_2025_OCT_VINTAGE` et `WEO_2026_APR_VINTAGE`. IFS a disparu et l'ancien `dataservices.imf.org` ne répond plus ([catalogue FMI](https://api.imf.org/external/sdmx/3.0/structure/dataflow/*/*/+?detail=allstubs) ; [page sdmxws](https://extauth.imf.org/maintenance/sdmxws-decommissioned.htm)).
- La Banque mondiale (Indicators v2, sans clé, CC BY 4.0) conserve une source 57 « WDI Database Archives » ([sources](https://api.worldbank.org/v2/sources?format=json&per_page=100)).
- L'OCDE (`sdmx.oecd.org`) plafonne à 60 téléchargements par heure. Un miroir annonce 20 par heure, ce qui révèle une contradiction non résolue ([OCDE](https://www.oecd.org/en/data/insights/data-explainers/2024/11/Api-best-practices-and-recommendations.html)). Elle publie les éditions 114 à 119 de l'Economic Outlook et un dataflow `DF_STES_REVISIONS` de révisions ([catalogue OCDE](https://sdmx.oecd.org/public/rest/dataflow/all/all/latest)).

**BCE, Eurostat et autres banques centrales.**

- La BCE expose une base temps réel `RTD` et les paramètres `updatedAfter` et `includeHistory` ([API BCE](https://data.ecb.europa.eu/help/api/data)).
- Eurostat conserve les premières publications de l'IPCH dans `prc_hicp_fp`. Son IPCH est passé en COICOP 2018, base 2025=100, en février 2026 ([test Eurostat](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr?geo=EA&coicop=CP00&lastTimePeriod=1)).
- La Banque du Japon a lancé son API le 18 février 2026 ([BoJ](https://www.boj.or.jp/en/statistics/outline/notice_2026/not260218a.htm)).
- La RBA ne propose que des CSV, bloqués par Akamai, avec « all other rights are reserved » ([RBA](https://www.rba.gov.au/copyright/)).

| Source | Accès | Limites | Couverture | Licence et réutilisation | Point-in-time |
|---|---|---|---|---|---|
| [FMI SDMX 2.1/3.0](https://data.imf.org/en/Resource-Pages/IMF-API) | Sans clé | Non publiées | Mondial, Canada compris ; 231 dataflows ; mensuel à annuel | Attribution ; usage commercial sur permission ; téléchargement massif automatisé interdit sans accord | **Natif** : dataflows `*_VINTAGE` (WEO, CPI, ER, MFS, BOP…) |
| [Banque mondiale v2](https://api.worldbank.org/v2/country/CA/indicator/NY.GDP.MKTP.CD?format=json&per_page=2) / [Data360](https://data360.worldbank.org/en/int/about) | Sans clé | Non publiées | WDI, IDS, GEM, GEP | CC BY 4.0 par défaut | `lastupdated` ; archives WDI (source 57) |
| [OCDE SDMX](https://sdmx.oecd.org/public/rest/dataflow/all/all/latest) | Sans clé | 60 téléchargements/h (contesté) ; paramètres restreints sur les très gros jeux | 1 553 dataflows ; CLI du Canada | CC BY 4.0 depuis le 1er juillet 2024 | **Natif** : EO 114–119, `DF_STES_REVISIONS` |
| [BRI v2](https://stats.bis.org/api-doc/v2/) | Sans clé | Non publiées | Taux directeurs (BdC à 2,5 % au 9 novembre 2026), crédit, immobilier | Usage libre sans suggérer d'aval (page à relire) | `etag` seul |
| [BCE Data Portal](https://data.ecb.europa.eu/help/api/data) | Sans clé | Non publiées | Zone euro ; EUR/CAD | Libre, y compris commercial, avec citation et sans modification | **Natif** : `RTD`, `updatedAfter`, `includeHistory` |
| [Eurostat](https://ec.europa.eu/eurostat/help/copyright-notice) | Sans clé ; JSON-stat, SDMX | — | UE | Libre avec citation, sauf données d'origine non européenne | `updated` ; `prc_hicp_fp` |
| [BoE IADB](https://www.bankofengland.co.uk/legal) | CSV par URL | Restriction en cas d'usage excessif | Bank Rate, séries monétaires ; courbes en ZIP seulement | UK Open Government Licence | Aucun |
| [BoJ](https://www.stat-search.boj.or.jp/info/api_notice_en.pdf) | Sans clé | Pas d'accès excessif | Japon | Notification et mention obligatoires | Aucun |
| [Bundesbank](https://www.bundesbank.de/en/homepage/user-information/terms-of-use-regarding-the-reuse-of-escb-statistics-621188) | SDMX sans clé | — | Allemagne, BBEX3 CAD/EUR | Conditions du SEBC | — |
| [Banque de France Webstat](https://webstat.banque-france.fr/api/explore/v2.1/catalog/datasets?limit=1) | Sans clé | 5 000 req/j (en-tête observé) | France | Non vérifiée | — |
| [UN Comtrade](https://comtradewiki.azurewebsites.net/?p=78) | Aperçu sans clé ; clé gratuite | 500 appels/j, 100 000 enregistrements par appel | Commerce mondial | Non vérifiée | — |
| [ILOSTAT](https://rplumber.ilo.org/data/indicator/?id=UNE_DEAP_SEX_AGE_RT_A&ref_area=CAN&format=.csv) / [OMC](https://apiportal.wto.org/) / [FAOSTAT](https://www.fao.org/statistics/highlights-archive/highlights-detail/faostat-launches-a-new-api-developer-portal-to-make-data-access-easier/en) | Sans clé / clé gratuite / connexion (depuis avril 2026) | SDMX de l'OIT en 403 | Emploi, commerce, agriculture | Non vérifiées | — |
| [AIE](https://www.iea.org/data-and-statistics/data-product/world-energy-outlook-2025-free-dataset) | Jeux gratuits | — | Énergie mondiale | CC BY-NC-SA 4.0 (non commercial) | — |

**Les agrégateurs.**

- DBnomics est le plus vaste (94 fournisseurs, 1,73 milliard de séries, sans clé), mais ses connecteurs FMI (2025-09-04), BRI (2025-07-10) et Banque mondiale (2024-09-19) n'ont pas été réindexés depuis les migrations. La licence suit celle du fournisseur d'origine, et le client Python est sous AGPL ([fournisseurs DBnomics](https://api.db.nomics.world/v22/providers?limit=200) ; [conditions](https://docs.db.nomics.world/legal-terms/)).
- OpenBB est passé à Apache 2.0 avec sa V5 du 29 septembre 2026 ; il embarque un fournisseur `tmx` et un serveur MCP ([PyPI openbb](https://pypi.org/project/openbb/)).
- pandas-datareader 0.11 a supprimé les lecteurs Yahoo, Quandl, Stooq et Tiingo ([whatsnew](https://github.com/pydata/pandas-datareader/blob/main/docs/source/whatsnew/v0.11.0.txt)).
- Le compte invité de Trading Economics renvoie 410, et Econdb exige désormais une authentification ([Trading Economics](https://api.tradingeconomics.com/historical/country/canada/indicator/gdp?c=guest:guest&f=json) ; [Econdb](https://www.econdb.com/api/series/CPICA/?format=json)).

Conclusion : appeler les API primaires et garder les agrégateurs pour l'exploration.

## Taux, obligations et devises restent ouverts, sauf ICE et le LBMA

### Courbes et taux de référence

**Canada.** La courbe zéro-coupon de la BdC (0,25 à 30 ans, depuis 1986) n'est pas dans Valet. Elle sort d'un formulaire CSV, « typically updated each Thursday by 16:30 ET, with a two-week lag ». Le 14 novembre, la dernière date disponible était le 28 octobre ([courbes BdC](https://www.bankofcanada.ca/rates/interest-rates/bond-yield-curves/)). Les adjudications du gouvernement du Canada sont dans Valet (`AUC_BOND_RESULTS`, 24 champs dont l'ISIN et le taux de couverture). La dernière adjudication d'obligations à rendement réel remonte au 1er septembre 2022, ce qui fragilise tout point mort d'inflation calculé par `BD.CDN.LONG − BD.CDN.RRB` (environ 2,15 points au 12 novembre) ([Valet AUC_BOND_RR_RESULTS](https://www.bankofcanada.ca/valet/observations/group/AUC_BOND_RR_RESULTS/json?recent=1)).

**États-Unis.** Le Trésor publie ses courbes « par » nominale et réelle en XML et CSV, à partir de cotations prises « at approximately 3:30 PM ». Il « does not create or publish daily zero-coupon curve rates » ([statistiques du Trésor](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics) ; [FAQ](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/interest-rates-frequently-asked-questions)). La Fed de New York publie le SOFR vers 8 h ET, puis l'EFFR et l'OBFR vers 9 h. Une révision n'intervient vers 14 h 30 que si l'écart dépasse un point de base ([NY Fed](https://www.newyorkfed.org/markets/reference-rates/additional-information-about-reference-rates)).

**Ce qui est fermé.** Le crédit à l'unité de transaction (TRACE) passe par l'API FINRA, dont le credential Public est gratuit mais exige un jeton. L'accès aux jeux obligataires y est « Limited », et les comptes individuels sont « not intended for commercial purposes » ([FINRA fees](https://developer.finra.org/fees) ; [FINRA docs](https://developer.finra.org/docs)). Les flux automatisés de MSRB EMMA sont payants ([MSRB](https://msrb.org/node/13302)). La Banque d'Angleterre précise que « Our yield curve data are not available over an API » ([BoE](https://www.bankofengland.co.uk/statistics/yield-curves)). Pour les FNB obligataires de l'univers (XBB, ZST, AGG, TLT), la courbe Valet et celle du Trésor suffisent à construire des facteurs de duration. Les écarts ICE BofA ne doivent pas entrer dans la base.

| Source | Accès | Limites | Couverture, historique, fréquence | Licence | Point-in-time |
|---|---|---|---|---|---|
| [Valet, obligations et CORRA](https://www.bankofcanada.ca/valet/observations/group/bond_yields_benchmark/json?recent=1) | Sans clé | Non chiffrées | Référence 2, 3, 5, 7, 10 ans, long, RRB ; CORRA ; bons du Trésor ; adjudications ; hypothèque 5 ans | Conditions BdC | Date d'observation seule ; `CORRA_TRANSPARENCY` pour les erreurs |
| [BdC zéro-coupon](https://www.bankofcanada.ca/rates/interest-rates/bond-yield-curves/) | CSV par formulaire | — | 0,25 à 30 ans, depuis 1986 | Conditions BdC | Publication le jeudi, deux semaines de décalage |
| [Trésor US XML/CSV](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed) | Sans clé | — | Courbe par nominale depuis 1990, réelle depuis 2003 ou 2004 (sources divergentes) ; quotidienne | Domaine public probable (non vérifié) | `<updated>` au niveau du flux seulement |
| [TreasuryDirect TA_WS](https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json&type=Note&pagesize=1) | JSON sans clé | — | Adjudications : CUSIP, `announcementDate`, bid-to-cover | — | Dates d'annonce et d'adjudication ; documentation déplacée |
| [NY Fed taux](https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json) | Sans clé | Non documentées | SOFR, EFFR, OBFR, percentiles, volumes | Conditions NY Fed | `revisionIndicator` ; publication à T+1 vers 8 h ou 9 h ET |
| [FINRA API](https://developer.finra.org/docs) | Credential Public à 0 $ ; jeton requis | 1 200 req/min par IP ; 5 000 enregistrements par requête synchrone | Agrégats TRACE (breadth, sentiment) | ToS FINRA ; usage individuel non commercial | `tradeReportDate` |
| [BCE courbes](https://www.ecb.europa.eu/stats/financial_markets_and_interest_rates/euro_area_yield_curves/html/index.en.html) | Sans clé | — | Courbes AAA de la zone euro, chaque jour TARGET à midi CET | SEBC | `includeHistory` |
| [ICE BofA via FRED](https://fred.stlouisfed.org/series/BAMLH0A0HYM2) | Clé FRED | 3 ans d'historique depuis avril 2026 | Écarts de crédit IG et HY | Reproduction interdite sans permission d'ICE | ALFRED |
| [Freddie Mac PMMS](https://www.freddiemac.com/pmms) | CSV | — | Taux hypothécaires depuis 1971 ; hebdomadaire, jeudi midi ET | Conditions non lues | Fenêtre du jeudi au mercredi |

### Devises : Valet comme taux officiel, Frankfurter comme miroir

**Valet.** Pour le CAD, `FXUSDCAD` reste la référence de la base : taux indicatif unique, publié à 16 h 30 HE. Un piège de mai 2026 : la BdC a cessé de publier le rouble et le riyal saoudien (dernière valeur au 30 avril) et a ajouté le ringgit, le zloty et le baht. Avec `recent=1`, les séries arrêtées renvoient d'anciennes dates, ce qui fausse le « dernier jour » si l'on lit naïvement la dernière ligne ([taux de change BdC](https://www.bankofcanada.ca/rates/exchange/daily-exchange-rates/) ; [Valet FX_RATES_DAILY](https://www.bankofcanada.ca/valet/observations/group/FX_RATES_DAILY/json?recent=1)).

**Frankfurter v2.** Frankfurter v2 agrège 111 banques centrales et sources officielles, avec un historique depuis 1948. Il est sans clé, sans quota et autorise l'usage commercial. Son serveur MCP officiel ne demande aucune inscription. `providers=boc` renvoie exactement le taux Valet (1,4257 au 13 novembre) ([Frankfurter](https://frankfurter.dev/) ; [fournisseurs](https://api.frankfurter.dev/v2/providers)). Il faut passer explicitement `providers=boc` ou `providers=ecb`, car la v2 mélange les fournisseurs par défaut.

**Paliers commerciaux.** Les paliers gratuits commerciaux sont minces et presque tous non redistribuables.

| Source | Accès | Limites | Couverture | Licence et réutilisation | Point-in-time |
|---|---|---|---|---|---|
| [BdC FX_RATES_DAILY](https://www.bankofcanada.ca/valet/observations/group/FX_RATES_DAILY/csv?start_date=2026-11-01) | Sans clé | Non chiffrées | 27 paires contre CAD ; taux unique depuis 2017, séries « legacy » avant | Conditions BdC ; taux « indicative » (source LSEG) | Publication vers 16 h 30 HE le jour ouvrable |
| [BCE EXR](https://data-api.ecb.europa.eu/service/data/EXR/D.CAD.EUR.SP00.A?lastNObservations=1&format=csvdata) | Sans clé | — | Taux de référence de l'euro depuis 1999, à 14 h 15 CET | SEBC | `includeHistory` |
| [Frankfurter v2](https://frankfurter.dev/) | Sans clé ; MCP officiel | Pas de quota ; limite anti-abus | 219 devises, 111 fournisseurs, depuis 1948 ; or (XAU) de certaines banques centrales | Commercial permis ; taux de chaque fournisseur soumis à ses conditions | Date seule ; `publish_cadence` par fournisseur |
| [Fed H.10](https://www.federalreserve.gov/releases/h10/current/) | DDP | — | Hebdomadaire ; via FRED depuis 1971 | Domaine public | DDP retiré en 2027 |
| [ExchangeRate-API (accès ouvert)](https://www.exchangerate-api.com/docs/free) | Sans clé | 429 pendant 20 min en cas d'abus ; clé gratuite : 1 500 req/mois | Quotidien | Attribution ; **redistribution interdite** | `time_last_update_utc` |
| [Open Exchange Rates](https://openexchangerates.org/signup) | Clé | 1 000 req/mois ; base USD | Horaire | Conditions non lues | — |
| [exchangerate.host](https://exchangerate.host/product) / [Fixer](https://fixer.io/product) | Clé APILayer | 100 req/mois | Quotidien ou horaire | Non commercial | — |
| [CurrencyAPI](https://currencyapi.com/pricing/) | Clé | 300 req/mois, 10/min | Quotidien | Usage commercial réservé au payant | — |
| [fawazahmed0](https://github.com/fawazahmed0/exchange-api) | CDN sans clé | Sans limite | Quotidien, cryptos comprises | CC0, mais provenance non documentée | — |
| [Twelve Data](https://twelvedata.com/pricing) / [Alpha Vantage](https://www.alphavantage.co/documentation/) / [OANDA](https://allratestoday.com/blog/is-oanda-api-free/) | Clé | 800/j ; 25/j ; essai de 7 jours | FX quotidien (intrajournalier premium chez AV) | Interne sans affichage ; conditions AV non lues ; OANDA payant | — |

### Matières premières et or : le LBMA est sous licence

L'or est le cas juridiquement le plus délicat. Le LBMA Gold Price est un indice de référence administré par IBA (ICE), et « any use of the benchmark for commercial purposes » exige une licence. Depuis la semaine du 24 novembre 2025, l'historique est réservé au portail des membres ([LBMA](https://www.lbma.org.uk/articles/lbma-benchmark-prices-data-tables-are-moving)). FRED l'a retiré le 31 janvier 2022, tout comme le World Gold Council et DBnomics ([FRED](https://news.research.stlouisfed.org/2022/01/ice-benchmark-administration-ltd-iba-data-to-be-removed-from-fred/) ; [gold.org](https://www.gold.org/goldhub/data/gold-prices)).

Pour GLD, la solution propre combine trois éléments :

- le prix de clôture du FNB lui-même ;
- l'or mensuel du FMI (PCPS `PGOLD`), dont la réponse porte un `PUBLICATION_DATE`. Le champ `LICENSE` y indique pourtant « All Rights Reserved », ce qui contredit les conditions générales du FMI et reste à clarifier ([FMI PCPS](https://api.imf.org/external/sdmx/2.1/data/IMF.RES,PCPS/G001.PGOLD.USD.M?startPeriod=2026-08)) ;
- en quotidien, l'or publié par certaines banques centrales via Frankfurter.

Le pétrole vient de l'EIA, qui relève du domaine public ([EIA](https://www.eia.gov/about/copyrights_reuse.php)). L'endpoint WTI d'Alpha Vantage n'est qu'un relais de FRED ([Alpha Vantage](https://www.alphavantage.co/documentation/)).

| Source | Accès | Limites | Couverture | Licence | Point-in-time |
|---|---|---|---|---|---|
| [LBMA / IBA](https://www.ice.com/iba/licensing) | Portail des membres | — | Or et argent ; platine et palladium chez LME | Licence IBA pour tout usage commercial et la redistribution | — |
| [FMI PCPS](https://data.imf.org/en/datasets/IMF.RES:PCPS) | SDMX sans clé | — | Plus de 70 produits, mensuel, depuis les années 1990 | Conditions du FMI ; champ « All Rights Reserved » | `PUBLICATION_DATE`, `UPDATE_DATE` |
| [Banque mondiale Pink Sheet](https://www.worldbank.org/en/research/commodity-markets) | XLSX, pas d'API | — | Mensuel ; prochaine mise à jour le 2 décembre 2026 | Renvoi vers CC BY (non confirmé sur la fiche) | Date de mise à jour |
| [EIA](https://www.eia.gov/opendata/documentation.php) | Clé gratuite | 5 000 lignes par réponse | WTI, Brent, gaz naturel | Domaine public | Aucun |
| [BdC BCPI](https://www.bankofcanada.ca/valet/observations/M.BCPI/json?recent=1) | Valet | — | IPPB total, énergie, métaux, agriculture ; mensuel et hebdomadaire | Conditions BdC | Date de référence seule |
| [GoldAPI](https://www.goldapi.io/) / [metals.dev](https://metals.dev/pricing) / [MetalpriceAPI](https://www.metalpriceapi.com) | Clé | 150 / 100 / 100 req/mois | XAU/CAD, métaux précieux ; fixings LBMA (GoldAPI) | CGU non lues | — |
| [Metals-API](https://metals-api.com/pricing) / [CME](https://www.cmegroup.com/market-data/delayed-quotes.html) | Payant / affichage web seulement | — | — | — | — |

## Le TSX reste l'angle mort des prix gratuits

### Actions et FNB

**Couverture du TSX au gratuit.** En novembre 2026, aucun fournisseur à clé gratuite ne couvre le TSX sans contrainte forte. Trois options existent :

- yfinance (`RY.TO`) : non officiel, version 1.8.0 du 3 novembre 2026, sans quota publié, mais sujet aux 429 depuis le cloud ;
- Alpha Vantage, avec le suffixe `.TRT` (`SHOP.TRT`) : 25 requêtes par jour et seulement les 100 derniers points en gratuit, `outputsize=full` étant réservé au premium ;
- EODHD (code `TO`, environ 2 900 tickers) : 20 appels par jour sur un an d'historique, « personal use » ([yfinance](https://pypi.org/project/yfinance/) ; [Alpha Vantage docs](https://www.alphavantage.co/documentation/) ; [EODHD](https://eodhd.com/pricing)).

Questrade offre une API gratuite (cotes de niveau 1 et bougies, actions canadiennes et américaines), mais elle exige un compte client et l'acceptation d'un accord d'accès ([Questrade](https://developer.questrade.com/)). Twelve Data, Finnhub, FMP, Massive, Alpaca et Tiingo se limitent aux États-Unis en gratuit, ou ne mentionnent pas le Canada.

**Ce que cela implique pour la base.** Pour les .TO et les FNB canadiens de l'univers (XIU.TO, XBB.TO, ZST.TO), yfinance reste la seule voie gratuite en volume. Il faut l'exécuter hors d'AgentCore, sur un poste local ou en CI, pour constituer un cache horodaté, et non en dépendance temps réel d'A5. EODHD ou Alpha Vantage servent au contrôle croisé incrémental. La licence de Yahoo impose de verser dans la base générale des rendements et indicateurs dérivés, pas des séries brutes, ou d'obtenir l'aval des organisateurs, puisque le jeu de départ utilise déjà yfinance.

**Fermetures récentes.** IEX Cloud a fermé le 31 août 2024 ([WatersTechnology](https://waterstechnology.com/data-management/7951882/iex-cloud-closure-forces-fintech-clients-to-seek-data-alternatives)). Stooq exige une clé depuis le printemps 2026 ([pandas-datareader #1012](https://github.com/pydata/pandas-datareader/issues/1012)). Google Finance n'offre aucune API, et son historique n'est même pas accessible par Apps Script ([Google](https://support.google.com/docs/answer/3093281?hl=en)).

| Source | Accès | Limites gratuites | Couverture et historique | Licence et redistribution | Point-in-time |
|---|---|---|---|---|---|
| [yfinance](https://pypi.org/project/yfinance/) | Sans clé, non officiel | Aucun quota publié ; 429 fréquents, surtout depuis le cloud | Mondial dont `.TO` ; long historique ; quotidien et intrajournalier | « Personal use only » ; licence Yahoo personnelle et révocable | Aucun |
| [Alpha Vantage](https://www.alphavantage.co/premium/) | Clé gratuite ; MCP officiel | 25 req/j ; illimité pour les projets éducatifs vérifiés | TSX en `.TRT` ; gratuit limité aux 100 derniers points | Usage commercial sur contact | Aucun pour les prix |
| [EODHD](https://eodhd.com/pricing) | Clé ; jeton `demo` pour 6 tickers | 20 appels/j (plus 500 de bienvenue), 20/min ; une 404 compte | `.TO` ; 1 an d'EOD ; dividendes et splits inclus | « Personal use » | `adjusted_close` recalculé à chaque dividende |
| [Twelve Data](https://twelvedata.com/pricing) | Clé ; MCP officiel | 8 crédits/min, 800/j | Actions et FNB US, FX, crypto ; Canada seulement via un module Cboe Canada payant (dès 180 $/an), TSX non nommé | Interne, sans affichage ; plan Business pour toute organisation | — |
| [Finnhub](https://finnhub.io/pricing) | Clé | 60 appels/min (sources tierces) | Bougies premium ; international payant | Personnel ; aucune redistribution, même dérivée | — |
| [Massive (ex-Polygon)](https://massive.com/pricing) | Clé ; MCP officiel expérimental | 5 appels/min (tiers) | Actions US, EOD, 2 ans en Basic | « Individual use only » | — |
| [Tiingo](https://www.tiingo.com/about/pricing) | Clé | 50 req/h, 1 000/j, 500 symboles/mois | Plus de 30 ans ; 110 531 titres ; Canada non mentionné | « Internal Use Only » | — |
| [FMP](https://site.financialmodelingprep.com/pricing-plans) | Clé | 250 appels/j | Bourses US ; Canada à partir de Premium (69 $/mois) | Affichage et redistribution sous contrat | — |
| [Marketstack](https://marketstack.com/pricing) | Clé | 100 req/mois | 1 an d'EOD | — | — |
| [Alpaca](https://docs.alpaca.markets/docs/about-market-data-api) | Clé | 200 appels/min | Actions US (IEX) depuis 2016, hors 15 dernières minutes | — | — |
| [Questrade](https://www.questrade.com/disclosure/legal-notice-and-disclosures/api-access-agreement) | Compte client et accord | — | Actions et options CA/US | Accord personnel ; flux tiers | — |
| [Databento](https://databento.com/venues) | Carte de paiement ; crédit de 125 $ | Crédit valable 6 mois | TSX, TSXV, Cboe Canada, CSE | Payant à l'usage | — |
| [TMX Datalinx](https://tmxinfoservices.com/corporate-and-reference-data/historical-trading-data) | Payant (essai de 90 jours) | — | TSX depuis 1998 | Utilisateur unique, sans redistribution | — |

### Opérations sur titres

Massive est le seul fournisseur gratuit qui livre les quatre dates d'un dividende : déclaration, ex-date, enregistrement et paiement. Il ne couvre que les titres américains, sur deux ans en Basic ([Massive dividendes](https://massive.com/docs/rest/stocks/corporate-actions/dividends.md)). Alpha Vantage `DIVIDENDS` renvoie aussi `declaration_date`, `record_date` et `payment_date`, comme le montre l'exemple IBM ([test Alpha Vantage](https://www.alphavantage.co/query?function=DIVIDENDS&symbol=IBM&apikey=demo)). Twelve Data ne donne que l'ex-date ([Twelve Data](https://twelvedata.com/docs/llms/fundamentals/dividends.md)). Chez EODHD, `adjusted_close` est « recomputed, not stored » : un nouveau dividende réécrit l'historique ([EODHD EOD](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)). La base doit donc stocker les prix bruts et les facteurs d'ajustement, jamais le seul prix ajusté. Aucune source gratuite vérifiée ne donne les dates de déclaration des dividendes canadiens. Pour les titres intercotés, la source primaire est le communiqué déposé en 6-K sur EDGAR.

### Cryptoactifs

CoinGecko Demo reste la meilleure base gratuite pour BTC et ETH :

- 100 appels par minute et 10 000 par mois, un an d'historique quotidien et horaire ;
- « Attribution required » ;
- un MCP officiel distant sans clé, dont les limites sont partagées entre utilisateurs ([CoinGecko](https://www.coingecko.com/en/api/pricing) ; [MCP CoinGecko](https://docs.coingecko.com/ai-integration/mcp-server)).

CoinMarketCap Basic revendique explicitement des droits commerciaux, ce qui en fait l'alternative la moins restrictive pour une démonstration ([CMC](https://coinmarketcap.com/api/pricing/)). Les ruptures de 2026 sont nombreuses :

- CoinDesk Data (ex-CryptoCompare) a retiré son palier gratuit le 21 mai 2026 ([CoinDesk Data](https://data.coindesk.com/blogs/changes-to-coindesk-data-indices-api-free-tier-access)) ;
- l'API v2 de CoinCap ne répond plus ([CoinPaprika](https://coinpaprika.com/education/migrating-from-coincap-api-to-coinpaprika/)) ;
- Binance bloque les IP américaines, AWS compris, et a quitté le Canada en 2023 ([BetaKit](https://betakit.com/binance-exits-canada-as-crypto-trading-platforms-feel-broader-impact-of-stricter-regulations/)).

Kraken et Coinbase publics servent de contrôle croisé sans clé.

| Source | Accès | Limites | Historique | Licence | Remarque |
|---|---|---|---|---|---|
| [CoinGecko Demo](https://www.coingecko.com/en/api/pricing) | Clé gratuite ; MCP sans clé | 100/min, 10 000/mois | 1 an quotidien et horaire ; 1 jour en 5 min | Attribution obligatoire ; licence commerciale à partir de 35 $/mois | Source principale recommandée |
| [CoinMarketCap Basic](https://coinmarketcap.com/api/pricing/) | Clé | 15 000 crédits/mois, 50/min | Quotidien sur 1 an (à confirmer) | Droits commerciaux inclus selon la FAQ | Alternative pour démonstration |
| [CoinPaprika](https://coinpaprika.com/api/pricing/) | Palier Free (quota par IP) | 20 000 appels/mois par IP, 10 req/s | 1 an quotidien | Personnel ; « Powered by CoinPaprika » | — |
| [CoinCap v3](https://splash.coincap.io/) | Clé | 500 crédits/mois, 5/min | — | — | v2 hors service |
| [Kraken](https://docs.kraken.com/exchange/guides/general/historical-data) / [Coinbase](https://docs.cloud.coinbase.com/advanced-trade/docs/changelog) | Sans clé | Par IP (1 appel/s est sûr chez Kraken ; 10 à 20 req/s chez Coinbase selon les sources) | 720 bougies par appel (Kraken) | Conditions d'échange | Contrôle croisé |
| [Binance](https://dev.binance.vision/t/api-error-451-unavailable-for-legal-reasons/13828) | — | 451 depuis les États-Unis ; `data-api.binance.vision` pour le spot | — | — | À éviter depuis AWS |
| [DefiLlama](https://defillama.com/pro-api) / [mempool.space](https://mempool.space/enterprise) / [Fear & Greed](https://api.alternative.me/fng/) | Sans clé | Non publiées | TVL DeFi ; on-chain Bitcoin ; sentiment | mempool sous AGPL, auto-hébergeable ; reste non vérifié | Compléments |

## EDGAR couvre huit des dix titres canadiens, SEDAR+ aucun

### Dépôts réglementaires

**L'API data.sec.gov.** EDGAR est la colonne vertébrale gratuite et redistribuable des fondamentaux. Les API data.sec.gov « do not require any authentication or API keys ». Elles sont mises à jour en temps réel : moins d'une seconde pour les soumissions, moins d'une minute pour le XBRL. Elles sont doublées de ZIP compilés chaque nuit vers 3 h ET ([SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)). L'accès équitable impose 10 requêtes par seconde au maximum et un User-Agent déclaré ([SEC developer](https://www.sec.gov/about/developer-resources)).

Chaque fait de `companyfacts` porte `end` (fin de période) et `filed` + `accn` (dépôt), et `submissions` donne `acceptanceDateTime` à la seconde. Le point-in-time est donc natif ([test Shopify](https://data.sec.gov/api/xbrl/companyfacts/CIK0001594805.json) ; [test RY](https://data.sec.gov/submissions/CIK0001000275.json)). Ce n'est pas le cas de l'endpoint `frames`, qui renvoie le fait « last filed », potentiellement retraité, et ne convient pas aux backtests.

**Couverture des titres canadiens.** Huit des dix titres canadiens de l'univers y figurent (RY, TD, SHOP, ENB, CNQ, MFC, FTS et CN sous le ticker NYSE `CNI`). **ATD et CSU sont absents** ([company_tickers.json](https://www.sec.gov/files/company_tickers.json)). Trois difficultés s'ajoutent :

- Les taxonomies sont mixtes : `ifrs-full` pour RY, TD, CNQ et MFC, `us-gaap` pour ENB, SHOP, CNI et FTS. A5 a donc besoin d'une table de correspondance des concepts.
- RY et TD déposent du XBRL trimestriel via leurs 6-K, alors que MFC et CNQ n'en déposent qu'en annuel (40-F).
- XOM a changé de CIK le 1er juillet 2026 après sa redomiciliation : le nouveau CIK 2115436 ne compte que 98 concepts, et l'historique reste sous l'ancien 34088 ([8-K ExxonMobil](https://investor.exxonmobil.com/sec-filings/all-sec-filings/content/0001193125-26-291990/d71068d8k12b.htm)).

**Côté canadien, la porte est fermée.** Les conditions de SEDAR+ (28 avril 2023) interdisent le « scraping », « any robot, spider or other automatic device », de « construct a database of any kind » et de « commercialize the Public Information » ([CGU SEDAR+](https://systems.securities-administrators.ca/?p=4978)). Le XBRL canadien est resté volontaire et « not yet available in SEDAR+ » ([ACVM XBRL](https://www.securities-administrators.ca/resources/xbrl-filing/)). Pour ATD et CSU, la seule voie conforme est le téléchargement manuel des rapports sur les sites des émetteurs, avec la date du communiqué comme date de publication.

### API commerciales de fondamentaux

Aucun palier gratuit n'offre de fondamentaux complets pour les sociétés TSX non intercotées.

- Alpha Vantage est le meilleur complément. Ses états financiers, `EARNINGS` (avec `reportedDate` et `reportTime`), `DIVIDENDS` et `ETF_PROFILE` restent gratuits, mais `OVERVIEW` est désormais premium ([Alpha Vantage docs](https://www.alphavantage.co/documentation/) ; [test EARNINGS](https://www.alphavantage.co/query?function=EARNINGS&symbol=IBM&apikey=demo)).
- Chez Massive, `filing_date` est « not necessarily the date this period was originally filed » ([Massive](https://massive.com/docs/rest/stocks/fundamentals/income-statements)).
- Chez SimFin, la `Publish Date` ignore les 8-K préliminaires ([SimFin names.py](https://raw.githubusercontent.com/SimFin/simfin/master/simfin/names.py)).

Pour éviter le look-ahead, il faut donc recalculer les dates de publication depuis `acceptanceDateTime`.

### FNB : avoirs, frais, réplication

Deux téléchargements officiels fonctionnaient sans clé le 14 novembre 2026 :

- le CSV d'iShares Canada (XIU au 12 novembre, 69 lignes, sans ISIN ; XBB, environ 1 950 lignes avec duration et coupon) ([CSV XIU](https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf/1464253357814.ajax?fileType=csv&fileName=XIU_holdings&dataType=fund)) ;
- le XLSX quotidien de SPDR pour SPY ([XLSX SPY](https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx)).

Aucun des deux n'est redistribuable. Le fichier SPDR interdit d'en divulguer le contenu « to third parties without SSGA's express written consent », et les conditions iShares interdisent le scraping et la reproduction ([iShares](https://www.ishares.com/us/compliance/factor-box-terms)). Invesco a répondu 406, Vanguard 404, et BMO était injoignable.

Pour la transparence des FNB canadiens, il faut stocker des expositions agrégées (par secteur ou par émetteur), datées « as of ». Pour les FNB américains, le N-PORT de la SEC reste redistribuable, mais il est trimestriel et différé de plusieurs mois. Ses amendements mensuels sont reportés au 17 novembre 2027 ([Thompson Hine](https://www.thompsonhine.com/insights/sec-extends-compliance-date-for-amendments-to-form-n-port)). Les RFG et méthodes de réplication des FNB TSX ne sont disponibles par aucune API gratuite : ils viennent des prospectus. `ETF_PROFILE` d'Alpha Vantage donne le `net_expense_ratio` et les avoirs des FNB américains ([test QQQ](https://www.alphavantage.co/query?function=ETF_PROFILE&symbol=QQQ&apikey=demo)).

### Identifiants et calendriers

La chaîne d'identifiants recommandée part du ticker et de la bourse :

- OpenFIGI (25 requêtes par minute sans clé, 250 avec ; Toronto = `exchCode CT`) donne le FIGI ([OpenFIGI](https://www.openfigi.com/api/documentation)) ;
- GLEIF, sans clé, donne le LEI et les ISIN liés ([GLEIF RY](https://api.gleif.org/api/v1/lei-records/ES7IP3U3RHIGC71XBU11)) ;
- la SEC donne le CIK quand il existe.

Les CUSIP sont sous licence CGS (FactSet) ([WatersTechnology](https://www.waterstechnology.com/data-management/7952899/where-have-four-years-of-cusip-legal-drama-gone)).

| Source | Accès | Limites | Couverture et historique | Licence | Point-in-time |
|---|---|---|---|---|---|
| [SEC data.sec.gov](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Sans clé ; User-Agent obligatoire (403 sinon) ; pas de CORS | 10 req/s | Émetteurs SEC, dont 8 titres TSX ; XBRL en temps réel ; ZIP nocturnes | Données publiques ; scripts autorisés | **Natif** : `end`, `filed`, `accn`, `acceptanceDateTime` ; `frames` = « last filed » |
| [EDGAR FTS](https://www.sec.gov/edgar/search/efts-faq.html) | Backend JSON non documenté | 10 req/s | Texte intégral depuis 2001 | Public | `file_date` |
| [FSDS](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets) / [FSN](https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets) | ZIP trimestriels | — | 2009 à 2026T3 ; notes jusqu'en octobre 2026 | Public | « As originally filed » |
| [N-PORT](https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets) / [N-CEN](https://www.sec.gov/data-research/sec-markets-data/form-n-cen-data-sets) / [13F](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets) | ZIP | — | Avoirs des fonds US depuis octobre 2019 ; N-CEN depuis 2018 ; 13F depuis 2013 | Public | Publication trimestrielle, « as filed » |
| [sec-api.io](https://sec-api.io/pricing) | Clé | 100 appels au total | Toutes les API ; MCP | Redistribution réservée à Enterprise | — |
| [SEDAR+](https://systems.securities-administrators.ca/?p=4978) | Consultation humaine seulement | — | Tous les émetteurs canadiens | Automatisation, bases de données et commercialisation interdites | Date de dépôt (manuelle) |
| [Alpha Vantage fondamentaux](https://www.alphavantage.co/documentation/) | Clé | 25 req/j | États financiers, `EARNINGS`, `DIVIDENDS`, `ETF_PROFILE`, `LISTING_STATUS` historique | Usage commercial sur contact | `reportedDate`, `declaration_date` |
| [FMP Basic](https://site.financialmodelingprep.com/pricing-plans) | Clé | 250/j ; 87 symboles ; 5 réponses par appel ; 500 Mo sur 30 j | US ; Canada à partir de 69 $/mois ; avoirs de FNB à partir de 139 $/mois | Contrat d'affichage obligatoire | — |
| [SimFin FREE](https://www.simfin.com/en/prices/) | Clé | 2 appels/s | 5 000 titres US, 5 à 7 ans | Données à supprimer à la fin de l'abonnement | `Publish Date` (ignore les 8-K) |
| [EODHD fondamentaux](https://eodhd.com/pricing) | Payant (59,99 $/mois) | — | `ETF_Data` : avoirs, RFG, secteurs | Personnel ou commercial séparés | — |
| [iShares Canada CSV](https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf/1464253357814.ajax?fileType=csv&fileName=XIU_holdings&dataType=fund) / [SPDR XLSX](https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx) | URL sans clé | — | Avoirs quotidiens de XIU, XBB et SPY | Reproduction et divulgation interdites | Date « as of » |
| [OpenFIGI](https://www.openfigi.com/api/documentation) / [GLEIF](https://gleif.org/en/lei-data/gleif-api) | Clé optionnelle / sans clé | 25 ou 250 req/min / 60 req/min (tiers) | FIGI, LEI, ISIN liés, sociétés mères | Conditions OpenFIGI non lues ; CC0 pour GLEIF (tiers) | — |

## Seules les sources publiques autorisent le texte intégral

### API de nouvelles généralistes et financières

**GDELT.** GDELT est la seule source généraliste à la fois gratuite, sans clé et redistribuable. Ses données sont « available for unlimited and unrestricted use for any academic, commercial, or governmental use », à condition de citer le projet et de mettre un lien ([GDELT](https://www.gdeltproject.org/about.html)). La redistribution porte sur ses métadonnées (URL, titre, ton, thèmes), pas sur le texte des articles. L'API DOC 2.0 couvre 65 langues, dont le français, mais ne cherche que dans une fenêtre glissante de trois mois ([DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)). Elle a répondu « Please limit requests to one every 5 seconds » dès la première requête ([test GDELT](https://api.gdeltproject.org/api/v2/doc/doc?query=%22Bank%20of%20Canada%22&mode=artlist&format=json)). Pour construire un historique, il faut archiver soi-même, ou passer par BigQuery (sandbox d'1 TiB par mois, tables expirant après 60 jours) ([BigQuery sandbox](https://docs.cloud.google.com/bigquery/docs/sandbox)).

**Agrégateurs commerciaux.** Leurs paliers gratuits sont presque tous réservés au développement :

- NewsAPI.org « may be used for development and testing in a development environment only », avec un délai de 24 heures ([NewsAPI](https://newsapi.org/terms)) ;
- GNews gratuit est non commercial, avec un délai de 12 heures et un contenu coupé à 250 caractères ([GNews](https://gnews.io/pricing)) ;
- Currents est la seule à permettre l'usage commercial avec attribution, sans republication du texte ([Currents](https://currentsapi.services/en/product/price)).

**Nouvelles financières.** Deux points ont changé en 2026. Alpha Vantage `NEWS_SENTIMENT` est désormais « Premium », ce qui casse de nombreux tutoriels FinBERT antérieurs ([Alpha Vantage](https://www.alphavantage.co/documentation/#news-sentiment)). Marketaux accepte `countries=ca` et `language=fr`, avec un sentiment par entité, mais seulement 3 articles par requête en gratuit, et ses CGU sont introuvables ([Marketaux](https://www.marketaux.com/documentation)).

**Réseaux sociaux.** Ils sont à exclure :

- Reddit a fermé l'accès libre à son API le 11 novembre 2025 ([r/redditdev](https://r.datuan.dev/r/redditdev/s/gquSJqMgrM)) ;
- X est passé au paiement à l'usage le 6 février 2026 ([Roboin](https://roboin.io/article/en/2026/02/08/x-transitions-api-to-pay-per-use-model-ending-free-plan/)) ;
- Stocktwits interdit le scraping depuis ses conditions révisées du 10 juillet 2026 ([Stocktwits](https://stocktwits.com/terms)).

### Banques centrales, statistique et politique

Les sources publiques se stockent en texte intégral, avec attribution. Les flux RSS de la BdC (communiqués, discours, RPM, EPE), de la Fed (domaine public), de la BCE et du Quotidien de StatCan, en anglais et en français, étaient actifs le 14 novembre ([flux BdC](https://www.bankofcanada.ca/rss-feeds/) ; [flux Fed](https://www.federalreserve.gov/feeds/feeds.htm) ; [Quotidien FR](https://www150.statcan.gc.ca/n1/rss/dai-quo/0-fra.rss)). Deux pièges :

- Les liens relatifs de la page RSS de StatCan pointent vers une 404 : il faut passer par `www150.statcan.gc.ca/n1/rss/`.
- L'entrée BLS de l'IPC d'octobre porte `published = 07:55`, alors que la publication officielle a lieu à 8 h 30 ([flux BLS](https://www.bls.gov/feed/cpi.rss)). La date du flux ne vaut donc pas date de disponibilité.

Côté politique et réglementaire, plusieurs sources sont ouvertes et sans clé : la Gazette du Canada, LEGISinfo en JSON bilingue, OpenParliament et l'API Nouvelles de Canada.ca (avec `fr/v2`) ([Canada.ca](https://www.canada.ca/en/news/web-feeds.html) ; [LEGISinfo](https://www.parl.ca/legisinfo/en/bills/json)). Le Federal Register est aussi sans clé, mais il renvoyait déjà le 14 novembre des documents datés du 16 novembre, alors en inspection publique ([Federal Register](https://www.federalregister.gov/api/v1/documents.json?per_page=1&conditions%5Bterm%5D=tariff&order=newest)). EDGAR diffuse le jour ouvrable suivant les dépôts commencés après 17 h 30 HE ([SEC](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)).

| Source | Accès | Limites gratuites | Historique, langues | Droits de stockage | Dates fournies |
|---|---|---|---|---|---|
| [GDELT DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) / [GKG](https://www.gdeltproject.org/data.html) | Sans clé | 1 requête par 5 s ; 250 résultats | 3 mois glissants ; 65 langues dont FR ; fichiers toutes les 15 min | Métadonnées redistribuables avec citation ; texte des articles aux éditeurs | `seendate` = détection, pas publication |
| [NewsAPI.org](https://newsapi.org/pricing) | Clé | 100 req/j ; délai de 24 h ; 1 mois | FR disponible | Développement seulement, pas de production | `publishedAt` |
| [GNews](https://gnews.io/pricing) | Clé | 100 req/j ; 10 articles ; délai de 12 h | 30 jours ; 41 langues | Non commercial ; cache raisonnable permis | — |
| [NewsData.io](https://newsdata.io/pricing) | Clé | 200 crédits/j ; délai de 12 h | 48 h | Tests et projets personnels ; attribution obligatoire | — |
| [Currents](https://currentsapi.services/en/product/price) | Clé | 250 req/j | 30 jours ; 34 langues | Commercial avec attribution et lien ; pas de republication | — |
| [Mediastack](https://mediastack.com/pricing) / [TheNewsAPI](https://www.thenewsapi.com/pricing) / [World News API](https://worldnewsapi.com/terms/) / [Event Registry](https://newsapi.ai/terms) | Clé | 100/mois ; 3 articles/req ; 50 points/j ; 2 000 recherches | Variable | Non commercial ; non précisé ; cache d'1 h au plus ; évaluation seulement | — |
| [Marketaux](https://www.marketaux.com/documentation) | Clé | 100 req/j, 3 articles | `countries=ca`, `language=fr` ; sentiment par entité | CGU introuvables | `published_at` |
| [Finnhub company-news](https://finnhub.io/docs/api/company-news) | Clé | 60/min (tiers) | Amérique du Nord, 1 an | Personnel ; pas de redistribution, même dérivée | — |
| [Massive news](https://massive.com/docs/rest/stocks/news) | Clé | 5/min (tiers) | Depuis 2016, 2 ans en Basic ; sentiment | « Individual use only » | `published_utc` |
| [Benzinga Basic](https://aws.amazon.com/marketplace/pp/prodview-xwgvhwowjmw3g) / [Alpaca news](https://docs.alpaca.markets/us/reference/news-3) / [Tiingo news](https://www.tiingo.com/documentation/news) | AWS Marketplace / clé / clé | — / 15 min de retard / 3 mois | Titre et accroche / résumé / tickers | Interne | `created_at` et `updated_at` ; `publishedDate` peut valoir l'heure de crawl |
| [Google News RSS](https://news.google.com/rss/search?q=Banque+du+Canada&hl=fr-CA&gl=CA&ceid=CA:fr) / [Yahoo RSS](https://feeds.finance.yahoo.com/rss/2.0/headline?s=RY.TO&region=CA&lang=en-CA) | Sans clé | — | fr-CA ; par ticker `.TO` | Personnel, non commercial | `pubDate` |
| [Radio-Canada](https://ici.radio-canada.ca/rss), [La Presse](https://www.lapresse.ca/affaires/rss), [Globe](https://www.theglobeandmail.com/privacy-terms/licensing-and-permissions/), [CBC](https://www.cbc.ca/webfeed/rss/rss-business), [Newswire.ca](https://www.newswire.ca/rss/news-releases-list.rss) | RSS sans clé | — | FR pour Radio-Canada et La Presse | Personnel ; titre et lien non commerciaux (Globe) | `pubDate` |
| [BdC](https://www.bankofcanada.ca/rss-feeds/), [Fed](https://www.federalreserve.gov/feeds/feeds.htm), [BCE](https://www.ecb.europa.eu/home/html/rss.en.html), [StatCan](https://www150.statcan.gc.ca/n1/dai-quo/rss-eng.htm), [BLS](https://www.bls.gov/feed/) | RSS/Atom sans clé | — | FR pour StatCan | Texte intégral réutilisable avec attribution | `dc:date`, `published` (avant l'heure officielle chez BLS) |
| [Gazette](https://gazette.gc.ca/rss/sc-rb-eng.html), [LEGISinfo](https://www.parl.ca/legisinfo/en/overview), [OpenParliament](https://openparliament.ca/api/), [Nouvelles Canada.ca](https://www.canada.ca/en/news/web-feeds.html) | Sans clé ; courriel dans le User-Agent pour OpenParliament | 429 possible (OpenParliament) | Bilingue | Canada.ca non commercial ; OpenParliament ne revendique aucun copyright | `publishedDate` |
| [Federal Register](https://www.federalregister.gov/api/v1/documents.json?per_page=1), [Congress.gov](https://github.com/LibraryOfCongress/api.congress.gov), [Regulations.gov](https://open.gsa.gov/api/regulationsgov/), [SEC RSS](https://www.sec.gov/news/pressreleases.rss) | Sans clé / clé api.data.gov | 10 000 résultats par requête ; 5 000/h ; 1 000/h par défaut | — | Contenu fédéral américain | `publication_date` future (FR) ; diffusion EDGAR décalée |
| [Reddit](https://r.datuan.dev/r/redditdev/s/gquSJqMgrM) / [X](https://postproxy.dev/blog/x-api-pricing-2026) / [Stocktwits](https://stocktwits.com/terms) | Approbation / paiement / interdit | — | — | À exclure | — |

Pour le sentiment, les jeux de référence portent des licences restrictives. `financial_phrasebank` est sous CC BY-NC-SA 3.0, et le modèle `ProsusAI/finbert` est désormais étiqueté CC BY-NC-SA 4.0 : la clause ShareAlike se propage à tout jeu dérivé ([PhraseBank](https://huggingface.co/datasets/takala/financial_phrasebank) ; [FinBERT](https://huggingface.co/ProsusAI/finbert)). Aucun jeu francophone de sentiment financier sous licence claire n'a été trouvé. Un LLM multilingue sur Bedrock reste l'option la plus défendable.

## Les données ESG ouvertes livrent des faits, jamais des scores

Aucune source gratuite de scores ESG d'entreprise n'est à la fois automatisable et redistribuable.

- yfinance expose encore `Ticker.sustainability` (Sustainalytics), mais les CGU Yahoo interdisent l'usage commercial et les robots ([CGU Yahoo](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html)).
- MSCI interdit les agents IA et les serveurs MCP ([MSCI](https://www.msci.com/legal/terms-of-use)).
- LSEG exige une approbation écrite, même pour une publication non commerciale ([LSEG](https://www.lseg.com/en/data-analytics/sustainable-finance/esg-scores)).
- ESG Book a fusionné avec EthiFinance en juillet 2026 ([ESG Today](https://www.esgtoday.com/ethifinance-esg-book-merge-to-form-european-sustainability-and-credit-rating-champion/)).

La bonne réponse est un profil ESG factuel, sourcé et explicable, construit à partir des sources ci-dessous.

**Émissions par installation.**

- Le GHGRP canadien (OGL–Canada) couvre 2004 à 2024, au seuil de 10 kt. Ses 82 colonnes incluent la dénomination sociale du déclarant, le numéro d'entreprise, le DUNS et le code SCIAN ([GHGRP](https://open.canada.ca/data/en/dataset/a8ba14b7-7f23-462a-bdbb-83b0ef629823)). Les agrégats 2024 donnent environ 18,6 Mt pour Canadian Natural, 13,6 Mt pour Imperial Oil (l'empreinte canadienne de fait de XOM) et 0,75 Mt pour Enbridge sous son propre nom ([datamart ECCC](https://data-donnees.ec.gc.ca/data/substances/monitor/greenhouse-gas-reporting-program-ghgrp-facility-greenhouse-gas-ghg-data/)).
- Climate TRACE (API v7 sans clé, CC BY 4.0, mensuel de janvier 2015 à août 2026, version v5.12.0) n'attribue que 1,76 Mt à Canadian Natural, soit un écart d'un facteur dix. Son rattachement aux propriétaires est incomplet pour les sables bitumineux ([Climate TRACE metadata](https://api.climatetrace.org/v7/metadata) ; [conditions](https://climatetrace.org/terms)).
- Côté américain, Envirofacts s'arrête à l'année 2023, et l'abrogation du GHGRP de l'EPA reste pendante ([Envirofacts](https://data.epa.gov/efservice/pub_dim_facility/year/=/2024/rows/0:0/JSON) ; [Beveridge & Diamond](https://www.bdlaw.com/publications/with-federal-greenhouse-gas-reporting-in-limbo-states-expand-ghg-reporting/)).

**Exclusions et méthodologies citables.** La liste d'exclusion de NBIM, mise à jour le 11 août 2026, exclut Canadian Natural, Cenovus, Imperial et Suncor pour « Unacceptable greenhouse gas emissions ». Enbridge et Exxon n'y figurent pas, et la liste n'existe qu'en HTML ([NBIM](https://www.nbim.no/en/responsible-investment/ethical-exclusions/exclusion-of-companies/)). Les règles de l'indice d'ESGV (FTSE Global Choice, v5.0, août 2026) excluent les sous-secteurs Pipelines, Integrated Oil and Gas et Crude Producers, ainsi que toute société tirant au moins 5 % de ses revenus des sables bitumineux. C'est une justification publique de l'exclusion d'ENB, XOM et CNQ pour le persona à fort critère ESG, même si les données sous-jacentes (Sustainalytics, ICB) restent propriétaires ([FTSE ground rules](https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-choice-index-series-ground-rules.pdf)).

**Classifications sectorielles.** GICS est « exclusive property of MSCI and S&P Dow Jones Indices » et ne doit jamais être stocké, y compris les libellés de secteur des CSV iShares ([MSCI GICS](https://www.msci.com/downloads/documents/indexes/gics/MSCI%20GICS%20Overview.pdf)). Les substituts libres sont :

- le SIC de la SEC : ENB 4610, XOM 2911, CNQ 1311 ([EDGAR ENB](https://data.sec.gov/submissions/CIK0000895728.json)) ;
- le SCIAN 2022 sous Licence ouverte StatCan, dont une version 2027 est prévue en janvier 2027 ([SCIAN 2022](https://open.canada.ca/data/en/dataset/980d598c-73c9-4003-b6e1-78a9a3081b6c)) ;
- FinanceDatabase (MIT, taxonomie indépendante) ([FinanceDatabase](https://github.com/JerBouma/FinanceDatabase)).

| Source | Accès | Couverture, historique, fréquence | Licence et redistribution | Date à stocker |
|---|---|---|---|---|
| [GHGRP Canada](https://open.canada.ca/data/en/dataset/a8ba14b7-7f23-462a-bdbb-83b0ef629823) | CSV/XLSX sans clé | Installations ≥ 10 kt, 2004–2024 ; annuel | OGL–Canada, redistribuable | Année de référence et date du fichier (24 juillet 2026) |
| [INRP/NPRI](https://open.canada.ca/data/en/dataset/40e01423-7728-429c-ac9d-2954385ccdfb) | CSV | Rejets de polluants, 1993–2024 ; joint au GHGRP par l'ID INRP | OGL–Canada | Année de référence |
| [EPA Envirofacts](https://data.epa.gov/efservice/pub_dim_facility/parent_company/CONTAINING/EXXON/rows/0:2/JSON) (GHGRP, TRI) | API sans clé | US ; RY2023 au plus récent ; sociétés mères avec pourcentages | Non vérifiée | Année de référence (gel réglementaire) |
| [Climate TRACE v7](https://api.climatetrace.org/) | API sans clé | Mondial, mensuel 2015-01 à 2026-08 | CC BY 4.0, sauf jeux externes et champs « license restricted » | `dataVersion`, `releaseDate` |
| [SBTi Target Dashboard](https://sciencebasedtargets.org/target-dashboard) | XLSX | Cibles, ISIN et LEI ; chaque jeudi | Licence non explicite | Date du fichier |
| [Net Zero Tracker](https://zerotracker.net/data-terms-of-use) / [Carbon Majors](https://carbonmajors.org/Downloads) / [TPI](https://transitionpathwayinitiative.org/use-of-the-centre-s-data) | Téléchargement | Engagements ; émissions des producteurs jusqu'à 2024 ; trajectoires | CC BY-NC 4.0 / non commercial / robots interdits | — |
| [GOGEL 2026](https://gogel.org/terms-conditions-without-identifiers) | Inscription | ≈ 1 900 sociétés pétrolières et gazières (publiée le 10 novembre 2026) | Partage hors de l'organisation **interdit** | — |
| [GEM trackers](https://globalenergymonitor.org/projects/global-methane-emitters-tracker/download-data/) | Téléchargement | Actifs fossiles et propriétaires | CC BY 4.0 en majorité | Date de version |
| [NBIM](https://www.nbim.no/en/responsible-investment/ethical-exclusions/exclusion-of-companies/) | HTML seulement | 201 sociétés | Non précisée | Instantané daté (liste du 11 août 2026) |
| [OFAC](https://ofac.treasury.gov/sanctions-list-service) / [Sanctions Canada](https://www.international.gc.ca/world-monde/international_relations-relations_internationales/sanctions/consolidated-consolide.aspx?lang=eng) / [OpenSanctions](https://www.opensanctions.org/licensing/) | Sans authentification / XML / API | Listes de sanctions | Publiques / publiques / CC BY-NC 4.0 | Fichiers delta (OFAC) |
| [Banque mondiale ESG (source 75)](https://api.worldbank.org/v2/sources?format=json&per_page=100) | API sans clé | 80 indicateurs souverains, mis à jour le 24 juin 2026 | CC BY 4.0 | `lastupdated` |
| [ND-GAIN](https://gain.nd.edu/our-work/country-index/download-data/) / [Yale EPI 2026](https://epi.yale.edu/node/51226) | ZIP | Plus de 180 pays / 177 pays | Aucune licence nommée / CC BY-NC-SA 4.0 | Édition |
| [MSC GeoMet](https://api.weather.gc.ca/collections?f=json) / [Incidents REC](https://open.canada.ca/data/dataset/7dffedc4-23fa-440c-a36d-adf5a6cc09f1) / [physrisk](https://registry.opendata.aws/os-climate-physrisk/) | OGC API / CSV / bibliothèque | 104 collections climatiques / incidents pipeliniers depuis 2008 / aléas physiques | Licence ECCC (commercial permis) / OGL / Apache-2.0 | Date d'observation |
| Scores : [Yahoo](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html), [MSCI](https://www.msci.com/legal/terms-of-use), [LSEG](https://www.lseg.com/en/data-analytics/sustainable-finance/esg-scores), [Finnhub](https://finnhub.io/pricing), FMP | — | — | **Interdits ou payants** | — |

Les incidents pipeliniers de la REC offrent un indicateur de controverse officiel, gratuit et propre à Enbridge, plus défendable qu'un score de controverse propriétaire ([REC](https://open.canada.ca/data/dataset/7dffedc4-23fa-440c-a36d-adf5a6cc09f1)). À l'inverse, GOGEL doit rester hors de la base partagée. Ses conditions limitent l'usage à la recherche interne non commerciale et interdisent tout partage hors de l'organisation, alors même qu'elle contient très probablement CNQ et XOM.

## A5 doit millésimer lui-même ce que les API ne millésiment pas

L'exigence de séparer la date d'observation et la date de publication se heurte à une réalité simple : la plupart des API ne servent que la dernière valeur révisée. Une poignée de mécanismes natifs suffit pourtant à couvrir les séries qui bougent le plus.

| Mécanisme | Source | Ce qu'il permet | Limite connue |
|---|---|---|---|
| `realtime_start/end`, `vintage_dates`, `output_type=4` | [ALFRED](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) | Valeur connue à la date D, premières publications, calendrier futur | Clé requise ; séries tierces sous copyright |
| Tableaux temps réel et calendrier JSON | [StatCan](https://www.statcan.gc.ca/en/dai/btd/rct) | Millésimes depuis 2015 pour 19 séries ; dates de diffusion depuis 2012 | 18-10-0259 en retard ; 20-10-0081 archivé ; IPC global, EPA et mises en chantier sans millésimes |
| Groupes par édition | [Valet](https://www.bankofcanada.ca/valet/lists/groups/json) | État de l'information à chaque RPM, EPE ou CSCE ; projections SWP | SWP s'arrête à 2019T4 |
| Dataflows `*_VINTAGE` | [FMI](https://api.imf.org/external/sdmx/3.0/structure/dataflow/*/*/+?detail=allstubs) | WEO d'avril 2026 et d'octobre 2025 ; millésimes mensuels CPI, ER, MFS | Millésime WEO d'octobre 2026 non identifié |
| EO 114–119, `DF_STES_REVISIONS` | [OCDE](https://sdmx.oecd.org/public/rest/dataflow/all/all/latest) | Prévisions par édition ; révisions des statistiques conjoncturelles | Contenu des révisions non inspecté |
| `RTD`, `includeHistory`, `updatedAfter` | [BCE](https://data.ecb.europa.eu/help/api/data) | Historique des versions et deltas | Comportement d'`includeHistory` non testé |
| `prc_hicp_fp` | [Eurostat](https://db.nomics.world/Eurostat/prc_hicp_fp?tab=table) | Premières publications de l'IPCH | Rupture COICOP 2018 en 2026 |
| RTDSM, FRED-MD/QD, archives GDPNow | [Philly Fed](https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-for-macroeconomists), [St. Louis Fed](https://www.stlouisfed.org/research/economists/mccracken/fred-databases) | Millésimes depuis 1965 ; fichiers mensuels par millésime | Excel ou CSV, pas d'API |
| `filed`, `accn`, `acceptanceDateTime` | [SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Date de publication à la seconde pour chaque fait XBRL | `frames` renvoie le « last filed » |
| `PUBLICATION_DATE` ; `revisionIndicator` ; `dataVersion` | [FMI PCPS](https://api.imf.org/external/sdmx/2.1/data/IMF.RES,PCPS/G001.PGOLD.USD.M?startPeriod=2026-08) ; [NY Fed](https://markets.newyorkfed.org/api/rates/secured/sofr/last/2.json) ; [Climate TRACE](https://api.climatetrace.org/v7/metadata) | Date de publication explicite ; drapeau de révision ; version du jeu | Pas d'historique des valeurs |

**Les pièges de dates.** Plusieurs champs fréquemment pris pour des dates de publication n'en sont pas :

- le `releaseTime` de WDS est écrasé à chaque révision ;
- `frames` de la SEC renvoie le fait retraité ;
- le `filing_date` de Massive et la `Publish Date` de SimFin sont postérieures à la première publication ;
- les observations Valet sont datées au début de la période de référence ;
- le Federal Register expose des `publication_date` futures ;
- l'entrée RSS du BLS précède l'heure officielle ;
- le COT de la CFTC porte la date du mardi mais n'est mis en ligne que le vendredi vers 15 h 30 ET ([CFTC](https://publicreporting.cftc.gov/resource/6dca-aqww.json)) ;
- les métadonnées CKAN datent l'ajout au catalogue, pas la publication.

Pour toutes les sources sans millésime (Valet, BRI, BoE, BoJ, Fiscal Data, CKAN, prix de marché, avoirs de FNB), la seule protection contre le look-ahead est un archivage prospectif par A5. Il s'agit d'un instantané horodaté de chaque réponse, conservé avec les en-têtes `Last-Modified` et `ETag`, et du Delta File de StatCan copié dans S3 avant qu'il ne sorte de sa fenêtre d'environ deux mois.

**Champs OKF recommandés.**

| Champ | Contenu |
|---|---|
| `observation_date` | Date de référence |
| `publication_datetime_utc` et `publication_datetime_local` | Date du calendrier officiel, sinon `acceptanceDateTime` ou `realtime_start`, sinon la date de collecte |
| `realtime_start`, `realtime_end` ou `vintage_id` | Millésime |
| `retrieved_at` | Horodatage de collecte (UTC) |
| `source_url`, `endpoint` | Requête exacte |
| `licence`, `licence_url`, `attribution_text` | Texte exact de la mention (par exemple « Source: Statistics Canada, Table 18-10-0004-01… ») |
| `redistribution` | Oui, non ou inconnu |
| `adjustment` | Brut, splits, ou splits et dividendes |
| `data_version` | Version du jeu de données |

L'ordonnanceur doit aussi suivre les horaires des sources :

- éviter WDS entre 0 h et 8 h 35 HE et collecter vers 8 h 45 les jours de diffusion, pilotés par le calendrier JSON ;
- collecter Valet après 17 h HE pour le change et les taux ;
- lire FRED via ALFRED pour les simulations historiques, afin de respecter les dates de disponibilité réelles des publications reportées par les shutdowns de 2025 et 2026 ([BEA](https://www.bea.gov/news/blog/2025-12-10/economic-release-schedule-updates) ; [WTOP](https://wtop.com/business-finance/2026/02/labor-department-delays-january-jobs-report-because-of-partial-shutdown/)).

## Conclusion

La revue renverse l'intuition de départ. Le problème d'AlphaForge n'est pas de trouver assez de données gratuites : les sources officielles canadiennes, américaines et internationales en offrent plus qu'A5 ne peut en ingérer, sans clé et sous des licences qui autorisent la redistribution. Le problème est que les trois sources les plus utiles au portefeuille d'un investisseur canadien sont celles que la licence ferme : prix TSX, fondamentaux de sociétés comme ATD et CSU, et avoirs des FNB canadiens. La base générale doit donc être pensée en deux zones. La première est un noyau officiel, redistribuable et millésimé, qui fait foi. La seconde est un cache de sources commerciales, gardé hors de la base partagée, d'où ne sortent que des signaux dérivés et des liens. Cette séparation, imposée par A6 à partir du champ `redistribution`, constitue en elle-même un argument d'explicabilité et de gouvernance devant un jury de la Banque Nationale.

Trois actions découlent de ce constat :

- Obtenir rapidement le petit nombre de clés gratuites nécessaires : FRED, BLS v2, BEA, Census, EIA, api.data.gov, CoinGecko Demo, Alpha Vantage (en demandant l'accès éducatif), OpenFIGI et Comtrade.
- Faire trancher par écrit, par les organisateurs, deux questions que les CGU laissent ouvertes : le datathon est-il un « usage commercial », et la base commune constitue-t-elle une « redistribution » ?
- Lancer dès maintenant l'archivage horodaté, qui conditionne le point-in-time. Les millésimes natifs ne couvrent que les séries les plus révisées (PIB, commerce, IPC de base, séries ALFRED). Pour tout le reste, chaque jour de collecte non archivé est un jour d'historique « tel que connu » définitivement perdu.
