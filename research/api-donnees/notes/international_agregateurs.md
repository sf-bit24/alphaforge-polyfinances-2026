# API de données économiques internationales et agrégateurs (état au 14-15 novembre 2026)

Méthode : recherche web, lecture des docs et des pages de conditions officielles, et **tests en direct avec `curl` le 14-15 novembre 2026** (horodatage serveur UTC). Quand la source d'un fait est un test en direct, le lien pointe vers l'URL exacte interrogée, et le résultat observé est indiqué. Une URL d'API interrogée sert alors de preuve « live » : elle montre que le point d'accès répondait à cette date, pas qu'il est documenté ou garanti.

---

## (A) Inventaire des API officielles internationales : fiches

### Takeaway
Les grandes API officielles (FMI, Banque mondiale, OCDE, BRI, BCE, Eurostat, Bundesbank, BoE, BoJ) répondaient toutes **sans clé** en novembre 2026, et presque toutes couvrent le Canada. Les vraies contraintes sont ailleurs : les **conditions de réutilisation** (FMI : permission requise pour l'usage commercial et le téléchargement automatisé en masse ; Eurostat : pas de réutilisation commerciale des données non européennes ; RBA : tous droits réservés), les **quotas** (OCDE : 60 téléchargements/heure) et des **migrations récentes** (nouveau portail FMI et retrait d'IFS, HICP en COICOP 2018).

### Cited Findings

