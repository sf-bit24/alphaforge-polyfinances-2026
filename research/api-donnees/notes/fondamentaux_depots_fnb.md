# Sources gratuites ou à palier gratuit : fondamentaux, dépôts réglementaires et données FNB (état au 14 novembre 2026)

> Périmètre : AlphaForge AI (datathon PolyFinances 2026, BN + AWS). L'agent de collecte A5 alimente la base de connaissances générale (Open Knowledge Format), y compris la transparence (look-through) des avoirs des FNB.
> Méthode : pages officielles lues via WebFetch/WebSearch, plus **appels directs (curl) faits le 2026-11-14** sur les points d'accès publics. Ces tests sont marqués « test direct 2026-11-14 » et l'URL testée sert de source.
> Convention point-in-time : **date d'observation** = fin de période fiscale (`end`, `period_end`, `fiscalDateEnding`, `reportDate`). **Date de publication** = date de dépôt ou d'acceptation (`filed`, `filingDate`, `acceptanceDateTime`, `reportedDate`, `Publish Date`).

## 1. Dépôts américains : SEC EDGAR (API data.sec.gov, recherche plein texte, jeux de données en vrac, N-PORT, N-CEN, 13F, sec-api.io, EdgarTools)

### Takeaway
EDGAR est la colonne vertébrale gratuite et redistribuable du projet. Les API JSON ne demandent ni authentification ni clé. Elles sont mises à jour en temps réel (moins d'une seconde pour les dépôts, moins d'une minute pour le XBRL). Chaque fait porte à la fois `end` (observation) et `filed` + `accn` (publication), ce qui rend le point-in-time natif. L'accès est limité à 10 requêtes/s et exige un en-tête User-Agent déclaré : sans lui, la réponse est 403. Six des dix titres TSX du périmètre (RY, TD, MFC, ENB, CNQ, CNR, FTS, SHOP couvrent huit titres) y sont présents via les formulaires 40-F/6-K/10-K, mais ATD et CSU en sont absents.

### Cited Findings