#### FMI : IMF Data, API SDMX 2.1 / 3.0 (remplace l'ancienne API JSON RESTful)
- Selon la page officielle, les données sont servies par deux API, SDMX 2.1 et SDMX 3.0. La documentation Swagger (https://portal.api.imf.org/apis#tags=iData) demande une connexion avec un compte du portail. Le support est datahelp@imf.org. La page ne mentionne **ni clé ni quota** — [IMF API page](https://data.imf.org/en/Resource-Pages/IMF-API)
- Base SDMX 3.0 : `https://api.imf.org/external/sdmx/3.0`. Base SDMX 2.1 : `https://api.imf.org/external/sdmx/2.1`. Les deux ont répondu HTTP 200 **sans clé ni en-tête d'abonnement** le 15 nov. 2026 — [test live SDMX 3.0](https://api.imf.org/external/sdmx/3.0/structure/dataflow/*/*/+?detail=allstubs) ; [test live SDMX 2.1](https://api.imf.org/external/sdmx/2.1/dataflow)
- Le catalogue comptait **231 dataflows, dont 105 hors millésimes**. On y trouve notamment `IMF.RES:WEO` (v9.0.0), `IMF.STA:COFER` (v7.0.1), `CPI`, `ER`, `EER`, `IL`, `IRFCL`, `MFS_*` (CBS, DC, IR, FMP, MA, ODC, OFC…), `BOP`, `IIP`, `FSIC`, `PCPS` (prix des matières premières), `QNEA`/`ANEA`, `GFS_*`, `GDD` et `HPD` (dette), `FM` (Fiscal Monitor), `WHDREO`. **Il n'existe plus de dataflow « IFS »** — [catalogue live](https://api.imf.org/external/sdmx/3.0/structure/dataflow/*/*/+?detail=allstubs)
- Une requête WEO pour le Canada (CAN.NGDP_RPCH.A) a renvoyé du JSON SDMX 2.0 (structure `dataSets/observations`). Une requête COFER avec `lastNObservations=1` a aussi fonctionné — [test WEO Canada](https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/+/CAN.NGDP_RPCH.A?c%5BTIME_PERIOD%5D=ge:2025&dimensionAtObservation=AllDimensions) ; [test COFER](https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/COFER/+/*?lastNObservations=1)
- **IFS a été retiré** et son contenu réparti entre plusieurs dataflows thématiques. Le paquet R `readimf` fournit une table de correspondance (`imf_ifs_map()`) entre les anciennes séries IFS et la nouvelle structure — [readimf README (CRAN)](https://cran.r-project.org/web/packages/readimf/readme/README.html)
- L'ancien service web SDMX (sdmxws.imf.org) affiche « web site is decommissioned. Please use our new IMF Data Services » — [page IMF sdmxws](https://extauth.imf.org/maintenance/sdmxws-decommissioned.htm). L'ancien hôte `dataservices.imf.org/REST/SDMX_JSON.svc` n'a renvoyé aucune réponse lors de notre test (connexion échouée, code 000) — [URL testée](https://dataservices.imf.org/REST/SDMX_JSON.svc/Dataflow). Un README tiers date sa mise hors service à 2025 — [imf-data-mcp README](https://cdn.jsdelivr.net/gh/c-cf/imf-data-mcp@main/README.md)
- Le FMI publie un guide de transition pour la base WEO (non lu en détail ici) — [WEO Database Transition Guide (PDF)](https://data.imf.org/-/media/iData/External-Storage/Documents/DDAF479A0D474D01AA7E1B8435396BFD/en/WEO_Database_Transition_Guide.pdf)
- L'API DataMapper (`/external/datamapper/api/v1/`) répond toujours en JSON. Dans notre test, la réponse commençait toutefois par d'autres pays que CAN : le filtre pays n'a peut-être pas été appliqué, à vérifier — [test DataMapper](https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH/CAN)
- **Licence et conditions.** Les données FMI peuvent être téléchargées, extraites, copiées, transformées en œuvres dérivées, publiées et distribuées, avec une attribution obligatoire du type « Source: International Monetary Fund, Database Name, <<lien>> ». Il est interdit d'altérer les données d'une façon qui en affecte la nature ou l'exactitude, et toute transformation substantielle doit être signalée. Un revendeur doit informer ses acheteurs que les données sont gratuites auprès du FMI. **Pour tout usage commercial potentiel, il faut écrire à copyright@imf.org.** Celui qui redistribue doit promouvoir le respect de ces conditions par ses propres utilisateurs. Enfin, les conditions générales stipulent : « The IMF prohibits bulk download of information by automated technology without explicit permission » — [IMF Copyright and Usage](https://www.imf.org/en/about/copyright-and-terms) (version .md : https://www.imf.org/en/about/copyright-and-terms/index.md)
- Couverture : le Canada est présent (test WEO CAN ci-dessus). La fréquence va de mensuelle à annuelle selon le dataflow.

#### Banque mondiale : Indicators API v2 et Data360
- Indicators API v2 : `https://api.worldbank.org/v2/`. Le test pour le PIB du Canada a renvoyé du JSON avec `lastupdated: 2026-11-11` et une valeur 2025, sans clé — [test live](https://api.worldbank.org/v2/country/CA/indicator/NY.GDP.MKTP.CD?format=json&per_page=2)
- La v1 de l'API Indicators a été retirée en novembre 2018 — [About the Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api)
- Sources disponibles via l'API (date de dernière mise à jour) : 2 = WDI (2026-11-11) ; 6 = International Debt Statistics (2026-11-05) ; 15 = Global Economic Monitor (2026-09-08) ; 27 = Global Economic Prospects (2026-06-11) ; **57 = WDI Database Archives (2025-10-29)** — [liste live des sources](https://api.worldbank.org/v2/sources?format=json&per_page=100)
- **Licence.** Sauf mention contraire dans les métadonnées de l'indicateur, l'usage commercial et non commercial est libre sous **CC BY 4.0**, avec une clause obligatoire de médiation en cas de litige — [Summary Terms of Use](https://data.worldbank.org/summary-terms-of-use). Il ne faut pas laisser entendre un soutien de la Banque mondiale ni utiliser son nom ou son logo — [Terms of Use for Datasets](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets)
- Quotas : aucune limite officielle trouvée. Les recommandations de « 1-2 requêtes/s » proviennent de guides tiers non officiels — [résumé de recherche, sources tierces](https://econindx-site.pages.dev/guides/getting-started-world-bank)
- **Data360** : l'API est annoncée sur data360.worldbank.org/en/api. Data360 repose sur le Data Catalog de la Banque et a été fusionné dans data.worldbank.org — [What is Data360?](https://data360.worldbank.org/en/int/about). Base testée : `https://data360api.worldbank.org/data360/data?DATABASE_ID=WB_WDI&INDICATOR=WB_WDI_NY_GDP_MKTP_CD&REF_AREA=CAN`. Elle renvoie du JSON de style SDMX (champs `OBS_STATUS`, `OBS_CONF`, `LATEST_DATA`, `TIME_PERIOD`…), sans clé — [test live Data360](https://data360api.worldbank.org/data360/data?DATABASE_ID=WB_WDI&INDICATOR=WB_WDI_NY_GDP_MKTP_CD&REF_AREA=CAN&top=2)
- Un point SDMX WDI existe aussi (`https://api.worldbank.org/v2/sdmx/rest`, référencé comme source `WB_WDI` dans sdmx1) — [sdmx1 sources.json](https://github.com/khaeru/sdmx/blob/main/sdmx/sources.json)

#### OCDE : Data Explorer, API SDMX (après la migration de 2024)
- Base : `https://sdmx.oecd.org/public/rest`. Un test sur le CLI du Canada a renvoyé du CSV SDMX avec une observation pour 2026-10, sans clé — [test live](https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.1/CAN.M.LI...AA...H?lastNObservations=1&format=csvfile)
- L'ancien `stats.oecd.org/SDMX-JSON/...` renvoie désormais une redirection 301 vers `sdmx.oecd.org/public/rest/...` — [URL testée](https://stats.oecd.org/SDMX-JSON/data/QNA/CAN.B1_GE.GYSA.Q/all?startTime=2024)
- **Quota.** La page officielle indique « maximum of 60 data downloads per hour » (limite qui s'applique aussi aux CSV du Data Explorer) — [OECD API rate limiting](https://www.oecd.org/en/data/insights/data-explainers/2024/11/Api-best-practices-and-recommendations.html). Ce chiffre est **contredit** par le miroir oecd-ilibrary, qui annonce 20 requêtes/minute et 20 téléchargements/heure (probablement une version antérieure) — [miroir](https://read.oecd-ilibrary.org/en/data/insights/data-explainers/2024/11/Api-best-practices-and-recommendations.html). Un dépassement entraîne un blocage temporaire.
- **Restrictions de paramètres (mars 2026).** Certains paramètres de requête sont bloqués, en appel API direct seulement, pour quelques très gros jeux publics (`DSD_BATIS@DF_BATIS`, `DSD_ECH@EXT_TEMP_P`) — [API query parameter restrictions](https://www.oecd.org/en/data/insights/data-explainers/2026/03/Restricted-API-parameter.html). Une annonce du 28 oct. 2025 visait les jeux de plus d'un milliard d'observations dans les espaces TiVA et CRS — [OECD Data Explorer News](https://www.oecd.org/en/data/insights/data-explainers/2025/02/OECD-Data-Explorer-News.html)
- **Licence : CC BY 4.0 pour les contenus publiés à partir du 1er juillet 2024.** Les contenus plus anciens restent sous les T&C de l'OCDE, « broadly similar » à CC BY — [communiqué juillet 2024](https://www.oecd.org/en/about/news/press-releases/2024/07/oecd-data-publications-and-analysis-become-freely-accessible.html) ; [Open by default policy](https://oecd.org/en/about/oecd-open-by-default-policy.html)
- Le catalogue comptait 1 553 dataflows au moment du test — [liste live](https://sdmx.oecd.org/public/rest/dataflow/all/all/latest)
- Pages de documentation : www.oecd.org renvoie un défi JavaScript Cloudflare (« Just a moment… ») aux clients automatisés, et WebFetch a reçu un 403 (constaté le 15 nov. 2026).

#### BRI : BIS Data Portal API (taux directeurs, crédit, prix immobiliers, taux de change effectifs)
- API v2 : `https://stats.bis.org/api/v2`, documentation Swagger sur https://stats.bis.org/api-doc/v2/. Le dataflow `WS_CBPOL` (taux directeurs), série quotidienne du Canada, a renvoyé **2,5 % au 2026-11-09**, avec une métadonnée de source « Bank of Canada », en CSV et sans clé — [test live](https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.CA?lastNObservations=1&format=csv) ; [doc v2](https://stats.bis.org/api-doc/v2/)
- **Conditions.** L'usage des statistiques est défini par la rubrique « About BIS statistics ». Il est libre à condition notamment de ne pas induire en erreur (pas de suggestion d'aval ou d'affiliation). L'API est fournie « as is » : la BRI peut la suspendre, publier de nouvelles versions qui cassent les anciennes et surveiller l'usage. Droit suisse applicable — [data.bis.org legal](https://data.bis.org/help/legal) ; [permitted use of BIS statistics](https://www.bis.org/about/legal/permitted-use-statistics). Ces pages étaient inaccessibles en lecture automatisée (403) : contenu repris de résumés de recherche, **à relire manuellement**.
- Les autres dataflows (crédit total, écart de crédit, prix immobiliers, taux de change effectifs) n'ont **pas** été vérifiés individuellement dans ce test.

#### BCE : ECB Data Portal API (ex-SDW)
- Base : `https://data-api.ecb.europa.eu/service/`. La série EXR D.CAD.EUR a renvoyé **1,5758 au 2026-11-13** en CSV, avec les en-têtes `last-modified` et `cache-control: max-age=30`, sans clé — [test live](https://data-api.ecb.europa.eu/service/data/EXR/D.CAD.EUR.SP00.A?lastNObservations=1&format=csvdata)
- Paramètres documentés : `startPeriod`, `endPeriod`, **`updatedAfter`** (deltas : mises à jour et révisions), `firstNObservations`, `lastNObservations`, `detail`, **`includeHistory`**. L'en-tête `If-Modified-Since` est accepté — [ECB API Data](https://data.ecb.europa.eu/help/api/data)
- **Licence et politique de réutilisation.** Les statistiques sont gratuites quel que soit l'usage, commercial ou non, à condition de citer la source (« Source: ECB statistics. »). Les données et métadonnées ne doivent pas être modifiées. Les données de tiers sont exclues sans permission. Aucune continuité des séries n'est garantie — [ECB usage policy](https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html)
- Couverture du Canada : indirecte seulement (taux de change contre l'euro, etc.).

#### Eurostat
- API JSON-stat 2.0 : `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}` — [test live](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr?geo=EA&coicop=CP00&lastTimePeriod=1). Il existe aussi des points SDMX 2.1 et 3.0 (`.../api/dissemination/sdmx/2.1` et `/3.0`) — [sdmx1 sources.json](https://github.com/khaeru/sdmx/blob/main/sdmx/sources.json). Pas de clé.
- Le test sur `prc_hicp_manr` a renvoyé `"updated":"2026-02-06T23:00:00+0100"`. Le jeu semble **figé depuis le passage du HICP en COICOP 2018 / ECOICOP v2** avec la base 2025=100, appliqué aux données de janvier 2026 publiées en février 2026 — [test live](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr?geo=EA&coicop=CP00&lastTimePeriod=1) ; [Statistics Poland, HICP](https://stat.gov.pl/en/topics/prices-trade/price-indices/harmonized-indices-of-consumer-prices-hicp,15,1.html) ; [ECB Economic Bulletin box 2026/03](https://www.ecb.europa.eu/press/economic-bulletin/focus/2026/html/ecb.ebbox202603_07~c015bf3c71.de.html). Le nouveau jeu `prc_hicp_minr` (ECOICOP v2) n'est attesté que par une source secondaire — [fgeerolf mirror](https://fgeerolf.com/data/eurostat/prc_hicp_minr.html)
- **Licence.** Les données sont réutilisables à des fins commerciales ou non, à condition de citer la source (décision de la Commission du 12 déc. 2011). **Exception : les données provenant d'autres sources qu'Eurostat**, par exemple celles des États-Unis, du Japon ou de la Chine, ne sont pas réutilisables commercialement et doivent être retirées des tableaux avant un usage commercial. Le contenu éditorial est sous CC BY 4.0 — [Eurostat copyright notice](https://ec.europa.eu/eurostat/help/copyright-notice)

#### ONU : UNdata/UNSD, UN Comtrade, ILOSTAT, OMC, FAO
- **UNdata SDMX** : `data.un.org/ws/rest/` redirige (302) vers `data.un.org/legacy/ws/rest/` (NSI Web Service v8.15.1.0) — [test live](https://data.un.org/legacy/ws/rest/dataflow/). Le client sdmx1 pointe encore vers `http://data.un.org/WS/rest` — [sdmx1 sources.json](https://github.com/khaeru/sdmx/blob/main/sdmx/sources.json)
- **API ODD de l'UNSD** : `https://unstats.un.org/sdgapi/v1/` répond en JSON, sans clé — [test live](https://unstats.un.org/sdgapi/v1/sdg/Goal/List?includechildren=false)
- **UN Comtrade.** Le point « preview » public fonctionne sans clé (test Canada → États-Unis, exportations 2024, HS TOTAL) — [test live](https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode=124&period=2024&partnerCode=842&cmdCode=TOTAL&flowCode=X). Le niveau gratuit avec clé offre **500 appels/jour** et jusqu'à **100 000 enregistrements par appel**, la clé s'obtenant gratuitement sur le portail développeur — [Comtrade wiki, abonnements](https://comtradewiki.azurewebsites.net/?p=78). La clé se passe dans l'en-tête `Ocp-Apim-Subscription-Key` — [jentic, spécification Comtrade](https://jentic.com/apis/comtrade.un.org/comtrade-un.md). Client Python officiel : `comtradeapicall` — [PyPI](https://pypi.org/project/comtradeapicall/1.1.0/)
- **ILOSTAT.** L'API « rplumber » renvoie du CSV avec le taux de chômage du Canada pour 2025, sans clé — [test live](https://rplumber.ilo.org/data/indicator/?id=UNE_DEAP_SEX_AGE_RT_A&ref_area=CAN&format=.csv). `sdmx.ilo.org/rest` a renvoyé **403** à notre client (protection anti-robots probable), et `www.ilo.org/sdmx` redirige (301) vers `webapps.ilo.org/sdmx` — [URL testée](https://sdmx.ilo.org/rest/dataflow/ILO?detail=allstubs)
- **OMC (WTO Timeseries API).** `https://api.wto.org/timeseries/v1` renvoie 401 « missing subscription key » sans clé — [test live](https://api.wto.org/timeseries/v1/indicators?lang=1). Le portail annonce une clé gratuite et immédiate (« sign up for an API key and start consuming APIs right away. It is free. ») — [WTO API portal](https://apiportal.wto.org/). Les quotas de 50/h sans clé et 500/h avec clé ne viennent que d'une source tierce, non vérifiée — [jentic WTO](https://jentic.com/apis/apiportal.wto.org/wto-timeseries)
- **FAO (FAOSTAT).** Un nouveau portail développeur a été annoncé le **13 avril 2026** (sorties JSON et CSV, connexion requise) — [annonce FAO](https://www.fao.org/statistics/highlights-archive/highlights-detail/faostat-launches-a-new-api-developer-portal-to-make-data-access-easier/en). L'ancien point `fenixservices.fao.org/faostat/api/v1` a renvoyé **HTTP 521** lors du test — [URL testée](https://fenixservices.fao.org/faostat/api/v1/en/definitions/domain). Un serveur MCP tiers s'authentifie par jeton ou par identifiant et mot de passe, avec rafraîchissement JWT — [faostat-mcp](https://glama.ai/mcp/servers/berba-q/faostat-mcp)

#### Banques centrales hors Canada et États-Unis
- **Bank of England (IADB).** L'export CSV par URL fonctionne : la série IUDBEDR (Bank Rate) était à 3,75 en octobre 2026, sans clé — [test live](https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Oct/2026&Dateto=now&SeriesCodes=IUDBEDR&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N). **La reproduction des données de la Database relève de l'UK Open Government Licence.** La Banque peut restreindre l'accès en cas d'« excessive use » et ne garantit pas la continuité des séries — [BoE Legal](https://www.bankofengland.co.uk/legal). Cela tranche la contradiction avec une ancienne mention « no commercial use » citée par DataHub — [DataHub](https://datahub.io/core/bond-yields-uk-10y)
- **Bank of Japan.** L'« API service for BOJ Time-Series Data Search » a été **lancé le 18 février 2026** et sert du JSON et du CSV — [BoJ notice](https://www.boj.or.jp/en/statistics/outline/notice_2026/not260218a.htm) ; [manuel API (PDF)](https://www.stat-search.boj.or.jp/info/api_manual_en.pdf). Le point `https://www.stat-search.boj.or.jp/api/v1/getDataCode?format=json&lang=en&db=FM01&code=STRDCLUCON` a répondu sans clé — [test live](https://www.stat-search.boj.or.jp/api/v1/getDataCode?format=json&lang=en&db=FM01&code=STRDCLUCON&startDate=202601). **Conditions** : notifier la BoJ par courriel (post.rsd17@boj.or.jp) lors de la mise en service d'une application utilisant l'API ; afficher la mention « This service uses the API provided by the "Bank of Japan Time-Series Data Search." The Bank of Japan does not guarantee the content of the service. » ; pas d'accès excessif ; la BoJ peut limiter ou suspendre l'accès — [Notice Regarding the Use of the API Service (PDF)](https://www.stat-search.boj.or.jp/info/api_notice_en.pdf)
- **Reserve Bank of Australia.** Pas d'API : seulement des tableaux CSV. Notre client a reçu un 403 (Akamai) sur `rba.gov.au/statistics/tables/` et sur les CSV. Le copyright est « all other rights are reserved » hors permissions explicites, avec une mention de source du type « Source: Reserve Bank of Australia [year] » — [RBA copyright](https://www.rba.gov.au/copyright/) ; [test live 403](https://www.rba.gov.au/statistics/tables/csv/f1-data.csv). Un paquet R `readrba` existe — [readrba](https://rdrr.io/cran/readrba)
- **Deutsche Bundesbank.** API SDMX `https://api.statistiken.bundesbank.de/rest` ; test BBEX3 CAD/EUR en CSV réussi sans clé — [test live](https://api.statistiken.bundesbank.de/rest/data/BBEX3/D.CAD.EUR.BB.AC.000?lastNObservations=1&format=csv). Conditions SEBC identiques à celles de la BCE — [Bundesbank terms of reuse of ESCB statistics](https://www.bundesbank.de/en/homepage/user-information/terms-of-use-regarding-the-reuse-of-escb-statistics-621188)
- **Banque de France (Webstat).** API Opendatasoft Explore v2.1 (`webstat.banque-france.fr/api/explore/v2.1/`). Les en-têtes observés indiquent un quota anonyme de **5 000 requêtes/jour** (`x-ratelimit-limit: 5000`, remise à zéro quotidienne) — [test live](https://webstat.banque-france.fr/api/explore/v2.1/catalog/datasets?limit=1). Le contenu du catalogue renvoyé n'a pas été analysé.
- **Banca d'Italia (Infostat).** `infostat.bancaditalia.it/inquiry/ws/rest/dataflow` a renvoyé 401 — [URL testée](https://infostat.bancaditalia.it/inquiry/ws/rest/dataflow)

#### OPEP et AIE
- **Panier OPEP.** Le flux `opec.org/basket/basketDayArchives.xml` est derrière un défi Cloudflare (403 pour un client automatisé) — [URL testée](https://www.opec.org/basket/basketDayArchives.xml)
- **AIE.** Les jeux gratuits du WEO 2025 sont sous **CC BY-NC-SA 4.0**, donc non commerciaux — [IEA WEO 2025 free dataset](https://www.iea.org/data-and-statistics/data-product/world-energy-outlook-2025-free-dataset). L'AIE a annoncé viser l'ouverture gratuite de toutes ses données, sans licence ni calendrier publiés — [OWID, free data IEA](https://ourworldindata.org/free-data-iea). `api.iea.org` répond (404 sur le chemin testé) avec un en-tête `X-Ratelimit-Limit: 250`, mais aucune API publique documentée n'a été trouvée — [URL testée](https://api.iea.org/stats/indicator?COUNTRY=CANADA)

### Inferences
- Pour l'agent A5, la combinaison FMI (WEO, COFER, PCPS), OCDE (CLI, EO), BRI (taux directeurs dont BoC), BCE (taux de change CAD/EUR, RTD), Banque mondiale (WDI) et BoE/BoJ couvre l'essentiel du contexte macro international **sans aucune clé**. Seuls l'OMC, Comtrade (au-delà de la preview) et FAOSTAT exigent une inscription, qui reste gratuite et rapide d'après leurs portails.
- Les deux licences les plus contraignantes pour une base de connaissances redistribuée sont celle du **FMI** (permission pour l'usage commercial et pour le téléchargement automatisé en masse) et celle de la **RBA** (tous droits réservés). Pour un datathon non commercial, l'attribution suffit vraisemblablement. Le champ `licence` de chaque fiche OKF devrait néanmoins reproduire la clause exacte et l'URL des conditions.
- Les métadonnées SDMX (BRI : `SOURCE_REF`, `COMPILATION` ; BCE : `TITLE_COMPL`, `UNIT`) se prêtent à un mappage direct vers le front-matter YAML (origine, unité, méthode).

### Gaps
- Quotas officiels non documentés pour le FMI, la Banque mondiale, la BRI, la BCE, Eurostat, la BoE et la BoJ : aucun chiffre trouvé.
- Pages de conditions BRI (permitted-use) et OCDE (T&C complets) non lisibles automatiquement (403 / Cloudflare) : contenu repris de résumés de recherche.
- Licences d'ILOSTAT, d'UN Comtrade, de FAOSTAT et de l'API OMC : non vérifiées.
- Panier OPEP : aucune API ni licence vérifiée (blocage Cloudflare).
- Fed et autres banques centrales du G7 (Banca d'Italia, Banque de France en détail) : couverture partielle. FRED/ALFRED sont présumés traités par une autre note.
- Contenu du manuel API de la BoJ (liste complète des points d'accès, limites) : non lu, PDF non rendu.

---

## (B) Agrégateurs et bibliothèques unifiées : fiches

### Takeaway
**DBnomics** reste l'agrégateur gratuit le plus large (94 fournisseurs, 1,73 milliard de séries, sans clé), mais plusieurs de ses connecteurs (FMI, BRI, Banque mondiale, OIT, BoJ) n'ont pas été réindexés depuis 2024-2025. **OpenBB/ODP est repassé sous licence Apache 2.0 avec la V5 (29 sept. 2026)**, ce qui lève la contrainte AGPL. Trading Economics (compte guest supprimé), Econdb (authentification désormais requise) et Nasdaq Data Link (clé obligatoire) ne sont plus utilisables sans compte.

### Cited Findings

#### DBnomics
- API : `https://api.db.nomics.world/v22`, version 22.1.17. Le test a renvoyé **94 fournisseurs, 47 467 jeux de données et 1 728 178 976 séries**, sans clé — [test live](https://api.db.nomics.world/v22/providers?limit=1)
- Le service est gratuit et ne demande pas d'authentification — [DBnomics FAQ](https://docs.db.nomics.world/faq/). Annonce : « rate limits will soon apply to requests made without an API key » — [forum DBnomics](https://dbnomics.discourse.group/t/dbnomics-site-update-new-features-and-improvements/984). Des plafonds d'usage équitable s'appliquent — [DBnomics sponsorship](https://db.nomics.world/sponsorship)
- **Licence.** Les données suivent la licence et les conditions du fournisseur d'origine. Les jeux agrégés par DBnomics sont sous **ODbL**. La plupart des fetchers sont sous **AGPLv3+** — [DBnomics Legal Terms](https://docs.db.nomics.world/legal-terms/). DBnomics ne redistribue pas les données payantes ou non redistribuables — [FAQ](https://docs.db.nomics.world/faq/)
- **Fraîcheur par fournisseur (champ `indexed_at`, 15 nov. 2026).** Récents : BOC 2026-11-14, STATCAN 2026-11-12, BOE 2026-11-14, ECB 2026-11-11, FED 2026-11-12, BEA 2026-11-12, RBA 2026-11-12, WTO 2026-11-12, AMECO 2026-11-14, UNDATA 2026-11-11, BDF 2026-11-12. Plus anciens : OECD 2026-06-16, BUBA 2026-07-06, Eurostat 2026-01-22, **IMF 2025-09-04**, **BIS 2025-07-10**, **WB 2024-09-19**, **ILO 2024-02-20**, **BOJ 2024-06-18**, FAO 2024-06-03, BLS 2026-03-25 — [liste live des fournisseurs](https://api.db.nomics.world/v22/providers?limit=200)
- Client Python : `dbnomics` 1.2.7 (2025-06-18), licence **GNU AGPL** — [PyPI dbnomics](https://pypi.org/project/dbnomics/)

#### Nasdaq Data Link (ex-Quandl)
- Sans clé, l'appel à une datatable renvoie 403 avec le code `QEPx04` (« A valid API key is required to retrieve data ») et l'en-tête `x-ratelimit-limit: 50`. L'endpoint `/api/v3/datasets/` est protégé par Incapsula (403 pour curl) — [test datatables](https://data.nasdaq.com/api/v3/datatables/NDAQ/RTAT10.json?qopts.per_page=1) ; [test datasets](https://data.nasdaq.com/api/v3/datasets/FRED/GDP.json?rows=1)
- Selon la doc officielle relayée par la recherche, l'accès anonyme est limité à 20 appels par 10 minutes et 50 par jour — [Nasdaq rate limits](https://docs.data.nasdaq.com/docs/rate-limits-1). Les utilisateurs de jeux gratuits sont limités à un appel à la fois, plus un en file — [Nasdaq getting started](https://docs.data.nasdaq.com/v1.0/docs). Les quotas avec clé gratuite (300/10 s, 2 000/10 min, 50 000/jour) ne proviennent que d'une source GitHub ancienne et non officielle — [EconMaett/Quandl](https://github.com/EconMaett/Quandl)
- Le client Python `nasdaq-data-link` en est à la version 1.0.4, **dernière publication le 2022-08-29** — [PyPI](https://pypi.org/project/nasdaq-data-link/). Le dépôt a été poussé pour la dernière fois en sept. 2026 — [GitHub API](https://api.github.com/repos/nasdaq/data-link-python)
- La base WIKI (cours d'actions) est arrêtée depuis 2018, selon des sources secondaires seulement — [glama, script de test](https://glama.ai/mcp/servers/@gvaibhav/TAM-MCP-Server/blob/25030aa6f226164ee92c345df5262b5904c7327f/tests/scripts/analyze-nasdaq-tier.mjs)

#### OpenBB Platform / Open Data Platform (ODP)
- **Historique de licence (fichier LICENSE du dépôt)** : MIT à la création (2021) ; **AGPLv3 à partir du 2024-05-14** (commit c61d10d6, « Update the license of the code in this repo to AGPL ») ; AGPL maintenue le 2025-02-10 ; **Apache 2.0 depuis la V5 du 2026-09-29** (commit bbf1ab20) — [LICENSE actuel](https://github.com/OpenBB-finance/OpenBB/blob/develop/LICENSE) ; [historique des commits du LICENSE](https://api.github.com/repos/openbq-org/OpenBB/commits?path=LICENSE)
- `openbb` 5.0.0 a été publié sur PyPI le 2026-09-29 (Apache-2.0). Fournisseurs installés par défaut : `openbb-bls`, `cboe`, `cftc`, `deribit`, `ecb`, `famafrench`, `federal-reserve`, `finra`, `fred`, `government-us`, **`imf`**, `jodi`, `nasdaq`, **`oecd`**, `sec`, **`tmx`** (Bourse de Toronto), `us-eia`, plus **`openbb-mcp-server`** — [PyPI openbb](https://pypi.org/project/openbb/)
- Le README décrit l'Open Data Platform par OpenBB comme une couche « connect once, consume everywhere » : Python, Workspace/Excel, **serveurs MCP pour agents IA** et API REST. Il avertit : « The data contained in the Open Data Platform is not necessarily accurate » — [README OpenBB](https://github.com/OpenBB-finance/OpenBB)
- L'API GitHub résout désormais le dépôt `OpenBB-finance/OpenBB` vers `openbq-org/OpenBB` (constaté le 15 nov. 2026, origine du changement non vérifiée) — [GitHub API](https://api.github.com/repos/OpenBB-finance/OpenBB)

#### pandas-datareader
- La **v0.11.0 (juin 2026)** rétablit la compatibilité avec pandas 3 et ajoute une API `pandas_datareader.macro` (FRED, Eurostat, OCDE : `read_macro`, `search_macro_datasets`). **Elle supprime les lecteurs AlphaVantage, Enigma, IEX, Morningstar, Naver, Nasdaq Trader, Quandl, Stooq, Tiingo et Yahoo Finance** et ajoute `get_data_econdb` — [whatsnew v0.11.0](https://github.com/pydata/pandas-datareader/blob/main/docs/source/whatsnew/v0.11.0.txt)
- Version 0.11.1 publiée le 2026-06-24 (BSD-3, Python ≥ 3.11). L'API publique est recentrée sur FRED, Fama/French, la Banque du Canada, la Banque mondiale, l'OCDE et Eurostat — [PyPI pandas-datareader](https://pypi.org/project/pandas-datareader/)

#### Trading Economics
- `api.tradingeconomics.com` avec `c=guest:guest` renvoie **HTTP 410** : « the guest account has been discontinued. Please subscribe to a plan » — [test live](https://api.tradingeconomics.com/historical/country/canada/indicator/gdp?c=guest:guest&f=json) ; [pricing](https://tradingeconomics.com/api/pricing.aspx)
- Aucun niveau gratuit officiel trouvé. Des sources tierces évoquent un essai à 100 requêtes et 100 000 points, avec des prix contradictoires — [apis.io plans](https://apis.io/plans/tradingeconomics/tradingeconomics-plans-pricing/). Client Python `tradingeconomics` 4.5.11 (2026-07-08) — [PyPI](https://pypi.org/project/tradingeconomics/)

#### Econdb
- `econdb.com/api/series/...` renvoie **401** « Authentication credentials were not provided » — [test live](https://www.econdb.com/api/series/CPICA/?format=json). La liste public-apis indique encore « No » pour l'authentification, ce qui est obsolète — [public-apis](https://github.com/public-apis/public-apis)
- Plans et prix : non confirmés, seuls des agrégateurs incohérents sont disponibles — [apispine](https://apispine.com/econdb)

#### Our World in Data (API et ETL)
- Chart API : ajouter `.csv` ou `.metadata.json` au slug du grapher. Licence CC BY 4.0. Une réponse **403 signale des données non redistribuables** — [OWID Chart API docs](https://owid-docs.readthedocs.io/projects/etl/api/chart-api/). Tests réussis — [CSV](https://ourworldindata.org/grapher/gdp-per-capita-worldbank.csv?v=1&csvType=filtered&useColumnShortNames=true&country=~CAN) ; [metadata](https://ourworldindata.org/grapher/gdp-per-capita-worldbank.metadata.json), avec le champ `citation` : « Eurostat, OECD, IMF, and World Bank (2026) »
- Une API d'indicateurs existe : `https://api.ourworldindata.org/v1/indicators/{id}.metadata.json` — [test live](https://api.ourworldindata.org/v1/indicators/2118.metadata.json). Le site distingue Charts API, Tables API (catalogue ETL) et recherche sémantique d'indicateurs — [OWID ETL API](https://owid-docs.readthedocs.io/projects/etl/api/)
- Les données produites par OWID sont sous CC BY. Les données de tiers gardent leur licence d'origine — [OWID FAQ](https://ourworldindata.org/faqs)
- `owid-catalog` 1.3.0 (2026-10-19, MIT) ; l'ancien dépôt `owid-catalog-py` est **archivé**, et `owid/etl` (MIT) est actif — [PyPI owid-catalog](https://pypi.org/project/owid-catalog/) ; [GitHub owid-catalog-py](https://github.com/owid/owid-catalog-py) ; [GitHub owid/etl](https://github.com/owid/etl)

#### Kaggle (fichiers en masse)
- `https://www.kaggle.com/api/v1/datasets/list?search=macroeconomic` a renvoyé du JSON **sans authentification** ; parmi les résultats, « bank-of-england/a-millennium-of-macroeconomic-data » — [test live](https://www.kaggle.com/api/v1/datasets/list?search=macroeconomic)

#### Hugging Face Datasets
- L'API de recherche du Hub (`/api/datasets?search=`) fonctionne sans clé. Les étiquettes de licence sont déclarées par les déposants : par exemple « GabrieleMagrini/FRED » est étiqueté apache-2.0 alors que la provenance est FRED — [test live](https://huggingface.co/api/datasets?search=fred&sort=downloads&limit=5)
- « CalcFi Open Data » (iizy/calcfi-open-data) est un miroir de 34 séries financières et macro (rendements du Trésor, CPI, chômage…) sous CC BY 4.0, mis à jour quotidiennement — [HF CalcFi](https://huggingface.co/datasets/iizy/calcfi-open-data). « THULab/macroecon » est sous cc-by-nc-nd-4.0 — [résumé de recherche](https://huggingface.co/datasets/THULab/macroecon/discussions)

#### Listes GitHub (public-apis, awesome-quant) : apports nets
- La liste **public-apis** (section Finance : 112 entrées ; Government : 137) ajoute peu côté international officiel. Entrées pertinentes : Econdb (obsolète, voir plus haut), FRED, U.S. Treasury Fiscal Data, BLS, Census, SEC EDGAR, Bank Negara Malaysia Open Data, Brazil Central Bank Open Data — [public-apis README](https://github.com/public-apis/public-apis)
- **awesome-quant** (section « Market Data & Data Sources ») : `pystlouisfed` (FRED, **ALFRED**, GeoFRED, FRASER), `fedfred`, `FRB`, `findatapy`, `pandaSDMX` (listé bien qu'inactif), Nasdaq Data Link, OpenBB. On y trouve aussi des services commerciaux avec niveau gratuit, comme FXMacroData (publications macro USD sur 90 jours, 100 requêtes/jour sans clé, d'après la liste) — [awesome-quant README](https://github.com/wilsonfreitas/awesome-quant)

### Inferences
- Pour un agent qui alimente une base redistribuée, mieux vaut **appeler les API officielles directement** et réserver DBnomics à l'exploration ou au repli. Deux raisons : la licence suit de toute façon le fournisseur d'origine, et plusieurs connecteurs DBnomics (FMI, BRI, Banque mondiale) semblent figés depuis les migrations de 2024-2025.
- Le passage d'OpenBB à Apache 2.0 rend ODP intégrable dans AlphaForge sans obligation de publier le code source. Son fournisseur `tmx` et son serveur MCP sont pertinents pour les titres canadiens. Le client Python `dbnomics` reste en revanche sous AGPL : il vaut mieux appeler l'API REST de DBnomics directement.
- Hugging Face et Kaggle ne conviennent pas comme sources primaires : la provenance et la licence sont déclaratives, et la distinction entre date d'observation et date de publication est rarement présente.

### Gaps
- Quotas exacts de DBnomics avec et sans clé : non publiés.
- Conditions du niveau gratuit Nasdaq Data Link en 2026 : non confirmées officiellement (la page de doc est rendue en JavaScript).
- Prix et quotas d'Econdb : non trouvés.
- Kaggle : authentification requise pour le téléchargement (vs liste) non vérifiée ; conditions d'usage de l'API non lues.
- Licences des jeux Hugging Face cités : à vérifier sur chaque fiche.

---

## Point-in-time : dates de publication et millésimes (vintages)

### Takeaway
Plusieurs sources exposent de vrais millésimes interrogeables par API : le **FMI** (dataflows `*_VINTAGE`, dont WEO avril 2026 et octobre 2025, plus des millésimes mensuels de CPI, ER, IL, MFS, BOP…), l'**OCDE** (Economic Outlook n° 114 à 119 et dataflow de révisions des statistiques conjoncturelles), la **BCE** (base temps réel `RTD`, paramètres `updatedAfter` et `includeHistory`) et la **Banque mondiale** (WDI Database Archives). Les autres fournissent au mieux une date de mise à jour (`lastupdated`, `updated`, `Last-Modified`).

### Cited Findings
- **FMI.** Parmi les dataflows millésimés : `WEO_2025_OCT_VINTAGE` et `WEO_2026_APR_VINTAGE` (agence IMF.RES), à côté du `WEO` courant (v9.0.0). Il existe aussi des millésimes mensuels (janvier à août 2026 selon les jeux) pour `CPI`, `PPI`, `ER`, `EER`, `IL`, `MFS_*`, `BOP`, `IIP`, `ITG`, `IMTS`, `QNEA`/`ANEA`, `QGFS`, `PI`, `LS`, `FA`, `SPE`, ainsi que pour les REO régionaux (`WHDREO_2025_OCT_VINTAGE`…) — [catalogue live FMI](https://api.imf.org/external/sdmx/3.0/structure/dataflow/*/*/+?detail=allstubs)
- **OCDE.** Les dataflows `DSD_EO_114@DF_EO_114` à `DSD_EO_118@DF_EO_118`, plus `DSD_EO@DF_EO` (« Economic Outlook 119 ») ; **`OECD.SDD.STES:DSD_STES_REVISIONS@DF_STES_REVISIONS` (« Short-term economic statistics revisions »)** ; le test `DF_TEST_MEI` (« TEST - Main Economic Indicators Publication ») — [catalogue live OCDE](https://sdmx.oecd.org/public/rest/dataflow/all/all/latest)
- **BCE.** Le dataflow `RTD` (base de données temps réel) est interrogeable, par exemple avec les clés `RTD.A.S0.N.F_CEC_CGG_D0.F` — [test live](https://data-api.ecb.europa.eu/service/data/RTD?lastNObservations=1&detail=serieskeysonly&format=csvdata). `updatedAfter` renvoie « the latest version of changed values … (i.e. updates and revisions) ». `includeHistory` est listé parmi les paramètres — [ECB API Data](https://data.ecb.europa.eu/help/api/data)
- **Banque mondiale.** La source 57 « WDI Database Archives » a été mise à jour pour la dernière fois le 2025-10-29. Chaque réponse de l'API Indicators porte un champ `lastupdated` — [sources live](https://api.worldbank.org/v2/sources?format=json&per_page=100) ; [test live](https://api.worldbank.org/v2/country/CA/indicator/NY.GDP.MKTP.CD?format=json&per_page=2)
- **Eurostat.** Les réponses JSON-stat portent un champ `updated`. Il existe un jeu « HICP - first published data » (`prc_hicp_fp`) qui conserve les premières publications — [test live](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr?geo=EA&coicop=CP00&lastTimePeriod=1) ; [DBnomics prc_hicp_fp](https://db.nomics.world/Eurostat/prc_hicp_fp?tab=table)
- **BRI.** La réponse CSV porte un en-tête `etag` ; aucun millésime trouvé — [test live](https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.CA?lastNObservations=1&format=csv)
- **BoJ.** La réponse JSON inclut `DATE` (horodatage de la réponse), mais aucun millésime n'est documenté — [test live](https://www.stat-search.boj.or.jp/api/v1/getDataCode?format=json&lang=en&db=FM01&code=STRDCLUCON&startDate=202601)
- **ALFRED** (millésimes de FRED) est accessible via `pystlouisfed`, selon awesome-quant — [awesome-quant](https://github.com/wilsonfreitas/awesome-quant)

### Inferences
- Pour l'exigence du brief qui distingue date d'observation et date de publication, on peut s'appuyer sur trois éléments. (1) Pour le FMI, le nom du dataflow `*_YYYY_MON_VINTAGE` donne le millésime de publication. (2) Pour la BCE, `updatedAfter` et `includeHistory` permettent de reconstituer l'historique des révisions. (3) Pour l'OCDE, `DF_STES_REVISIONS` semble être le successeur, sur la nouvelle plateforme, de l'ancienne « MEI Original Release Data and Revisions Database ». C'est une inférence d'après le nom : le contenu n'a pas été inspecté.
- Pour les sources sans millésime (BRI, BoE, BoJ, RBA), l'agent devrait horodater lui-même chaque collecte (`retrieved_at`) et conserver les en-têtes `Last-Modified` et `ETag` pour approcher la date de publication.

### Gaps
- Le dataflow WEO d'octobre 2026 n'apparaît pas comme millésime : le `WEO` courant correspond-il à octobre 2026 ? Non vérifié.
- Structure et contenu exacts de `DF_STES_REVISIONS` (dimensions de date de publication) : non inspectés.
- Comportement réel de `includeHistory` à la BCE (format des versions) : non testé.
- Historisation des révisions dans DBnomics : non vérifiée.
- Calendriers de publication (release calendars) par API : non trouvés pour ces organisations.

---

## Clients Python et serveurs MCP

### Takeaway
**sdmx1** (activement maintenu, 36 sources dont IMF_DATA/IMF_DATA3, OECD, ECB, ESTAT, BIS, ILO, WB_WDI, StatCan) est le client SDMX de référence en 2026. **pandaSDMX est abandonné** (dernière version en 2023, Python < 3.12). **imfp** cible désormais l'API SDMX 3.0 du FMI. Côté MCP, le seul serveur publié par un éditeur établi est celui d'OpenBB (Apache 2.0). Les autres (FMI, OCDE, Comtrade, FAOSTAT, Banque mondiale) sont communautaires et non audités.

### Cited Findings
- **sdmx1** 2.28.0 (2026-10-18), Apache-2.0, Python ≥ 3.11, dépôt `khaeru/sdmx` actif (dernier push 2026-10-18) — [PyPI sdmx1](https://pypi.org/project/sdmx1/) ; [GitHub](https://github.com/khaeru/sdmx). Il compte 36 sources : ABS, BBK, **BIS (pointé sur `stats.bis.org/api/v1`)**, ECB, ESTAT/ESTAT3, ILO, IMF (sdmxcentral), **IMF_DATA (`api.imf.org/external/sdmx/2.1`)**, **IMF_DATA3 (`.../3.0`)**, OECD, OECD3, OECD_JSON (`stats.oecd.org`, désormais une redirection), **StatCan**, UNSD (`data.un.org/WS/rest`, désormais redirigé), WB (WITS), WB_WDI… — [sources.json](https://github.com/khaeru/sdmx/blob/main/sdmx/sources.json)
- **pandaSDMX** 1.10.0 (2023-02-25), Python < 3.12, dernier push GitHub le 2023-12-28 — [PyPI pandasdmx](https://pypi.org/project/pandasdmx/) ; [GitHub dr-leo/pandaSDMX](https://github.com/dr-leo/pandaSDMX)
- **wbgapi** 1.0.14 (2026-02-27), MIT — [PyPI wbgapi](https://pypi.org/project/wbgapi/)
- **imfp** 2.1.1 (2026-10-22), Apache-2.0 : « downloading economic data from the International Monetary Fund SDMX 3.0 API, following econdataverse conventions ». Il reprend la logique du paquet R `imfapi` (`imf_get_dataflows`, `imf_get_datastructure`, `imf_get_codelists`, `imf_get`) — [PyPI imfp](https://pypi.org/project/imfp/)
- **dbnomics** 1.2.7 (2025-06-18), AGPL — [PyPI](https://pypi.org/project/dbnomics/). **sdmxthon** 2.6.11 (2026-06-03), Apache 2.0 — [PyPI](https://pypi.org/project/sdmxthon/). **comtradeapicall** (officiel Comtrade) — [PyPI](https://pypi.org/project/comtradeapicall/1.1.0/). **owid-catalog** 1.3.0 — [PyPI](https://pypi.org/project/owid-catalog/)
- Clients non officiels pour la BoJ : `bojstat` (Python, couvre les API Code, Layer et Metadata) et `bojapi` (R, sans clé) — [context7 bojstat](https://context7.com/youseiushida/bojstat) ; [bojapi README](https://rdrr.io/cran/bojapi/f/README.md)
- **Serveurs MCP.**
  - `openbb-mcp-server` 2.0.1 (« Model-Context-Protocol bridge for the Open Data Platform by OpenBB », Apache-2.0) — [PyPI](https://pypi.org/project/openbb-mcp-server/)
  - `cyanheads/imf-mcp-server` (FMI SDMX 3.0 : WEO, BOP, CPI, taux de change) — [ecosyste.ms](https://awesome.ecosyste.ms/projects/github.com%2Fcyanheads%2Fimf-mcp-server)
  - `c-cf/imf-data-mcp` — [mcpservers.org](https://mcpservers.org/servers/c-cf/imf-data-mcp)
  - `cyanheads/oecd-mcp-server` — [claudemarketplaces](https://claudemarketplaces.com/mcp/cyanheads/oecd-mcp-server)
  - `isakskogstad/OECD-MCP` — [glama](https://glama.ai/mcp/servers/isakskogstad/OECD-MCP)
  - `cyanheads/un-comtrade-mcp-server` — [crossaitools](https://crossaitools.com/mcp/cyanheads/un-comtrade-mcp-server)
  - `berba-q/faostat-mcp` — [glama](https://glama.ai/mcp/servers/berba-q/faostat-mcp)
  - Banque mondiale : `world-bank-data-mcp` — [glama](https://glama.ai/mcp/servers/@llnOrmll/world-bank-data-mcp/blob/78036a29f65c3230752e81448d9c5471e0311e44/README.md) ; `mcp_wbgapi360` — [lobehub](https://lobehub.com/ko/mcp/maykolmedrano-mcp_wbgapi360)
  - Une passerelle tierce « @pipeworx/dbnomics » est signalée (50 appels/jour en anonyme), mais aucun dépôt MCP officiel DBnomics n'a été trouvé : `github.com/dbnomics/dbnomics-mcp` renvoie 404 — [GitHub API](https://api.github.com/repos/dbnomics/dbnomics-mcp)

### Inferences
- Pour l'agent A5 (Strands sur Bedrock/AgentCore), deux voies semblent les plus sûres : des outils maison minces au-dessus de `sdmx1` ou de `requests` (FMI, OCDE, BCE, BRI, Eurostat, ILO), complétés par `wbgapi`, ou ODP avec son serveur MCP. Les serveurs MCP communautaires devraient être audités (code, dépendances, maintenance) avant tout usage.
- Points de vigilance avec sdmx1 : sa source `BIS` pointe sur l'API v1 alors que la v2 existe, et `UNSD` et `OECD_JSON` pointent vers des hôtes qui redirigent. Mieux vaut tester chaque source avant de s'y fier.

### Gaps
- Activité et maintenance réelles des serveurs MCP communautaires : non vérifiées (licences, derniers commits).
- Prise en charge par sdmx1 des millésimes FMI (`*_VINTAGE`) et des requêtes `c[TIME_PERIOD]` en SDMX 3.0 : non testée.

---

## Pièges 2025-2026 : migrations, endpoints dépréciés, fermetures

### Takeaway
Les ruptures majeures de 2025-2026 sont les suivantes : mise hors service de l'ancienne API JSON du FMI et retrait d'IFS ; quotas et restrictions de paramètres à l'OCDE ; HICP Eurostat passé en COICOP 2018 avec base 2025=100 ; nouveaux portails de la BoJ (février 2026) et de FAOSTAT (avril 2026) ; fin du compte guest de Trading Economics ; authentification désormais requise chez Econdb ; ménage dans pandas-datareader (Yahoo, Quandl… supprimés) ; changement de licence d'OpenBB (AGPL puis Apache 2.0) ; connecteurs DBnomics figés pour le FMI, la BRI et la Banque mondiale.

### Cited Findings
- **FMI.** `dataservices.imf.org` ne répondait plus lors de notre test, et sdmxws.imf.org est déclaré « decommissioned ». IFS est retiré et éclaté en dataflows thématiques — [URL testée](https://dataservices.imf.org/REST/SDMX_JSON.svc/Dataflow) ; [page sdmxws](https://extauth.imf.org/maintenance/sdmxws-decommissioned.htm) ; [readimf](https://cran.r-project.org/web/packages/readimf/readme/README.html)
- **FMI, conditions.** Le téléchargement en masse par moyen automatisé est interdit sans permission explicite — [IMF Copyright and Usage](https://www.imf.org/en/about/copyright-and-terms)
- **OCDE.** Limite de 60 téléchargements/heure, chiffre contredit par le miroir (20/min et 20/h). Restrictions de paramètres depuis mars 2026 sur de très gros jeux. `stats.oecd.org` redirige vers `sdmx.oecd.org` — [OECD rate limiting](https://www.oecd.org/en/data/insights/data-explainers/2024/11/Api-best-practices-and-recommendations.html) ; [Restricted API parameters](https://www.oecd.org/en/data/insights/data-explainers/2026/03/Restricted-API-parameter.html) ; [redirection testée](https://stats.oecd.org/SDMX-JSON/data/QNA/CAN.B1_GE.GYSA.Q/all?startTime=2024)
- **Eurostat.** HICP en COICOP 2018 et base 2025=100 à partir des données de janvier 2026. L'ancien `prc_hicp_manr` porte `updated` 2026-02-06 — [Statistics Poland](https://stat.gov.pl/en/topics/prices-trade/price-indices/harmonized-indices-of-consumer-prices-hicp,15,1.html) ; [test live](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr?geo=EA&coicop=CP00&lastTimePeriod=1)
- **Eurostat, licence.** Les données d'autres sources qu'Eurostat (États-Unis, Japon, Chine…) ne sont pas réutilisables commercialement — [Eurostat copyright](https://ec.europa.eu/eurostat/help/copyright-notice)
- **UNdata.** L'API SDMX a été déplacée sous `/legacy/` (redirection 302) — [test live](https://data.un.org/legacy/ws/rest/dataflow/)
- **FAOSTAT.** Nouveau portail développeur avec connexion (13 avril 2026). L'ancien hôte fenixservices a renvoyé 521 — [annonce FAO](https://www.fao.org/statistics/highlights-archive/highlights-detail/faostat-launches-a-new-api-developer-portal-to-make-data-access-easier/en) ; [URL testée](https://fenixservices.fao.org/faostat/api/v1/en/definitions/domain)
- **Bank of Japan.** Nouvelle API depuis le 18 février 2026, avec une obligation de notification et une mention de crédit — [BoJ notice](https://www.boj.or.jp/en/statistics/outline/notice_2026/not260218a.htm) ; [API notice PDF](https://www.stat-search.boj.or.jp/info/api_notice_en.pdf)
- **Trading Economics.** Compte guest supprimé (HTTP 410) — [test live](https://api.tradingeconomics.com/historical/country/canada/indicator/gdp?c=guest:guest&f=json)
- **Econdb.** Authentification désormais requise (401) — [test live](https://www.econdb.com/api/series/CPICA/?format=json)
- **Nasdaq Data Link.** Clé requise même pour les datatables ; client Python inchangé depuis 2022 — [test live](https://data.nasdaq.com/api/v3/datatables/NDAQ/RTAT10.json?qopts.per_page=1) ; [PyPI](https://pypi.org/project/nasdaq-data-link/)
- **pandas-datareader 0.11** : lecteurs Yahoo, Quandl, Stooq, Tiingo, IEX, AlphaVantage… supprimés — [whatsnew v0.11.0](https://github.com/pydata/pandas-datareader/blob/main/docs/source/whatsnew/v0.11.0.txt)
- **OpenBB.** Licence AGPLv3 entre le 2024-05-14 et la V5 du 2026-09-29, puis Apache 2.0. Les versions 4.x restent sous AGPL — [LICENSE](https://github.com/OpenBB-finance/OpenBB/blob/develop/LICENSE) ; [historique](https://api.github.com/repos/openbq-org/OpenBB/commits?path=LICENSE)
- **DBnomics.** Connecteurs `IMF` indexé le 2025-09-04, `BIS` le 2025-07-10, `WB` le 2024-09-19 ; arrivée annoncée de quotas pour les requêtes sans clé — [providers live](https://api.db.nomics.world/v22/providers?limit=200) ; [forum](https://dbnomics.discourse.group/t/dbnomics-site-update-new-features-and-improvements/984)
- **Protection anti-robots.** RBA (Akamai 403), OPEP (Cloudflare), pages de documentation de l'OCDE (Cloudflare), `sdmx.ilo.org` (403) : constaté le 15 nov. 2026 lors de nos tests — [RBA testé](https://www.rba.gov.au/statistics/tables/) ; [OPEP testé](https://www.opec.org/basket/basketDayArchives.xml) ; [ILO testé](https://sdmx.ilo.org/rest/dataflow/ILO?detail=allstubs)
- **pandaSDMX** est abandonné (incompatible avec Python ≥ 3.12) — [PyPI](https://pypi.org/project/pandasdmx/)

### Inferences
- Tout code ou toute bibliothèque antérieure à 2025 qui appelle `dataservices.imf.org`, IFS, `stats.oecd.org`, `pandasdmx`, `get_data_yahoo` ou `get_data_quandl` de pandas-datareader, ou le compte guest de Trading Economics, est cassé ou le sera.
- L'agent A5 devrait (1) respecter les quotas (backoff sur 429/403, cache local, `updatedAfter` à la BCE) ; (2) consigner dans le YAML l'URL exacte de la requête, l'horodatage de collecte, la licence et l'URL des conditions ; (3) éviter le scraping des sites protégés (RBA, OPEP), qui pose aussi un problème de conformité aux conditions.

### Gaps
- Date officielle exacte de la mise hors service de `dataservices.imf.org` : seule une source tierce indique « 2025 ».
- Liste officielle des paramètres bloqués par l'OCDE en mars 2026 : non lue intégralement.
- Changelogs de l'API Eurostat (codes `prc_hicp_*` remplacés) : non trouvés.
- Changement de propriétaire ou de nom de l'organisation GitHub d'OpenBB (`openbq-org`) : non expliqué.