**Fiche : API data.sec.gov (submissions, companyconcept, companyfacts, frames)**
- URL de base : `https://data.sec.gov/`. Points d'accès : `/submissions/CIK##########.json` (historique des dépôts et métadonnées : noms, bourses, tickers), `/api/xbrl/companyconcept/CIK##########/us-gaap/<Concept>.json`, `/api/xbrl/companyfacts/CIK##########.json` et `/api/xbrl/frames/us-gaap/<Concept>/USD/CY2019Q1I.json` — [SEC – EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- Authentification : « These APIs do not require any authentication or API keys to access » — [SEC – EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- Latence : le JSON est mis à jour « throughout the day, in real time, as submissions are disseminated ». Le délai type est de moins d'une seconde pour submissions et de moins d'une minute pour les API XBRL, plus long aux heures de pointe — [SEC – EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- Vrac : `companyfacts.zip` (toutes les données Frames et Company Facts) et `submissions.zip`, recompilés chaque nuit vers 3 h ET. La SEC les présente comme le moyen le plus efficace de récupérer de gros volumes — [SEC – EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- CORS non pris en charge (« data.sec.gov does not support Cross Origin Resource Scripting »). Un appel direct depuis un navigateur est donc impossible et il faut passer par un backend ou l'agent — [SEC – EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- Frames : « aggregates one fact for each reporting entity that is **last filed** that most closely fits the calendrical period requested ». Formats de période : `CY####` (annuel, 365 j ± 30), `CY####Q#` (trimestriel, 91 j ± 30), `CY####Q#I` (instantané). Page mise à jour le 8 avril 2025 — [SEC – EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- Champs d'un fait companyfacts : `start`, `end`, `val`, `accn`, `fy`, `fp`, `form`, `filed`, `frame`. Exemple Shopify : `end 2026-09-30, form 10-Q, filed 2026-11-03, frame CY2026Q3` — [test direct 2026-11-14](https://data.sec.gov/api/xbrl/companyfacts/CIK0001594805.json)
- Champs submissions (`filings.recent`) : `accessionNumber`, `filingDate`, `reportDate`, `acceptanceDateTime`, `act`, `form`, `fileNumber`, `items`, `core_type`, `isXBRL`, `isInlineXBRL`, `isXBRLNumeric`, `primaryDocument`. Exemple RY : 6-K, `reportDate 2026-07-31`, `filingDate 2026-08-27`, `acceptanceDateTime 2026-08-27T10:17:11Z`. L'en-tête de submissions contient aussi `sic`, `fiscalYearEnd` et `lei` (null pour RY) — [test direct 2026-11-14](https://data.sec.gov/submissions/CIK0001000275.json)
- Politique d'accès équitable : « no more than 10 requests per second », quel que soit le nombre de machines. La SEC se réserve le droit de bloquer les IP abusives et n'autorise pas les robots « unclassified ». Page mise à jour le 10 mars 2025 — [SEC – Developer Resources](https://www.sec.gov/about/developer-resources)
- User-Agent : déclarer par exemple `User-Agent: Sample Company Name AdminContact@<sample company domain>.com`, avec `Accept-Encoding: gzip, deflate`. Une erreur « Undeclared Automated Tool » signale un UA manquant. La FAQ n'indique pas de durée de blocage précise — [SEC – Webmaster FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions)
- Une requête sans User-Agent reçoit **HTTP 403**. Avec un UA déclaré, la réponse est 200 — [test direct 2026-11-14](https://data.sec.gov/submissions/CIK0000320193.json)
- Licence : les données de la SEC sont publiques. La SEC ne fournit pas de soutien technique aux téléchargements scriptés mais les autorise — [SEC – Webmaster FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions)
- Correspondance ticker → CIK : le fichier `https://www.sec.gov/files/company_tickers.json` compte 10 404 entrées le 2026-11-14. On y trouve RY (CIK 1000275), TD (947263), SHOP (1594805), BMO (927971), ENB (895728), CNQ (1017413), CNI (16868 ; ticker NYSE CNI, et non CNR), MFC (1086888) et FTS (1666175). **ATD et CSU sont absents** — [test direct 2026-11-14](https://www.sec.gov/files/company_tickers.json)
- Taxonomies selon l'émetteur canadien (test companyfacts) :
  - RY : `ifrs-full`, 298 concepts, formulaires 40-F et 6-K. Les faits issus de 6-K vont de 2019 à 2026, ce qui donne des trimestriels en XBRL.
  - TD : `ifrs-full`, 239 concepts, dernier dépôt le 2026-11-13.
  - CNQ : `ifrs-full`, 40-F seulement, dernier dépôt le 2026-03-26.
  - MFC : `ifrs-full`, 40-F seulement, dernier dépôt le 2026-02-11, donc pas de trimestriel XBRL.
  - CNI : `us-gaap` via 40-F/6-K.
  - FTS : `us-gaap` via 40-F.
  - ENB : `us-gaap`, 10-K/10-Q.
  - SHOP : `us-gaap`, 10-K/10-Q (ancien 40-F).
  - Sources : [test RY](https://data.sec.gov/api/xbrl/companyfacts/CIK0001000275.json), [test TD](https://data.sec.gov/api/xbrl/companyfacts/CIK0000947263.json), [test MFC](https://data.sec.gov/api/xbrl/companyfacts/CIK0001086888.json), [test CNQ](https://data.sec.gov/api/xbrl/companyfacts/CIK0001017413.json), [test ENB](https://data.sec.gov/api/xbrl/companyfacts/CIK0000895728.json), [test CNI](https://data.sec.gov/api/xbrl/companyfacts/CIK0000016868.json), [test FTS](https://data.sec.gov/api/xbrl/companyfacts/CIK0001666175.json)
- **XOM change de CIK** : le 1er juillet 2026, Exxon Mobil Corporation (New Jersey) a achevé sa redomiciliation. ExxonMobil Holdings Corporation (Texas) devient l'émetteur coté successeur, avec échange 1 pour 1 et ticker XOM inchangé — [8-K ExxonMobil](https://investor.exxonmobil.com/sec-filings/all-sec-filings/content/0001193125-26-291990/d71068d8k12b.htm). Dans `company_tickers.json`, XOM pointe désormais vers le CIK **2115436** (« ExxonMobil Holdings Corp »), qui ne compte que 98 concepts us-gaap. L'historique est resté sous l'ancien CIK **34088**, dernier dépôt le 2026-05-04 — [test direct 2026-11-14](https://data.sec.gov/api/xbrl/companyfacts/CIK0002115436.json), [test CIK 34088](https://data.sec.gov/api/xbrl/companyfacts/CIK0000034088.json)

**Fiche : EDGAR Full-Text Search (FTS)**
- Recherche dans le texte intégral de tous les dépôts électroniques depuis 2001, pièces jointes comprises. Opérateurs disponibles : OR, `-`, NEAR() — [SEC – FTS FAQ](https://www.sec.gov/edgar/search/efts-faq.html)
- Backend JSON utilisé par l'interface : `https://efts.sec.gov/LATEST/search-index?q=...&forms=40-F`. Il renvoie `ciks`, `period_ending`, `file_date`, `form`, `adsh`, `sics`, `display_names` (avec tickers) et des agrégats. Il répond avec un UA déclaré. Ce point d'accès n'est **pas documenté comme API officielle** — [test direct 2026-11-14](https://efts.sec.gov/LATEST/search-index?q=%22Royal%20Bank%22&forms=40-F)

**Fiche : Financial Statement Data Sets (FSDS) et Financial Statement and Notes (FSN)**
- FSDS : données numériques des états financiers de base extraites du XBRL, de janvier 2009 à septembre 2026. Publication **trimestrielle** (dernier fichier `2026q3.zip`, 62,13 Mo). En décembre 2024, la SEC a retraité les jeux pour ne garder que les états primaires et a ajouté un champ « segments » à NUM. Les données sont « as originally filed » et accompagnées d'un avertissement d'exactitude — [SEC – FSDS](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets)
- FSN : texte et chiffres détaillés des états **et des notes**, « without change from the as filed », de janvier 2009 à **octobre 2026** — [SEC – FSN](https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets)

**Fiche : jeux de données Form N-PORT (avoirs des fonds et FNB américains)**
- Données structurées des rapports mensuels de portefeuille des sociétés d'investissement enregistrées et de certains FNB constitués en UIT. Les fonds monétaires (règle 2a-7) sont exclus. Publication **trimestrielle**, d'octobre 2019 à septembre 2026. Derniers fichiers : `2026q3_nport.zip` (440,95 Mo) et `2026q2_nport.zip` (420,28 Mo). Le jeu ne contient que l'information publique. Documentation dans `nport_readme.pdf` — [SEC – N-PORT Data Sets](https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets)
- Les amendements de 2024 au N-PORT (dépôt mensuel sous 30 jours, publication mensuelle) ont été reportés. Nouvelle conformité : **17 novembre 2027** (fonds de 1 G$ et plus) et **18 mai 2028** (autres) — [Thompson Hine](https://www.thompsonhine.com/insights/sec-extends-compliance-date-for-amendments-to-form-n-port)
- Le 18 février 2026, la SEC a **proposé** d'accorder 15 jours de plus pour le dépôt mensuel, de **ramener la publication de mensuelle à trimestrielle** et d'alléger le contenu. Les commentaires étaient attendus au 24 avril 2026. Aucune adoption finale n'a été trouvée — [Simpson Thacher](https://www.stblaw.com/about-us/publications/view/2026/05/11/sec-proposes-amendments-to-form-n-port-and-extends-compliance-dates-for-names-rule-reporting-(registered-funds-regulatory-update)), [MFDF](https://www.mfdf.org/home/news---resources/news/2026/02/25/sec-proposes-n-port-amendments)

**Fiche : jeux de données Form N-CEN**
- Rapport annuel de toutes les sociétés d'investissement enregistrées, extrait du XML, « as-filed ». Couverture de septembre 2018 à septembre 2026, mise à jour trimestrielle — [SEC – N-CEN Data Sets](https://www.sec.gov/data-research/sec-markets-data/form-n-cen-data-sets)

**Fiche : jeux de données Form 13F**
- Données « as-filed » extraites du XML des 13F (investisseurs institutionnels). Depuis mars 2024, chaque jeu couvre les trois mois précédents et paraît après la fin de février, mai, août et novembre. Dernier fichier : `01jun2026-31aug2026_form13f.zip` (96,05 Mo). Couverture de juillet 2013 à août 2026 — [SEC – 13F Data Sets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets)

**Fiche : sec-api.io (commercial)**
- Gratuit : **100 appels au total**, sans carte, toutes API et serveur MCP compris, « same data as paid plans ». Premier palier payant : **Personal & Startups à 49 $/mois** (588 $/an). Business : 199 $/mois. L'API N-PORT/FNB et la recherche plein texte ne sont **pas** incluses dans Personal (Business et plus seulement). 13F et XBRL-to-JSON sont inclus dès Personal. Licences : Personal pour usage personnel ou interne de startup, Business pour usage interne, redistribution réservée à Enterprise — [sec-api.io pricing](https://sec-api.io/pricing)

**Fiche : EdgarTools (bibliothèque Python)**
- Licence MIT, environ 2,9 k étoiles. Exige Python 3.11 ou plus. Identité déclarée via `set_identity("nom@exemple.com")`. Fonctions utiles : états financiers standardisés (trimestriels et TTM), 13F (`.holdings`), N-PORT (`Fund("VOO").get_portfolio()`), Form 4. Serveur MCP local via l'extra `edgartools[ai]` (`edgartools-mcp`) et serveur hébergé `app.edgar.tools/mcp` — [GitHub dgunning/edgartools](https://github.com/dgunning/edgartools)
- Dernière version **v6.1.0, publiée le 2026-11-12** (PyPI 6.1.0, `requires_python >=3.11`) — [GitHub API releases](https://api.github.com/repos/dgunning/edgartools/releases/latest), [PyPI edgartools](https://pypi.org/pypi/edgartools/json)

### Inferences
- Pour le look-ahead, la bonne clé de jointure est le couple (`end`, `filed`/`acceptanceDateTime`) de companyfacts et submissions. **Frames ne convient pas au backtest** : il renvoie le fait « last filed », donc potentiellement retraité après coup.
- `fy`/`fp` dans companyfacts désignent l'exercice **du document déposé** et non celui du fait. Un 10-K FY2026 contient les comparatifs FY2025 avec `fy=2026`. Il faut dater les faits avec `start`/`end`.
- Pour les banques canadiennes (RY, TD), les 6-K portent du XBRL IFRS trimestriel. Pour MFC et CNQ, seul l'annuel (40-F) existe en XBRL : les trimestres devront venir d'une autre source (SEDAR+ ou relations investisseurs, voir §2).
- Les taxonomies sont mixtes (`ifrs-full` et `us-gaap`). A5 aura donc besoin d'une table de correspondance de concepts, par exemple `Revenue` (IFRS) vers `Revenues` ou `RevenueFromContractWithCustomer...` (US GAAP).
- N-PORT reste **trimestriel en publication publique** au moins jusqu'en 2027. Avec l'avis de février 2026, il pourrait le rester définitivement. Le décalage de publication des avoirs de FNB américains via la SEC se compte donc en mois.

### Gaps
- Le délai exact de publication publique des N-PORT sous le régime actuel (mois 3 du trimestre, rendu public environ 60 jours après la fin du trimestre) n'a pas été confirmé sur une page SEC lue dans cette session.
- La durée de blocage IP en cas de dépassement des 10 req/s n'est documentée sur aucune page officielle lue.
- La signification du nouveau champ `core_type` dans submissions n'a pas été documentée.

## 2. Dépôts canadiens : SEDAR+, SEDI, annuaire TSX/TMX, CIRO, XBRL canadien

### Takeaway
Aucune API publique ni aucun accès en vrac gratuit n'existe pour SEDAR+. Ses conditions d'utilisation (ASC, 28 avril 2023) **interdisent explicitement** le scraping, les recherches automatisées, la constitution de bases de données et la commercialisation. Le XBRL canadien reste volontaire et absent de SEDAR+. Pour ATD et CSU, qui ne déposent pas à la SEC, il faut des téléchargements manuels ou les sites de relations investisseurs, ou une licence de l'ASC ou des ACVM.

### Cited Findings

**Fiche : SEDAR+ (sedarplus.ca)**
- Conditions d'utilisation, dernière mise à jour le **28 avril 2023**. Section 2(f) : obligation de ne pas « engage in any 'scraping' or the use of any automated means to use or reproduce multiple pieces » de l'information publique. Section 5 : interdiction d'utiliser « any robot, spider or other automatic device » et de « perform automated searches against the SEDAR+ Public Website ». Section 2(e) : interdiction de « construct a database of any kind ». Section 2(b) : interdiction de « commercialize the Public Information ». Section 2(c) : interdiction de toute « frequent, public, commercial or mass distribution » — [Terms of Use SEDAR+ (ACVM/ASC)](https://systems.securities-administrators.ca/?p=4978)
- Section 1 : l'ASC est « the representative securities regulatory authority authorized to grant licenses and enter into agreements ». La page ne mentionne aucune API ni aucun abonnement de données — [Terms of Use SEDAR+](https://systems.securities-administrators.ca/?p=4978)
- Lecture d'un tiers : Hudson Labs a examiné SEDAR et SEDAR+ et conclu que le scraping n'est pas conforme aux conditions, donc ne le pratique pas — [Hudson Labs – web scraping policy](https://hudson-labs.com/web-scraping-policy)
- Côté déposants, les frais système SEDAR+ et NRD augmentent de 60 % le 28 novembre 2025, puis de 3 % par an sur 4 ans à partir de 2026. Ces frais ne visent pas les consommateurs de données — [MLT Aikins](https://www.mltaikins.com/insights/canadian-securities-administrators-significantly-increase-sedar-and-nrd-system-fees/)

**Fiche : ACVM – Data Distribution Services (DDS)**
- D'après l'extrait de recherche, les ACVM proposent des flux structurés en vrac des données SEDI (profils d'initiés, transactions, avoirs) et NRD, livrés quotidiennement en fichiers sur un point de terminaison sécurisé. Page bloquée par Cloudflare lors de la lecture directe, donc **tarifs et conditions non vérifiés** — [ACVM – Data Distribution Services](https://www.securities-administrators.ca/?p=33446)

**Fiche : SEDI (déclarations d'initiés)**
- Le site public permet de consulter les déclarations sans inscription. Les transactions déposées sont visibles « at least within 5 minutes ». Les pages d'aide décrivent des consultations par rapport (téléchargement PDF) et un sommaire hebdomadaire, sans export en vrac gratuit (extraits de recherche) — [SEDI – aide publique](https://www.sedi.ca/sedi/new_help/english/public/Access_Public_Information/access_insider_transaction_detail_reports.htm), [SEDI FAQ (PDF)](https://www.sedi.ca/sedi/new_help/english/public/PDF_en/FAQs_Factsheet_-SEDI_(FINAL).pdf)

**Fiche : XBRL au Canada**
- Le programme XBRL des ACVM était **volontaire** : « public companies will not be required to file in XBRL; this will be an optional filing in addition to the mandatory filing in PDF » — [Avis ACVM 51-323 (BCSC)](https://www.bcsc.bc.ca/-/media/PWS/Resources/Securities_Law/Policies/Policy5/51323_CSA_Notice.pdf)
- La page XBRL des ACVM indique que les dépôts XBRL faits dans l'ancien SEDAR se trouvent via la recherche « legacy SEDAR » et que « XBRL filings are not yet available in SEDAR+ ». Page d'environ deux ans, non relue directement à cause de Cloudflare — [ACVM – XBRL Filing](https://www.securities-administrators.ca/resources/xbrl-filing/)
- Aucun texte de 2025 ou 2026 rendant le XBRL obligatoire pour les émetteurs n'a été trouvé. XBRL US a toutefois plaidé pour des données structurées dans la modernisation de l'information sur les fonds d'investissement (NI 81-101) — [Lettre XBRL US aux ACVM (déc. 2024)](https://xbrl.us/wp-content/uploads/2024/12/XBRL-US-Ltr-to-CSA-National-Instrument-81-101-Mutual-Fund-Prospectus.pdf), [XBRL International](https://www.xbrl.org/news/canada-to-embrace-open-data-standards-for-investment-fund-reporting/)

**Fiche : annuaire des sociétés inscrites TSX/TSXV (TMX)**
- La page « Listed Company Directory » propose un lien « download a full list of TSX/TSXV issuers ». La recherche se fait sur money.tmx.com — [TSX – Listed Company Directory](https://tsx.com/en/listings/listing-with-us/listed-company-directory)
- Les rapports mensuels MiG renvoient à des listes mensuelles d'émetteurs. Le MiG de juin 2026 recense 3 761 émetteurs TSX et TSXV — [TSX – ressource MiG](https://www.tsx.com/en/resource/3560/)
- Données de calendrier corporatif TMX vendues comme module partenaire chez Massive à **99 $/mois** — [Massive pricing](https://massive.com/pricing)

### Inferences
- Pour ATD (Couche-Tard) et CSU (Constellation Software), qui n'ont pas de CIK SEC, la seule voie gratuite et conforme semble être le **téléchargement manuel** des rapports sur les sites de relations investisseurs, ou depuis SEDAR+ en consultation humaine. Il faut documenter la date de publication depuis le communiqué ou la date de dépôt SEDAR+. Automatiser SEDAR+ violerait ses conditions.
- Pour les autres titres TSX intercotés, la SEC (40-F/6-K/10-K) offre un substitut machine-lisible et redistribuable aux dépôts SEDAR+.

### Gaps
- **CIRO** n'a pas été examiné dans cette session : on ne sait pas s'il publie des données exploitables (statistiques de négociation, ventes à découvert) ni sous quelles conditions.
- Existence et tarif d'un flux de données SEDAR+ (documents et métadonnées) via les ACVM ou l'ASC : non confirmés, page DDS inaccessible.
- Le format exact (Excel ou CSV), la fréquence et la licence du fichier « full list of TSX/TSXV issuers » n'ont pas été vérifiés.

## 3. API de fondamentaux (FMP, Finnhub, Alpha Vantage, SimFin, EODHD, Tiingo, Massive, Financial Datasets, Macrotrends, Morningstar, Intrinio) et couverture TSX au palier gratuit

### Takeaway
Aucun palier gratuit vérifié n'offre des fondamentaux complets pour les sociétés TSX non intercotées. Chez FMP, le Canada commence au palier Premium (69 $/mois). Chez EODHD, il n'y a aucun fondamental gratuit. SimFin gratuit couvre 5 000 titres américains. Alpha Vantage est le meilleur complément gratuit : états financiers, EARNINGS avec `reportedDate`, DIVIDENDS avec `declaration_date` et ETF_PROFILE avec avoirs, à 25 requêtes par jour. Son endpoint **OVERVIEW est devenu premium**. Presque tous les fournisseurs interdisent l'affichage ou la redistribution sans licence.

### Cited Findings

**Fiche : Financial Modeling Prep (FMP)**
- **Basic** (0 $) :
  - quotas : 250 appels/jour, 5 ans d'historique, bande passante de 500 Mo sur 30 jours glissants ;
  - états financiers (income, balance, cash flow) : « Maximum 5 Responses per API Call, Symbol Limited to AAPL, TSLA, AMZN and 84 more » ;
  - états « As Reported » limités aux rapports annuels ;
  - TTM et « Latest Financial Statements » non inclus ;
  - calendriers de résultats et de dividendes : un mois d'historique, symboles limités ;
  - **ETF & Fund Holdings, ETF Sector Weighting, ETF Holder Bulk : non inclus**.
  - Source : [FMP – Pricing plans](https://site.financialmodelingprep.com/pricing-plans)
- **Starter** : 29 $/mois (19 $ en annuel), 300 appels/min, **US Coverage**. **Premium** : 69 $/mois (49 $ en annuel), 750 appels/min, **« UK and Canada Coverage »**, 30 ans d'historique, calendriers corporatifs. **Ultimate** : 139 $/mois (99 $ en annuel), « Global Coverage », **« ETF & Mutual Fund Holdings »**, 13F, vrac — [FMP – Pricing plans](https://site.financialmodelingprep.com/pricing-plans)
- Licence : « Displaying or redistributing data sourced from FMP requires a specific Data Display and Licensing Agreement with FMP ». Des offres distinctes « Personal Use » et « Commercial Use » existent. FMP propose aussi un serveur MCP — [FMP – Pricing plans](https://site.financialmodelingprep.com/pricing-plans)

**Fiche : Finnhub**
- Endpoints pertinents (swagger officiel) : `/stock/metric` (Basic Financials), `/stock/financials` (« standardized … for global companies going back 30+ years »), `/stock/financials-reported` (également téléchargeable en vrac sur Kaggle « SEC Financials »), `/stock/profile2` (« free version of Company Profile », interrogeable par symbole, ISIN ou CUSIP), `/calendar/earnings` (« EPS and Revenue … are non-GAAP »), `/stock/dividend`, `/etf/holdings` (« full ETF holdings… global coverage »), `/etf/profile` — [Finnhub swagger.json](https://finnhub.io/static/swagger.json)
- La page de tarification FNB indique que la couverture mondiale des données de FNB et de fonds est réservée aux « advanced users and enterprise clients » (via support@finnhub.io) — [Finnhub – pricing ETF/indices](https://www.finnhub.io/pricing-etf-indices)
- Une source tierce marque « ETFs Holdings [PREMIUM] » — [n8n node Finnhub](https://frontend-f26.pages.dev/node/n8n-nodes-finnhub@0.1.10-finnhub/ETF:ETFs%20Holdings%20%5BPREMIUM%5D). La limite gratuite de 60 appels/min est citée par des sources tierces seulement, la page officielle étant rendue en JavaScript — [Massive vs Finnhub](https://massive.com/compare/massive-vs-finnhub)

**Fiche : Alpha Vantage**
- Gratuit : « standard API usage limit (25 API requests per day) ». Premier palier : **49,99 $/mois pour 75 req/min**. Les données temps réel et différées de 15 min sont soumises à un processus d'autorisation. Usage commercial : contacter les ventes — [Alpha Vantage – Premium](https://www.alphavantage.co/premium/), [Documentation](https://www.alphavantage.co/documentation/)
- La documentation de novembre 2026 marque **Company Overview (OVERVIEW) « Premium »** (« this is a premium API function »). Les autres fonctions fondamentales ne portent pas cette mention : INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, SHARES_OUTSTANDING, EARNINGS, EARNINGS_ESTIMATES, ETF_PROFILE, DIVIDENDS, SPLITS, LISTING_STATUS, EARNINGS_CALENDAR, IPO_CALENDAR — [Alpha Vantage – Documentation](https://www.alphavantage.co/documentation/)
- Les états financiers sont décrits comme des « normalized fields mapped to GAAP and IFRS taxonomies of the SEC », généralement rafraîchis le jour même de la publication. Les prix TSX sont disponibles avec le suffixe `.TRT` (exemple `SHOP.TRT`) — [Alpha Vantage – Documentation](https://www.alphavantage.co/documentation/)
- EARNINGS renvoie `fiscalDateEnding`, `reportedDate`, `reportTime` (exemple IBM : `2026-09-30`, publié le `2026-10-21`, `post-market`) — [test direct 2026-11-14](https://www.alphavantage.co/query?function=EARNINGS&symbol=IBM&apikey=demo)
- LISTING_STATUS accepte un paramètre `date` (à partir du 2010-01-01) pour remonter dans le temps, avec les titres actifs ou radiés — [Alpha Vantage – Documentation](https://www.alphavantage.co/documentation/)

**Fiche : SimFin**
- Paliers : FREE à 0 $ (2 appels/s), START à 15 $/mois (180 $/an), BASIC à 35 $/mois, PRO à 71 $/mois. FREE couvre **5 000 titres américains**. L'historique des fondamentaux est de 5 ans selon la liste et de 7 ans selon le tableau (la page se contredit). Le téléchargement en vrac est disponible en FREE (5 ans, différé). Aucune couverture canadienne n'est mentionnée. Les données doivent être supprimées à la fin de l'abonnement. Projets commerciaux : offre Enterprise — [SimFin – Prices](https://www.simfin.com/en/prices/)
- Champs point-in-time : `Publish Date` et `Restated Date`. Pour les sociétés américaines, `PUBLISH_DATE` « only uses the publication date of the Form 10-K and 10-Q… and does not use … preliminary reports filed as Form 8-K ». L'information a donc pu être publique **avant** cette date — [simfin/names.py](https://raw.githubusercontent.com/SimFin/simfin/master/simfin/names.py)
- Paquet Python `simfin` 1.0.2 publié le 2026-04-30, licence MIT — [PyPI simfin](https://pypi.org/pypi/simfin/json)

**Fiche : EODHD**
- Palier gratuit : **20 appels/jour**, 20 req/min, 1 an d'historique. **Fondamentaux (actions mondiales, FNB mondiaux, fonds US) non inclus**. Le calendrier corporatif (résultats, IPO, fractionnements) est absent du gratuit ; il est disponible en module à 19,99 $/mois. Un appel de fondamentaux coûte 10 crédits. « Fundamentals Data Feed » coûte **59,99 $/mois** (599,90 $/an). Des plans Personal et Commercial distincts existent, ainsi qu'un serveur MCP — [EODHD – Pricing](https://eodhd.com/pricing)
- La clé `demo` fonctionne sur VTI.US. `ETF_Data` contient `ISIN`, `NetExpenseRatio` (0,0003), `TotalAssets`, `Holdings_Count` (3 417), `Holdings` (3 417 lignes), `Sector_Weights`, `World_Regions` et `Inception_Date` — [test direct 2026-11-14](https://eodhd.com/api/fundamentals/VTI.US?api_token=demo&fmt=json)

**Fiche : Tiingo**
- Starter (gratuit) : 50 req/h, 1 000 req/jour, 500 symboles uniques par mois, 1 Go. Power : 30 $/mois (300 $/an). Commercial (usage interne) : 50 $/mois. Le module fondamentaux est vendu « in coordination with our third-party provider », sans prix affiché. Usage individuel : « you may not display or share the data with another person or organization » — [Tiingo – Pricing](https://www.tiingo.com/about/pricing)
- Fondamentaux : module complémentaire, avec les valeurs du **DOW 30 gratuites en évaluation (3 ans)** — [Tiingo – Fundamentals docs](https://api.tiingo.com/documentation/fundamentals)

**Fiche : Massive (ex-Polygon.io)**
- Endpoint `GET /stocks/financials/v1/income-statements`, **non inclus dans Stocks Basic (gratuit)**. Il est inclus dans Stocks Advanced et dans l'extension « Financials & Ratios ». Historique depuis le 2009-03-29, identifiants CIK. Le champ `filing_date` est « the most recent SEC filing that included the period's data… not necessarily the date this period was originally filed ». Pour la date originale, utiliser `/stocks/filings/vX/index` — [Massive – Income statements](https://massive.com/docs/rest/stocks/fundamentals/income-statements)
- Prix : « Financials & Ratios » à 29 $/mois, Stocks Advanced à 199 $/mois, tous deux « Individual use only ». Modules partenaires : ETF Global à 99 $/mois, calendrier TMX à 99 $/mois — [Massive – Pricing](https://massive.com/pricing)

**Fiche : Financial Datasets (financialdatasets.ai)**
- **Aucun palier gratuit** affiché : « Credits » à 20 $ en paiement unique pour 1 000 requêtes, Personal à 200 $/mois (100 000 requêtes), Professional à 1 000 $/mois avec licence commerciale et « Data redistribution rights … with attribution ». Les données internationales se limitent aux fondamentaux annuels britanniques et français (FTSE 100, CAC 40), donc **pas de Canada**. Un jeu « Index fund holdings » couvre les avoirs de FNB — [Financial Datasets – Pricing](https://www.financialdatasets.ai/pricing)
- Serveur MCP officiel `financial-datasets/mcp-server` : licence MIT, environ 2,3 k étoiles, **dernier push le 2025-06-05** — [GitHub API](https://api.github.com/repos/financial-datasets/mcp-server)

**Fiche : Macrotrends**
- Conditions d'utilisation mises à jour le 13 novembre 2025. Elles comportent une section « Prohibited Activities » et réservent tout usage non expressément accordé. La liste exacte n'a pas pu être lue (403) — [Macrotrends – Terms](https://www.macrotrends.net/terms)

### Inferences
- La combinaison gratuite la plus solide pour l'univers : SEC (fondamentaux XBRL, y compris pour les huit titres canadiens intercotés), puis Alpha Vantage (EARNINGS et DIVIDENDS datés, ETF_PROFILE ; 25 req/jour obligent à mettre en cache), puis la saisie manuelle pour ATD et CSU.
- Le quota FMP Basic (« AAPL, TSLA, AMZN and 84 more ») couvre probablement plusieurs titres américains de l'univers. La liste exacte des 87 symboles n'a pas été vue, il faut tester RY et ENB.
- Le `filing_date` de Massive et la `Publish Date` de SimFin ne sont **pas** des dates de première publication fiables. Pour éviter le look-ahead, il faut recalculer la publication à partir des submissions SEC (`acceptanceDateTime`) ou du communiqué (8-K Item 2.02 ou 6-K).

### Gaps
- **Morningstar** (pas d'API gratuite présumée) et **Intrinio** (pas de palier gratuit présumé) : non vérifiés dans cette session.
- Finnhub : la limite gratuite officielle (60 appels/min) et le statut gratuit ou premium de `/stock/metric`, `/stock/financials` et `/etf/holdings` restent non confirmés sur une page officielle, la page tarifaire étant rendue en JavaScript.
- Alpha Vantage : la couverture des fondamentaux pour des symboles TSX non déposants à la SEC n'a pas été testée (clé démo limitée à IBM).
- La liste exacte des symboles du FMP Basic et le texte complet des interdictions de Macrotrends restent inconnus.

## 4. Données FNB : avoirs, pondérations, frais/RFG, ASG, réplication (iShares, BMO, Vanguard, SPDR, Invesco, N-PORT, API FNB) et conditions des émetteurs

### Takeaway
Deux téléchargements officiels fonctionnent sans clé le 2026-11-14 : iShares Canada (CSV quotidien, XIU et XBB au 12 novembre 2026) et SPDR (XLSX quotidien SPY au 12 novembre 2026). Les autres (iShares US, Invesco, Vanguard, BMO) n'ont pas pu être confirmés par script. Le fichier SPDR **interdit expressément** la reproduction ou la divulgation à des tiers sans consentement écrit. Les conditions iShares interdisent le scraping. Pour un usage redistribuable, il faut des agrégats dérivés ou la SEC (N-PORT, trimestriel et différé), qui ne couvre pas les FNB canadiens.

### Cited Findings

**Fiche : iShares Canada (BlackRock Canada) – CSV des avoirs**
- Patron d'URL fonctionnel : `https://www.blackrock.com/ca/investors/en/products/{productId}/{slug}/1464253357814.ajax?fileType=csv&fileName={TICKER}_holdings&dataType=fund`.
  - XIU (id 239832) : en-tête `Fund Holdings as of,"Nov 12, 2026"`. Colonnes `Ticker, Name, Sector, Asset Class, Market Value, Weight (%), Notional Value, Shares, Price, Location, Exchange, Currency, FX Rate, Market Currency`. 69 lignes, qui incluent les dix titres canadiens de l'univers (RY 9,58 %, TD 6,94 %, SHOP, ENB, CNQ, MFC, CNR, CSU 1,77 %, ATD 1,46 %, FTS 1,03 %).
  - Sources : [test direct XIU 2026-11-14](https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf/1464253357814.ajax?fileType=csv&fileName=XIU_holdings&dataType=fund)
- XBB (id 239493) : environ 1 950 lignes. Colonnes supplémentaires pour l'obligataire : `Par Value, Duration, Maturity, Coupon (%), Effective Date` — [test direct XBB 2026-11-14](https://www.blackrock.com/ca/investors/en/products/239493/ishares-canadian-universe-bond-index-etf/1464253357814.ajax?fileType=csv&fileName=XBB_holdings&dataType=fund)
- Artefacts observés dans XIU : une ligne `"2299955D","CONSTELLATION SOFTWARE INC"` avec un prix de 0,00 et une valeur de 0,98 $ (probablement un droit ou une entitlement), des lignes de trésorerie (CAD, USD, garanties) et un contrat à terme `PTZ6` (S&P/TSE 60 déc. 2026) de valeur nulle mais de valeur notionnelle 39,2 M$. Les fichiers **ne contiennent ni ISIN ni CUSIP**, seulement des tickers — [test direct XIU 2026-11-14](https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf/1464253357814.ajax?fileType=csv&fileName=XIU_holdings&dataType=fund)

**Fiche : iShares US**
- Le patron `https://www.ishares.com/us/products/{id}/{slug}/1467271812596.ajax?fileType=csv&fileName=AGG_holdings&dataType=fund` a renvoyé une **page HTML** (titre « iShares Core U.S. Aggregate Bond ETF | AGG ») au lieu d'un CSV le 2026-11-14. Le point d'accès script a donc changé ou est protégé — [test direct 2026-11-14](https://www.ishares.com/us/products/239458/ishares-core-total-us-aggregate-bond-etf/1467271812596.ajax?fileType=csv&fileName=AGG_holdings&dataType=fund)
- Conditions iShares et BlackRock : les conditions de l'outil Factor Box (iShares US) interdisent le « scraping, database scraping … any robot or automated device » pour « searching, monitoring or copying the site or obtaining reports or data ». Les conditions BlackRock Insights interdisent de « sell, copy, publish, distribute … reproduce, and/or create any derivative works ». Les données téléchargées via l'outil de rapports sont réservées à un usage interne — [iShares – Factor Box terms](https://www.ishares.com/us/compliance/factor-box-terms), [BlackRock – Insights terms](https://www.blackrock.com/corporate/compliance/insights-terms-and-conditions), [iShares – Report generation tool](https://ishares.com/us/resources/tools/report-generation-tool/create-report)

**Fiche : SPDR (State Street) – XLSX quotidien**
- `https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx` renvoie un XLSX (environ 54 ko) avec « As of 12-Nov-2026 ». Colonnes `Name, Ticker, Identifier, SEDOL, Weight, Sector, Shares Held, Local Currency` — [test direct 2026-11-14](https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx)
- Mention de licence intégrée au fichier : « The whole or any part of this work may not be reproduced, copied or transmitted or any of its contents disclosed to third parties without SSGA's express written consent ». Le fichier annonce aussi que « State Street Global Advisors (SSGA) is now State Street Investment Management », et plusieurs FNB ont été renommés au 31/10/2026 — [test direct 2026-11-14](https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx)

**Fiche : Invesco (QQQ), Vanguard (VTI/BND/ESGV), BMO (ZST/ZAG)**
- Invesco : `https://www.invesco.com/us/financial-products/etfs/holdings/main/holdings/0?audienceType=Investor&action=download&ticker=QQQ` et l'API `dng-api.invesco.com` ont renvoyé **HTTP 406** (protection anti-robot probable) — [test direct 2026-11-14](https://www.invesco.com/us/financial-products/etfs/holdings/main/holdings/0?audienceType=Investor&action=download&ticker=QQQ)
- Vanguard : `investor.vanguard.com/.../profile/api/VTI/portfolio-holding/stock` a renvoyé **404**. La page VTI affiche une composition datée du 30/06/2025 dans l'extrait de recherche — [test direct 2026-11-14](https://investor.vanguard.com/investment-products/etfs/profile/api/VTI/portfolio-holding/stock?start=1&count=5), [Vanguard – VTI](https://investor.vanguard.com/investment-products/mutual-funds/profile/VTI)
- BMO GAM : le site bmogam.com était injoignable depuis l'environnement de test. Des tiers affichent des avoirs de ZST à des dates divergentes : Trackinsight (51 avoirs au 30/06/2026) et Cboe Canada (49 avoirs au 03/09/2026) — [Trackinsight ZST](https://www.trackinsight.com/en/fund/ZST/holdings), [Cboe Canada](https://etfmarket.cboe.com/canada/en/etf-comparison/ZST-vs-ZST.L)

**Fiche : API FNB (frais, actifs, avoirs)**
- Alpha Vantage `ETF_PROFILE` (non marqué premium, 25 req/jour) renvoie `net_assets`, `net_expense_ratio`, `portfolio_turnover`, `dividend_yield`, `inception_date`, `leveraged`, `sectors` et `holdings` (symbole, description, poids). Pour QQQ : 103 avoirs, `net_expense_ratio 0.0018`, `last_updated 2026-11-13` — [test direct 2026-11-14](https://www.alphavantage.co/query?function=ETF_PROFILE&symbol=QQQ&apikey=demo)
- EODHD `ETF_Data` (fondamentaux payants, 59,99 $/mois) : avoirs complets, `NetExpenseRatio`, `TotalAssets`, pondérations sectorielles et régionales — [test direct](https://eodhd.com/api/fundamentals/VTI.US?api_token=demo&fmt=json), [EODHD pricing](https://eodhd.com/pricing)
- FMP : avoirs de FNB réservés au palier **Ultimate (139 $/mois)** — [FMP pricing](https://site.financialmodelingprep.com/pricing-plans). Finnhub : `/etf/holdings` à couverture mondiale, mais réservé aux « advanced / enterprise » — [Finnhub swagger](https://finnhub.io/static/swagger.json), [Finnhub ETF pricing](https://www.finnhub.io/pricing-etf-indices). sec-api.io : N-PORT en palier Business (199 $/mois) — [sec-api.io pricing](https://sec-api.io/pricing)
- SEC N-PORT pour les FNB américains : `Fund("VOO").get_portfolio()` dans EdgarTools, ou les jeux trimestriels de la SEC (voir §1) — [EdgarTools](https://github.com/dgunning/edgartools), [SEC N-PORT](https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets)

### Inferences
- Pour la transparence de XIU, XBB, ZST et ZAG (FNB canadiens), aucune source réglementaire machine-lisible équivalente au N-PORT n'a été trouvée. Le CSV de l'émetteur est la seule source quotidienne. Il convient de stocker la date « as of » du fichier comme date d'observation et l'horodatage de collecte comme date de publication, et de ne redistribuer que des expositions agrégées.
- Faute d'ISIN dans les fichiers iShares Canada, la jointure avec la base de titres passera par une correspondance ticker + bourse vers FIGI (OpenFIGI, `exchCode CT`, voir §5).
- La méthode de réplication (physique ou synthétique, échantillonnage) et le RFG des FNB canadiens doivent venir des fiches techniques et prospectus des émetteurs. Aucune API gratuite vérifiée ne les fournit pour les FNB TSX.
- GLD (SPDR Gold) détient de l'or physique : sa transparence est triviale (100 % or) et ne passe pas par un fichier d'actions.

### Gaps
- Patrons d'URL fonctionnels pour iShares US (AGG, TLT), Vanguard (VTI, BND, ESGV), Invesco (QQQ) et BMO (ZST, ZAG) : non confirmés, à retester depuis un navigateur.
- Le texte intégral des conditions générales d'iShares.com US, de BlackRock Canada, de Vanguard, d'Invesco et de BMO sur le scraping et la redistribution n'a pas été lu (404, 403 ou injoignable).
- Les RFG, ASG et méthodes de réplication de chaque FNB de l'univers n'ont pas été collectés.

## 5. Données de référence et identifiants : OpenFIGI, GLEIF LEI, ISIN/CUSIP, GICS vs SIC/NAICS

### Takeaway
OpenFIGI et GLEIF sont gratuits et fonctionnent sans clé (OpenFIGI : 25 req/min sans clé, 250 avec). Ils permettent de relier ticker TSX, FIGI, LEI et ISIN. Les CUSIP et ISIN nord-américains relèvent de la licence CGS (FactSet), qui fait l'objet d'un litige antitrust. GICS est propriétaire (S&P/MSCI) et ne peut pas être redistribué sans licence. Les codes SIC de la SEC sont gratuits dans l'API submissions.

### Cited Findings

**Fiche : OpenFIGI**
- API gratuite et ouverte. Clé via l'en-tête `X-OPENFIGI-APIKEY`. Mapping (`POST /v3/mapping`) : **25 req/min et 10 tâches par requête sans clé, 250 req/min et 100 tâches avec clé**. Search/Filter : 5 req/min sans clé, 20 avec. Codes 429 (avec `retry-after`) et 413. Les actions non cotées sont exclues par défaut (`includeUnlistedEquities`) — [OpenFIGI – API documentation](https://www.openfigi.com/api/documentation)
- `exchCode "CT"` (Toronto) : RY donne FIGI `BBG000BCJHV8` (composite `BBG000BCJG31`) et XIU donne `BBG000C1JRD9` (securityType ETP). En-têtes `ratelimit-limit: 25`, `ratelimit-policy: 25;w=60` — [test direct 2026-11-14](https://api.openfigi.com/v3/mapping)

**Fiche : GLEIF LEI API**
- `https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]=...` fonctionne sans clé. RY a pour LEI `ES7IP3U3RHIGC71XBU11`, statut ISSUED, juridiction CA. Relations : `isins`, `direct-parent`, `ultimate-parent`, `direct-children`, `branches`. Les BIC sont fournis. Aucun en-tête de limite de débit n'a été observé — [test direct 2026-11-14](https://api.gleif.org/api/v1/lei-records/ES7IP3U3RHIGC71XBU11)
- Licence CC0 1.0 pour le Global LEI Index et limite de 60 req/min : affirmations **de sources tierces seulement** — [Apify LEI actor](https://apify.com/rein8/lei-legal-entity-lookup.md), [Jentic GLEIF](https://jentic.com/apis/gleif.org/gleif.md). Page officielle : [GLEIF API](https://gleif.org/en/lei-data/gleif-api)

**Fiche : CUSIP / ISIN**
- Recours collectif devant le SDNY contre CUSIP Global Services, S&P Global, l'ABA et FactSet au sujet des licences et des frais CUSIP. Demande de certification en novembre 2025, puis gain procédural des demandeurs. FactSet a acquis CGS pour près de 2 G$ (annonce de décembre 2021). La Commission européenne a émis une communication des griefs sur les frais ISIN — [WatersTechnology](https://www.waterstechnology.com/data-management/7952899/where-have-four-years-of-cusip-legal-drama-gone), [MLex](https://www.mlex.com/mlex/articles/2406895/plaintiffs-seek-class-certification-in-us-antitrust-case-against-s-p-global-factset-aba)
- Finnhub `profile2` accepte l'ISIN ou le CUSIP en entrée — [Finnhub swagger](https://finnhub.io/static/swagger.json). EODHD fournit l'ISIN des FNB (VTI : `US9229087690`) — [test direct](https://eodhd.com/api/fundamentals/VTI.US?api_token=demo&fmt=json)

**Fiche : classifications sectorielles**
- GICS est « the exclusive property and a trademark » de S&P et MSCI. Les utilisateurs s'engagent à ne pas « redistribute the GICS Service in any form … to any third party other than as permitted » — [FundApps – GICS disclaimer](https://docs.fundapps.co/si/GICSDisclaimer.html), [FIS – GICS third-party terms](https://www.fisglobal.com/-/media/fisglobal/files/PDF/policy/third-party-terms/GICS-Service-Third-Party-Data-Terms.pdf?sc_lang=en)
- Consultation S&P DJI et MSCI du 17 juillet 2026 sur des changements possibles de la structure GICS pour 2027 — [S&P Global press](https://press.spglobal.com/2026-07-17-S-P-DOW-JONES-INDICES-AND-MSCI-ANNOUNCE-CONSULTATION-ON-POTENTIAL-CHANGES-TO-THE-GLOBAL-INDUSTRY-CLASSIFICATION-STANDARD-GICS-R)
- Code SIC SEC gratuit dans submissions (AAPL : `sic 3571 Electronic Computers` ; RY : `sic 6029`) et dans les FSDS/FSN — [test direct AAPL](https://data.sec.gov/submissions/CIK0000320193.json), [SEC FSDS](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets)

### Inferences
- La colonne « Sector » des CSV iShares utilise des libellés de secteurs GICS (Financials, Energy…). Les republier tels quels dans une base partagée pourrait poser un problème de licence GICS. Il vaut mieux mapper vers SIC ou NAICS, ou vers une taxonomie maison.
- Chaîne d'identifiants recommandée pour A5 : ticker + bourse → FIGI (OpenFIGI) → LEI (GLEIF, qui donne aussi les ISIN liés) → CIK (SEC) lorsqu'il existe.

### Gaps
- Licence officielle de GLEIF (CC0) et limite de débit officielle : non lues sur gleif.org (page à contenu dynamique).
- Licence ou conditions d'usage de FIGI (OpenFIGI) : non lues.
- Licence de NAICS (US Census ; SCIAN de Statistique Canada sous Licence du gouvernement ouvert) : non vérifiée dans cette session.

## 6. Calendriers de résultats et dividendes déclarés (dates d'annonce) : sources gratuites

### Takeaway
Les meilleures sources gratuites et datées sont Alpha Vantage, puis Finnhub, puis la SEC. Alpha Vantage fournit EARNINGS_CALENDAR (3, 6 ou 12 mois), EARNINGS (`reportedDate`, `reportTime`) et DIVIDENDS (`declaration_date`, `ex_dividend_date`, `record_date`, `payment_date`). Finnhub fournit `/calendar/earnings`. La SEC fournit des horodatages d'acceptation (`acceptanceDateTime`) pour les 8-K et 6-K. Le calendrier JSON de Nasdaq fonctionne, mais il est non officiel.

### Cited Findings
- Alpha Vantage `EARNINGS_CALENDAR` : par défaut toutes les sociétés attendues sur 3 mois, avec `horizon` de 3, 6 ou 12 mois, en CSV (`symbol,name,reportDate,fiscalDateEnding,estimate,currency,timeOfTheDay`) — [Alpha Vantage – Documentation](https://www.alphavantage.co/documentation/), [test direct 2026-11-14](https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey=demo)
- Alpha Vantage `DIVIDENDS` : exemple IBM `declaration_date 2026-10-21`, `ex_dividend_date 2026-11-10`, `record_date 2026-11-10`, `payment_date 2026-12-10`, `amount 1.69` — [test direct 2026-11-14](https://www.alphavantage.co/query?function=DIVIDENDS&symbol=IBM&apikey=demo)
- Finnhub `/calendar/earnings` : publications historiques et à venir, avec EPS et revenus **non-GAAP**. `/stock/dividend` couvre 30 ans et `/stock/dividend2` des dividendes mondiaux — [Finnhub swagger](https://finnhub.io/static/swagger.json)
- FMP Basic : calendriers de résultats et de dividendes limités à un mois et aux symboles autorisés — [FMP pricing](https://site.financialmodelingprep.com/pricing-plans). EODHD : calendrier absent du gratuit, module à 19,99 $/mois — [EODHD pricing](https://eodhd.com/pricing)
- Nasdaq (non officiel) : `https://api.nasdaq.com/api/calendar/earnings?date=2026-11-18` renvoie du JSON (`asOf`, `rows` avec `symbol`, `time`, `fiscalQuarterEnding`, `epsForecast`, `lastYearRptDt`). Ses conditions d'utilisation n'ont pas été vérifiées — [test direct 2026-11-14](https://api.nasdaq.com/api/calendar/earnings?date=2026-11-18)
- SEC : `acceptanceDateTime` à la seconde près pour chaque dépôt, y compris les 6-K des banques canadiennes — [test direct](https://data.sec.gov/submissions/CIK0001000275.json)

### Inferences
- Pour les dividendes déclarés des titres TSX, la date d'annonce primaire est le communiqué de l'émetteur, souvent déposé en 6-K pour les intercotés. Ni Alpha Vantage ni Finnhub n'ont été testés sur des symboles `.TRT`.

### Gaps
- Aucune source officielle gratuite (TMX ou TSX) n'a été identifiée pour un calendrier de résultats ou de dividendes canadiens. TMX existe en module payant chez Massive (99 $/mois).

## 7. SDK Python et serveurs MCP

### Takeaway
EdgarTools (MIT, v6.1.0 du 2026-11-12) est le choix évident pour EDGAR, avec un MCP intégré. `sec-edgar-api` (jadchaar) n'a pas bougé depuis 2023. FinanceDatabase (MIT) est actif. Côté MCP : `sec-edgar-mcp` (AGPL-3.0, attention à la licence copyleft), Alpha Vantage MCP (MIT), et des MCP de FMP, EODHD et sec-api.io annoncés par ces fournisseurs.

### Cited Findings
- `edgartools` 6.1.0 (2026-11-12), MIT, Python 3.11 ou plus — [PyPI](https://pypi.org/pypi/edgartools/json), [GitHub](https://github.com/dgunning/edgartools)
- `sec-edgar-api` 1.1.0 (2023-09-30), MIT, dernier push en juillet 2024. Ce wrapper non officiel est stagnant — [GitHub API](https://api.github.com/repos/jadchaar/sec-edgar-api), [PyPI](https://pypi.org/pypi/sec-edgar-api/json)
- `sec-edgar-downloader` 5.1.0 (2026-02-02), MIT — [GitHub API](https://api.github.com/repos/jadchaar/sec-edgar-downloader/releases/latest)
- `simfin` 1.0.2 (2026-04-30), MIT — [PyPI](https://pypi.org/pypi/simfin/json)
- `financedatabase` 2.5.2 (2026-11-14), MIT, « 300.000+ symbols containing Equities, ETFs, Funds, Indices… », environ 9,6 k étoiles — [GitHub API](https://api.github.com/repos/JerBouma/FinanceDatabase), [PyPI](https://pypi.org/pypi/financedatabase/json)
- `sec-edgar-mcp` (stefanoamorelli) v1.1.0 (2026-08-20), **AGPL-3.0**. Variable `SEC_EDGAR_USER_AGENT` obligatoire. Outils : états financiers parsés du XBRL et transactions d'initiés Form 3/4/5 — [GitHub API](https://api.github.com/repos/stefanoamorelli/sec-edgar-mcp), [README](https://raw.githubusercontent.com/stefanoamorelli/sec-edgar-mcp/main/README.md)
- `financial-datasets/mcp-server` : MIT, dernier push le 2025-06-05, et l'API sous-jacente est payante — [GitHub API](https://api.github.com/repos/financial-datasets/mcp-server), [pricing](https://www.financialdatasets.ai/pricing)
- `alphavantage/alpha_vantage_mcp` : MIT, push du 2026-10-03 — [GitHub API](https://api.github.com/repos/alphavantage/alpha_vantage_mcp)
- MCP annoncés par les fournisseurs : sec-api.io (inclus dans le gratuit à 100 appels) — [sec-api.io](https://sec-api.io/pricing) ; EODHD (« MCP server Included ») — [EODHD](https://eodhd.com/pricing) ; FMP (« MCP Server ») — [FMP](https://site.financialmodelingprep.com/pricing-plans) ; EdgarTools (local et hébergé) — [GitHub](https://github.com/dgunning/edgartools)

### Inferences
- Pour un dépôt sous licence permissive, préférer le MCP d'EdgarTools (MIT) à `sec-edgar-mcp` (AGPL-3.0), dont l'intégration dans un service réseau peut imposer la publication du code.
- Les classifications sectorielles de FinanceDatabase devraient être vérifiées avant redistribution, en raison du risque GICS.

### Gaps
- Le dépôt GitHub officiel du MCP EODHD (`EodHistoricalData/EODHD-APIs-MCP-Server`) est introuvable sous ce nom (404 sur l'API GitHub).
- Le serveur MCP de Massive (Polygon) n'a pas été vérifié.

## 8. Pièges 2025–2026 et points d'attention point-in-time

### Takeaway
Les principaux risques pour A5 sont de trois ordres. Le premier est le look-ahead introduit par les champs « dernière version » : frames SEC, `filing_date` de Massive, `Publish Date` de SimFin. Le deuxième regroupe les changements d'identifiants (XOM change de CIK en juillet 2026) et les fournisseurs qui basculent des endpoints en premium (Alpha Vantage OVERVIEW). Le troisième tient aux licences : SEDAR+ interdit l'automatisation, et les fichiers d'émetteurs ou de fournisseurs sont non redistribuables.

### Cited Findings
- Frames renvoie le fait « last filed » — [SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces). Massive : `filing_date` « not necessarily the date this period was originally filed » — [Massive](https://massive.com/docs/rest/stocks/fundamentals/income-statements). SimFin : `PUBLISH_DATE` ignore les 8-K préliminaires — [simfin names.py](https://raw.githubusercontent.com/SimFin/simfin/master/simfin/names.py)
- Le CIK de XOM passe de 34088 à 2115436 après la redomiciliation du 2026-07-01 — [8-K](https://investor.exxonmobil.com/sec-filings/all-sec-filings/content/0001193125-26-291990/d71068d8k12b.htm), [test company_tickers.json](https://www.sec.gov/files/company_tickers.json)
- Alpha Vantage OVERVIEW est marqué premium — [Documentation](https://www.alphavantage.co/documentation/). Le gratuit reste limité à 25 req/jour — [Premium](https://www.alphavantage.co/premium/)
- Le calendrier N-PORT est en mouvement : conformité reportée à novembre 2027 et mai 2028, et proposition de février 2026 de garder une publication trimestrielle — [Thompson Hine](https://www.thompsonhine.com/insights/sec-extends-compliance-date-for-amendments-to-form-n-port), [MFDF](https://www.mfdf.org/home/news---resources/news/2026/02/25/sec-proposes-n-port-amendments)
- FSDS retraités en décembre 2024 (états primaires seulement, champ segments ajouté) — [SEC FSDS](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets)
- SSGA devient « State Street Investment Management » et des FNB SPDR sont renommés au 31/10/2026 (fichier SPY). C'est un risque pour les correspondances par nom de fonds — [fichier SPY](https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx)
- Une requête sans User-Agent reçoit 403 sur data.sec.gov — [test direct](https://data.sec.gov/submissions/CIK0000320193.json). Le CORS n'est pas pris en charge — [SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- Le ticker CN est CNR au TSX mais CNI au NYSE et dans les fichiers SEC — [company_tickers.json](https://www.sec.gov/files/company_tickers.json), [XIU CSV](https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf/1464253357814.ajax?fileType=csv&fileName=XIU_holdings&dataType=fund)
- Les fichiers d'avoirs contiennent des lignes parasites (droits à prix nul, contrats à terme à valeur nulle mais notionnel élevé, trésorerie et garanties) — [XIU CSV](https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf/1464253357814.ajax?fileType=csv&fileName=XIU_holdings&dataType=fund)
- Sur FMP, quatre limites se cumulent au palier gratuit : 500 Mo de bande passante sur 30 jours, 5 réponses par appel, symboles limités et Canada payant — [FMP](https://site.financialmodelingprep.com/pricing-plans)

### Inferences
- Règle à appliquer dans OKF : chaque fait porte `observation_date` (fin de période), `publication_date` (`acceptanceDateTime`, ou à défaut `filed`), `source_url`, `licence`, `retrieved_at`, `vintage` (identifiant accn ou version du fichier). Les sources « latest-only » (frames, FMP, Massive) ne doivent servir qu'aux vues courantes, jamais aux backtests.
- La pondération de transparence doit utiliser `Weight (%)` ou `Market Value`, et non `Notional Value`, pour les lignes de dérivés. Il faut aussi normaliser les tickers (CNR et CNI, classes A/B) avant la jointure.

### Gaps
- Aucun changement 2025–2026 des API data.sec.gov (nouveaux endpoints, nouvelle limite) n'a été trouvé au-delà de l'apparition du champ `core_type`, sans documentation trouvée.
- Les changements récents de conditions chez Finnhub, Tiingo et Morningstar n'ont pas été examinés.
