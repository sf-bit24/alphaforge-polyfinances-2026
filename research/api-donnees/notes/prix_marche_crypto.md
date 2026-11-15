# API gratuites / freemium — prix de marché (actions, FNB, indices), opérations sur titres et crypto-actifs (état au 14 novembre 2026)

Notes de recherche pour AlphaForge AI (Datathon PolyFinances 2026, BN + AWS). Agent collecteur A5 (Strands Agents sur Bedrock/AgentCore), donc des appels potentiellement émis depuis des IP AWS. Univers : TSX (.TO), actions US, FNB (XIU.TO, XBB.TO, ZST.TO, SPY, QQQ, ESGV, AGG, TLT, GLD), BTC-USD et ETH-USD.

Conventions : chaque fait porte sa source. « Non vérifié » signale un chiffre issu d'un agrégateur tiers ou d'une seule source. Les pages tarifaires consultées le 14 novembre 2026 sont présumées à jour à cette date. Les sources tierces (agrégateurs, blogs de concurrents) sont signalées comme telles.

---

## 1. Actions / FNB / indices : fiches par fournisseur (statut 2026, quotas gratuits, premier palier payant)

### Takeaway
En novembre 2026, aucun fournisseur à clé gratuite ne couvre le TSX sans contrainte forte. Les paliers gratuits sont devenus très étroits : Alpha Vantage donne 25 requêtes/jour et 100 points de série seulement, EODHD 20 appels/jour sur 1 an d'historique, Marketstack 100 requêtes/mois, Massive (ex-Polygon) 5 appels/min sur les seules actions US. yfinance reste le moyen le plus pratique pour le .TO, mais il est non officiel, limité par IP (surtout depuis le cloud) et réservé à un usage personnel.

### Cited Findings

**yfinance (Yahoo Finance, non officiel)**
- Dernière version : 1.8.0, publiée le 3 novembre 2026. La page PyPI rappelle : « Remember - the Yahoo! finance API is intended for personal use only » et renvoie aux conditions d'utilisation de Yahoo pour les droits sur les données téléchargées. — [PyPI yfinance](https://pypi.org/project/yfinance/)
- Le README présente le projet comme un outil open source qui utilise les API publiques de Yahoo, « intended for research and educational purposes ». — [README yfinance](https://raw.githubusercontent.com/ranaroussi/yfinance/main/README.md)
- `curl_cffi` (usurpation d'empreinte de navigateur) est la dépendance par défaut, avec un repli sur `requests` documenté dans « Advanced Installation ». — [PyPI yfinance](https://pypi.org/project/yfinance/)
- Une source tierce indique que l'adaptateur HTTP bascule vers `requests` si `curl_cffi` est absent ou si `YF_DISABLE_CURL_CFFI` est défini. Elle ajoute que les deux backends peuvent être bloqués ou limités. — [orthogonal.info (tiers)](https://orthogonal.info/yfinance-python-stock-data-live-streaming-screening/)
- Les limitations de débit persistent en 2026 : HTTP 429 / `YFRateLimitError`. Une issue TradingAgents (env. septembre 2026) montre qu'un 429 peut interrompre un agent ou être interprété comme un symbole radié. — [TradingAgents #1386](https://github.com/TauricResearch/TradingAgents/issues/1386) ; [TradingAgents #437](https://github.com/TauricResearch/TradingAgents/issues/437)
- Issue de référence côté yfinance : « YFRateLimitError('Too Many Requests…') » (début 2025). — [yfinance #2289](https://github.com/ranaroussi/yfinance/issues/2289)
- Yahoo ne publie aucun quota. La limitation se fait par IP, et les hôtes cloud ou CI partagent la réputation de leurs IP. Source : billet d'un fournisseur concurrent, donc biaisé. — [SiftingIO](https://sifting.io/blog/yfinance-rate-limited-migrating-python-price-pulls-keyed-api)
- Des forums PythonAnywhere et Streamlit signalent des blocages depuis AWS et des IP cloud partagées : un script fonctionne en local mais échoue en hébergé. — [PythonAnywhere forum](https://www.pythonanywhere.com/forums/topic/36371/) ; [Streamlit forum](https://discuss.streamlit.io/t/yfratelimiterror-too-many-requests-rate-limited-try-after-a-while/111207)
- Une issue yfinance rapporte des 429 après environ 950 tickers. — [yfinance #2456](https://github.com/ranaroussi/yfinance/issues/2456)
- Conditions Yahoo : une version archivée des ToS (Irlande, antérieure au 9 juin 2025) accorde une « personal, royalty-free, non-transferable, non-assignable, revocable and non-exclusive licence to use the software and APIs ». Les ToS actuelles sont publiées sur legal.yahoo.com. — [Yahoo ToS, version antérieure](https://legal.yahoo.com/ie/en/yahoo/terms/otos/previousversion-2025-06-09/index.html) ; [Yahoo ToS actuelles](https://legal.yahoo.com/xw/en/yahoo/terms/otos/index.html)
- Selon Massive (concurrent), les conditions API de Yahoo interdisent d'en tirer un revenu sans autorisation écrite, et la licence Apache de yfinance couvre le code, pas les données. — [Massive vs yfinance (concurrent)](https://massive.com/compare/massive-vs-yfinance.md)

**Alpha Vantage**
- Gratuit : « standard API usage limit (25 API requests per day) ». La page premium ne donne aucune limite par minute pour le palier gratuit. — [Alpha Vantage Premium](https://www.alphavantage.co/premium/)
- Une source tierce mentionne 5 requêtes/min en gratuit (non vérifié). — [getdrio (tiers)](https://www.getdrio.com/mcp/alphavantage-calvernaz)
- Paliers premium : 75 req/min à 49,99 $/mois, 150 à 99,99 $, 300 à 149,99 $, 600 à 199,99 $, 1 200 à 249,99 $. Plans annuels à 499 $, 999 $, etc. (« 2 months off »). Les données temps réel et différées US pour usage personnel passent par « Alpha X Terminal ». — [Alpha Vantage Premium](https://www.alphavantage.co/premium/)
- Endpoints premium : TIME_SERIES_INTRADAY, TIME_SERIES_DAILY_ADJUSTED, REALTIME_BULK_QUOTES, REALTIME_BULK_BID_ASK_PRICES. — [Documentation Alpha Vantage](https://www.alphavantage.co/documentation/)
- TIME_SERIES_DAILY est gratuit, mais « The "full" outputsize is available to premium keys ». En gratuit, seul `compact` est disponible, soit les 100 derniers points. `full` donne « 25+ years of historical data ». — [Documentation Alpha Vantage](https://www.alphavantage.co/documentation/)
- Format de symbole TSX : SHOP.TRT (Toronto) et GPV.TRV (TSX Venture), et non le suffixe .TO. — [Documentation Alpha Vantage](https://www.alphavantage.co/documentation/)
- Serveur MCP officiel hébergé sur mcp.alphavantage.co, avec la clé gratuite dans l'URL (`https://mcp.alphavantage.co/mcp?apikey=...`) ou par OAuth selon le client. Le projet `calvernaz/alphavantage` est distinct et local, même s'il est parfois étiqueté « Official ». — [mcp.alphavantage.co](https://mcp.alphavantage.co/) ; [Documentation Alpha Vantage](https://www.alphavantage.co/documentation/)

**Twelve Data**
- Basic (gratuit) : « API requests: 8 (800 a day) », WebSocket « 8 trial ». Trois marchés : « Real-time US equities and ETFs », forex et crypto. — [Twelve Data Pricing](https://twelvedata.com/pricing)
- Le fichier llms de Twelve Data résume Basic ainsi : `Basic | $0 | 8 (800/day cap) | trial (8 symbols) | US (3)`. — [twelvedata llms-full](https://twelvedata.com/llms-full.txt)
- Plans payants : Grow 79 $/mois (« EOD global equities and ETFs »), Pro 229 $, Ultra 999 $. Aucun plan ne nomme explicitement le TSX. Un add-on « Cboe Canada » est proposé « From $180 /year » (non professionnel). La page affiche des chiffres incohérents entre les cartes et le tableau (377 contre 55+ crédits, par exemple). — [Twelve Data Pricing](https://twelvedata.com/pricing)
- « Business plans are required for any company, team, fund, or organization using Twelve Data — even if the data is only used internally ». — [Twelve Data Business pricing](https://twelvedata.com/pricing-business)
- `symbol_search` avec `show_plan=true` indique le plan requis pour chaque symbole, ce qui permet de vérifier RY sur le TSX. — [twelvedata llms-full](https://twelvedata.com/llms-full.txt)
- SDK Python officiel : `twelvedata-python`. — [GitHub twelvedata-python](https://www.github.com/twelvedata/twelvedata-python)

**Finnhub**
- Le palier gratuit est limité à 60 appels/min. En payant, 900/min pour les données de marché et 300/min pour les fondamentaux. Chiffres repris par plusieurs sources ; la page de tarifs ne s'est pas rendue lors de la consultation. — [finnhub.io/pricing (extrait de recherche)](https://finnhub.io/pricing)
- Les bougies (`/stock/candle`) sont premium : le palier gratuit renvoie 403, selon un concurrent. — [Massive vs Finnhub (concurrent)](https://massive.com/compare/massive-vs-finnhub)
- Un test tiers d'une clé gratuite a trouvé 10 endpoints fonctionnels : quote, profile2, peers, earnings, recommendation, metric, company-news, news, search, market-status. Les bougies, états financiers, dividendes, forex et crypto ne fonctionnaient pas. Source tierce, non vérifiée. — [freeapisforyou (tiers)](https://www.freeapisforyou.in/api/finnhub) ; [GitHub, document tiers](https://github.com/RaquazaCode/Fintech-AI-SaaS-Using-Google-Antigravity-Skills-Stitch/blob/main/Finnhub%20API%20Free%20Tier%20Capabilities%20(2026).docx.md)
- La couverture internationale (dont le TSX) exige un plan payant selon des agrégateurs, et les prix rapportés divergent (11,99–99,99 $/mois contre 100–500 $+). — [Jentic (tiers)](https://jentic.com/apis/finnhub.io/finnhub.md) ; [apicostcalc (tiers)](https://apicostcalc.com/finnhub.html)
- WebSocket gratuit limité à 50 symboles (tiers). — [Robot Wealth](https://robotwealth.com/finnhub-api/)

**Massive (ex-Polygon.io)**
- Polygon.io est devenu Massive le 30 octobre 2025 selon un communiqué, mais certaines pages datent le changement de 2026. `api.polygon.io` et `api.massive.com` fonctionnent en parallèle avec les mêmes clés. — [apicostcalc (tiers)](https://apicostcalc.com/blog/polygon-massive-rebrand-api-pricing.html)
- Stocks Basic gratuit : EOD, 2 ans d'historique, 5 appels/min (429 au-delà). Payant : Starter 29 $/mois, Developer 79 $, Advanced 199 $. Chiffres tiers, non vérifiés sur massive.com : la page de tarifs (JS) n'a rendu que Stocks Advanced. — [qveris (tiers)](https://qveris.ai/guides/polygon-pricing-optimized/) ; [apicostcalc (tiers)](https://apicostcalc.com/blog/polygon-massive-rebrand-api-pricing.html)
- Sur la page officielle : Stocks Advanced à 199 $/mois, « Individual use only », « real-time stock data, 20+ years of history, websockets » ; Financials & Ratios à 29 $/mois. — [massive.com/pricing](https://massive.com/pricing)
- Splits : « included in all Stocks plans », avec 2 ans d'historique sur Basic. — [Massive splits docs](https://massive.com/docs/rest/stocks/corporate-actions/splits.md)
- Dividendes : voir la section 3. — [Massive dividends docs](https://massive.com/docs/rest/stocks/corporate-actions/dividends.md)
- Serveur MCP officiel `massive-com/mcp_massive` (licence MIT, Python, anciennement `polygon-io/mcp_polygon`), hébergé sur `https://mcp.massive.com` et déclaré « experimental ». Couvre agrégats, trades et quotes, snapshots, dividendes, splits, IPO et fondamentaux. — [GitHub mcp_massive](https://github.com/massive-com/mcp_massive) ; [jsDelivr README mcp_polygon](https://cdn.jsdelivr.net/gh/polygon-io/mcp_polygon@master/README.md)

**Tiingo**
- Starter (gratuit) : 500 symboles uniques/mois, 50 requêtes/heure, 1 000/jour, 1 Go/mois, plus de 30 ans d'historique de prix, 5 ans de fondamentaux. Power : 30 $/mois ou 300 $/an pour un particulier ; usage commercial interne 50 $/mois ou 499 $/an. — [Tiingo Pricing](https://www.tiingo.com/about/pricing)
- Couverture : 110 531 titres, dont 49 683 actions US et chinoises et 60 848 FNB et fonds. Le Canada n'est pas mentionné. — [Tiingo Pricing](https://www.tiingo.com/about/pricing)
- Licence « Internal Use Only » : « Internal use means you may only use the data for your own personal use ». La redistribution est tarifée à part. — [Tiingo Pricing](https://www.tiingo.com/about/pricing)

**EODHD (EOD Historical Data)**
- Free (Sandbox, 0 $) : 20 appels/jour plus 500 appels de bienvenue, plafond de 20 requêtes/min, remise à zéro à minuit GMT. 1 an d'EOD, flux « live » différé de 15 min. Dividendes et splits inclus ; intraday et fondamentaux exclus. — [EODHD Pricing](https://eodhd.com/pricing)
- La page de l'API EOD précise : « Past year of data, personal use ». Chaque requête coûte un appel, y compris une 404. — [EODHD EOD API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)
- Payants : Historian (EOD All-World, plus de 30 ans, dividendes et splits) 19,99 $/mois ; EOD+Intraday 29,99 $ ; Fundamentals 59,99 $ ; All-in-One 99,99 $. Tous à 100 000 appels/jour et 1 000 req/min. Des plans « Commercial / B2B » sont distincts. — [EODHD Pricing](https://eodhd.com/pricing)
- Jeton `demo` : « without limits on six tickers » (AAPL.US, TSLA.US, BTC-USD.CC, VTI.US, AMZN.US, EURUSD.FOREX). — [EODHD EOD API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)
- Format `SYMBOL.EXCHANGE`, endpoint `https://eodhd.com/api/eod/SYMBOL.EXCHANGE`. — [EODHD EOD API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)
- Le TSX porte le code `TO` (MIC XTSE, environ 2 900 tickers) : page TD.TO, liste de l'échange TO. — [EODHD TD.TO](https://eodhd.com/financial-summary/TD.TO) ; [EODHD exchange TO](https://eodhd.com/exchange/TO?page=4) ; [EODHD llms-full](https://eodhd.com/llms-full.txt)
- Les listes de tickers sont disponibles sur les forfaits payants « and Free packages ». — [EODHD llms-full](https://eodhd.com/llms-full.txt)
- EODHD fait la promotion d'un « MCP Server For Financial Data by EODHD » (bandeau sur le site). — [EODHD exchange TO, p.27](https://eodhd.com/exchange/TO?page=27)

**Financial Modeling Prep (FMP)**
- Basic gratuit : 250 appels/jour, EOD, symboles limités aux échanges US. Starter (300 appels/min) est aussi limité aux échanges US. La page officielle a renvoyé 403 à la récupération ; ces informations viennent d'extraits de recherche. — [FMP Pricing](https://site.financialmodelingprep.com/developer/docs/pricing)
- Le quota gratuit se renouvelle toutes les 24 h, et un dépassement renvoie 429 sans frais. — [FMP education](https://site.financialmodelingprep.com/education/other/do-you-need-a-credit-card-to-use-financial-modeling-prep)
- Le prix du Starter diverge selon les sources tierces (19, 22 ou 29 $/mois) et n'a pas été vérifié. — [ROIC.ai (concurrent)](https://www.roic.ai/blog/financial-modeling-prep-alternative-roic-ai-vs-fmp) ; [multiples.vc](https://multiples.vc/compare/fmp-api-alternatives)

**Marketstack (APILayer)**
- Free : « 100 Requests / mo », « 1 Year History », « End-of-Day Data », HTTPS inclus, « 2700+ Stock Exchanges Info ». Le TSX n'est pas nommé. — [Marketstack Pricing](https://marketstack.com/pricing)
- Basic 9,99 $/mois (10 000 req, 10 ans, intraday IEX US) ; Professional 49,99 $ ; Business 149,99 $. — [Marketstack Pricing](https://marketstack.com/pricing)

**Stooq (CSV)**
- Depuis mars ou avril 2026, Stooq exige une clé API : une page HTML remplace le CSV, d'où une `ParserError` dans pandas-datareader. La clé s'obtient via la page `get_apikey` et un captcha ; une autre source mentionne un courriel à www@stooq.com. Sources communautaires, sans doc officielle. — [pandas-datareader #1012](https://github.com/pydata/pandas-datareader/issues/1012) ; [lite-C forums](https://opserver.de/ubb7/ubbthreads.php?ubb=showflat&Number=489362)
- pandas-datareader 0.11.0 (juin 2026) a retiré le lecteur Stooq. — [FXMacroData vs Stooq](https://fxmacrodata.com/articles/fxmacrodata-vs-stooq) ; [pandas-datareader-runner](https://github.com/moos-labs/pandas-datareader-runner)

**Nasdaq Data Link (ex-Quandl)**
- Les données « Free » ne demandent aucun abonnement ; les jeux premium sont vendus séparément. — [Nasdaq Data Link help](https://help.data.nasdaq.com/article/568-how-much-does-nasdaq-data-link-data-cost-how-do-i-find-pricing) ; [Getting started](https://docs.data.nasdaq.com/docs/getting-started)
- Clé gratuite : 50 000 req/jour, 2 000 par 10 min, 1 requête concurrente ; 50 req/jour en anonyme. Agrégateur, non vérifié. — [apis.io (tiers)](https://apis.io/rate-limits/nasdaq-omx-group/nasdaq-omx-group-rate-limits/)

**Alpaca Market Data**
- Basic gratuit : actions sur « the IEX exchange » uniquement. Historique « Since 2016 » mais limité aux « latest 15 minutes » (les 15 dernières minutes ne sont pas servies). 200 appels/min. WebSocket : 30 symboles. Algo Trader Plus à 99 $/mois : toutes les bourses US, 10 000/min. Couverture : actions et FNB US, options US. — [Alpaca Market Data docs](https://docs.alpaca.markets/docs/about-market-data-api)
- « With the exception of historical crypto data, all market data endpoints require authentication ». — [Alpaca Market Data docs](https://docs.alpaca.markets/docs/about-market-data-api)

**Databento**
- Crédit de 125 $ à l'inscription, utilisable sur l'historique ou le premier mois d'abonnement. Il expire après 6 mois, une seule fois par équipe. — [Databento usage-based pricing](https://databento.com/docs/knowledge-base/new-users/usage-based-pricing-and-data-credits) ; [Databento roadmap](https://roadmap.databento.com/announcements/end-of-early-access-125-in-free-credits-for-all-users)
- Un moyen de paiement est exigé à l'inscription. — [Databento blog](https://databento.com/blog/why-payment-information-required)
- La liste des venues inclut, pour le Canada : CSE, Cboe Canada, Toronto Stock Exchange, TSX Venture. Les schémas et prix TSX restent à vérifier. — [Databento venues](https://databento.com/venues)

**Questrade (courtier canadien)**
- « The Questrade API is free for anyone to use ». Données : cotes de niveau 1 et bougies historiques pour actions et options canadiennes et US. Les clients accèdent aux comptes et aux données, mais l'exécution d'ordres est réservée aux développeurs partenaires. — [Questrade developer](https://developer.questrade.com/) ; [Questrade API getting started](https://www.Questrade.com/api/documentation/getting-started)
- L'API exige un compte Questrade et l'acceptation d'un « API access agreement ». Les flux dépendent d'accords avec des tiers fournisseurs. — [Questrade API access agreement](https://www.questrade.com/disclosure/legal-notice-and-disclosures/api-access-agreement)

**Wealthsimple**
- Pas d'API publique officielle : accès via agrégateurs (SnapTrade, Plaid) ou bibliothèques non officielles GraphQL (`ws-api`). — [API Evangelist](https://providers.apievangelist.com/providers/wealthsimple/) ; [PyPI ws-api](https://pypi.org/project/ws-api/)

**TMX Datalinx / TMX (bourse de Toronto)**
- Aucune API EOD gratuite. Trading Summary quotidien (CSV, JSON, XML) avec prix visibles après connexion au webstore. Historique TSX depuis septembre 1998. — [TMX Webstore Trading Summary](https://www.tmxwebstore.com/products/trading-summary-daily) ; [TMX historical trading data](https://tmxinfoservices.com/corporate-and-reference-data/historical-trading-data)
- Essai gratuit de 90 jours mentionné dans un document TMX. Historical Market Data Online est facturé à l'enregistrement (0,14 par enregistrement trade/quote TSX). Prix pour un seul utilisateur final, sans droits de redistribution. — [TMX Historical Market Data Online](https://tmxinfoservices.com/corporate-and-reference-data/historical-trading-data/tmx-historical-market-data-online-custom-queries) ; [TMX whitepaper PDF](https://eu-assets.contentstack.com/v3/assets/bltabaa95ef14172c61/blt79b1097fcd949d15/6750edea7f3a37d7cdfde6f4/_b20f012a-072c-484e-a3eb-2ab73877dd2f_Whitepaper_Program.pdf)

**Google Finance (GOOGLEFINANCE)**
- `price` : « delayed by up to 20 minutes ». Contenu « solely for informational purposes, not for trading purposes or advice ». « Historical data cannot be downloaded or accessed via the Sheets API or Apps Script » (#N/A). Pas d'API programmatique. — [Google Docs Editors Help](https://support.google.com/docs/answer/3093281?hl=en)

**IEX Cloud**
- Fermé : annonce le 31 mai 2024, retrait de tous les produits au 31 août 2024. La bourse IEX continue de fonctionner. — [Alpha Vantage, analyse IEX Cloud (concurrent)](https://www.alphavantage.co/iexcloud_shutdown_analysis_and_migration/) ; [WatersTechnology](https://waterstechnology.com/data-management/7951882/iex-cloud-closure-forces-fintech-clients-to-seek-data-alternatives)
- Un ancien dirigeant d'IEX Cloud aurait racheté les actifs juste avant la fermeture. — [WatersTechnology](https://www.waterstechnology.com/node/7951983)

### Inferences
- Pour les .TO en volume, yfinance reste la seule option gratuite pratique. Il faut toutefois l'utiliser hors AWS (poste local ou CI) pour constituer un cache horodaté, et non comme dépendance temps réel de A5 sur AgentCore, puisque des 429 sont rapportés depuis les IP cloud.
- Alpha Vantage gratuit (25 req/jour, 100 points) suffit pour un rafraîchissement quotidien d'une poignée de titres TSX (format `.TRT`), pas pour reconstituer un historique.
- EODHD gratuit (20 appels/jour, 1 an) couvre probablement les .TO, ce qui reste à confirmer par un test, avec une clause « personal use ».
- Massive, Alpaca, FMP, Finnhub et Twelve Data gratuits sont pertinents pour les actions et FNB US, mais pas pour le TSX.

### Gaps
- Questrade, Wealthsimple et Databento ont été étudiés ici. En revanche, Tradier, Intrinio, Interactive Brokers, Investing.com, stockanalysis.com et Financial Datasets n'ont pas été vérifiés en ligne durant cette session (budget de recherche épuisé) : leurs quotas et conditions de 2026 restent inconnus.
- Le quota gratuit exact de Massive (5/min, 2 ans) n'est confirmé que par des tiers : la page de tarifs est rendue en JS.
- Les pages de tarifs et la documentation de Finnhub ne se sont pas rendues ; la liste des endpoints gratuits vient de tiers.
- Le prix exact du FMP Starter n'est pas vérifié.
- La présence du TSX dans les plans payants de Twelve Data (Grow et au-delà) n'est pas confirmée ; seul l'add-on Cboe Canada est nommé.

---

## 2. Couverture réelle du TSX (.TO) au palier gratuit

### Takeaway
Au palier gratuit, trois fournisseurs couvrent explicitement le TSX : yfinance (`.TO`, non officiel), Alpha Vantage (`.TRT`, 25 req/jour) et EODHD (`.TO`, 20 appels/jour, 1 an). Questrade le couvre aussi, mais exige un compte client. Twelve Data, Finnhub, FMP, Massive, Alpaca et Tiingo sont limités aux États-Unis en gratuit ou ne mentionnent pas le Canada.

### Cited Findings
| Fournisseur | TSX gratuit ? | Format / remarque | Source |
|---|---|---|---|
| yfinance | Oui (non officiel) | `RY.TO`. Usage personnel, 429 fréquents | [PyPI](https://pypi.org/project/yfinance/) ; [yfinance #2289](https://github.com/ranaroussi/yfinance/issues/2289) |
| Alpha Vantage | Oui | `SHOP.TRT`, `GPV.TRV`. 25 req/jour, `compact` = 100 points | [Docs AV](https://www.alphavantage.co/documentation/) ; [Premium](https://www.alphavantage.co/premium/) |
| EODHD | Probable (à tester) | Code `TO` (XTSE). Free = 20/jour, 1 an, personal use | [TD.TO](https://eodhd.com/financial-summary/TD.TO) ; [Pricing](https://eodhd.com/pricing) |
| Twelve Data | Non | Basic = « US (3) ». Add-on Cboe Canada dès 180 $/an | [llms-full](https://twelvedata.com/llms-full.txt) ; [Pricing](https://twelvedata.com/pricing) |
| Finnhub | Non (tiers) | Bougies premium, international payant | [Massive vs Finnhub](https://massive.com/compare/massive-vs-finnhub) |
| FMP | Non | « limited to US exchanges » | [FMP Pricing](https://site.financialmodelingprep.com/developer/docs/pricing) |
| Massive | Non (inférence) | Produit « Stocks » US. Aucune mention du TSX | [massive.com/pricing](https://massive.com/pricing) |
| Alpaca | Non | Actions US (IEX) seulement | [Alpaca docs](https://docs.alpaca.markets/docs/about-market-data-api) |
| Tiingo | Non mentionné | « US and Chinese stocks » | [Tiingo Pricing](https://www.tiingo.com/about/pricing) |
| Marketstack | Non confirmé | 100 req/mois, « 2700+ exchanges » | [Marketstack Pricing](https://marketstack.com/pricing) |
| Stooq | Non vérifié | Clé API requise depuis 2026 | [pandas-datareader #1012](https://github.com/pydata/pandas-datareader/issues/1012) |
| Questrade | Oui (compte requis) | Actions canadiennes et US, L1 et bougies | [Questrade developer](https://developer.questrade.com/) |
| Databento | Crédits 125 $ | TSX listé dans les venues | [Databento venues](https://databento.com/venues) |
| TMX Datalinx | Non (payant, essai 90 j) | Officiel, depuis 1998 | [TMX historical](https://tmxinfoservices.com/corporate-and-reference-data/historical-trading-data) |
| Google Finance | Affichage seulement | Pas d'historique via API ou Apps Script | [Google Help](https://support.google.com/docs/answer/3093281?hl=en) |

### Inferences
- Les FNB canadiens de l'univers (XIU.TO, XBB.TO, ZST.TO) suivent la même logique que les actions .TO. La couverture par EODHD et Alpha Vantage est plausible mais non testée.
- Conventions de clôture : EODHD met à jour les autres bourses 2 à 3 h après la clôture (NYSE et Nasdaq en moins de 15 min) ; les barres crypto et forex sont datées du jour UTC courant ([EODHD EOD API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)). Il faudra normaliser les fuseaux : clôture TSX et NYSE à 16 h ET, crypto en jour UTC.

### Gaps
- Aucun appel réel n'a été fait (pas de clés) pour confirmer RY.TO sur EODHD Free ou SHOP.TRT sur Alpha Vantage Free.
- La couverture TSX de Stooq et Marketstack en 2026 n'est pas confirmée.
- Le fuseau et la convention de clôture précis de yfinance et d'Alpha Vantage pour le TSX n'ont pas été vérifiés.

---

## 3. Opérations sur titres (dividendes, splits, changements de symbole)

### Takeaway
Massive (ex-Polygon) est le seul fournisseur gratuit qui livre les quatre dates d'un dividende (déclaration, ex-date, enregistrement, paiement), mais seulement pour les titres US et sur 2 ans. EODHD gratuit inclut dividendes et splits sur 1 an. Twelve Data ne renvoie que l'ex-date. Les changements de symbole sont mal couverts partout en gratuit.

### Cited Findings
- **Massive** : `GET /stocks/v1/dividends` renvoie `ex_dividend_date`, `declaration_date`, `record_date`, `pay_date`, `cash_amount`, `currency` (exemples : USD, CAD), `frequency`, `distribution_type`, `historical_adjustment_factor` et `split_adjusted_cash_amount`. « Included in all Stocks plans ». Basic = 2 ans (données depuis le 15 janvier 2000). — [Massive dividends](https://massive.com/docs/rest/stocks/corporate-actions/dividends.md)
- **Massive** : splits inclus dans tous les plans Stocks. Ticker Events (chronologie d'entité, dont les changements de symbole) existe, mais son inclusion dans Basic n'est pas confirmée. — [Massive splits](https://massive.com/docs/rest/stocks/corporate-actions/splits.md) ; [Microsoft connector Polygon](https://learn.microsoft.com/en-us/connectors/polygon)
- **EODHD** : dividendes et splits inclus dans Free (1 an). `adjusted_close` est « adjusted for both splits and dividends » et « recomputed, not stored » : un nouveau dividende modifie l'historique. `close` est « as traded — not adjusted », le volume ajusté des splits. OHLC ajustés des splits via `function=splitadjusted`. — [EODHD Pricing](https://eodhd.com/pricing) ; [EODHD EOD API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)
- **Twelve Data** : `dividends` renvoie l'ex-date, le montant et la fréquence, sans dates de déclaration, d'enregistrement ou de paiement. Un `dividends_calendar` existe aussi. — [Twelve Data dividends](https://twelvedata.com/docs/llms/fundamentals/dividends.md) ; [dividends calendar](https://twelvedata.com/docs/llms/fundamentals/dividends-calendar.md)
- **Alpaca** : l'API Corporate Actions Announcements couvre dividendes, fusions, scissions et splits passés et à venir. Selon le billet de lancement, les changements de symbole n'y figurent pas. La FAQ renvoie à l'Assets API pour les changements de symbole, mais la référence EU liste les « name changes » : les sources se contredisent. Les données peuvent arriver en retard après l'annonce. — [Alpaca blog](https://alpaca.markets/blog/introducing-corporate-actions-api-announcements/) ; [Alpaca support](https://alpaca.markets/support/what-are-corporate-action-announcements-and-how-can-i-access-them) ; [Alpaca EU reference](https://docs.alpaca.markets/eu/reference/corporateactions)
- **Alpha Vantage** : endpoints « Corporate Action » DIVIDENDS et SPLITS présents dans la table des matières. Un catalogue tiers décrit DIVIDENDS comme « historical and future (declared) dividend distributions ». Les champs n'ont pas pu être vérifiés (page de 819 000 caractères). — [Documentation AV](https://www.alphavantage.co/documentation/) ; [qveris (tiers)](https://www.qveris.ai/tools/alphavantage.dividends.list.v1.467a92c0)
- **Finnhub** : dividendes non accessibles en gratuit selon un test tiers. — [freeapisforyou (tiers)](https://www.freeapisforyou.in/api/finnhub)
- **yfinance** : dividendes et splits via `Ticker.actions`, `.dividends`, `.splits` (ex-date seulement, sans dates d'annonce). Ces noms d'attributs viennent de connaissances antérieures et n'ont pas été revérifiés dans la doc 1.8.0 durant cette session. — [README yfinance](https://raw.githubusercontent.com/ranaroussi/yfinance/main/README.md)

### Inferences
- Pour les titres canadiens, aucune source gratuite vérifiée ne fournit les dates de déclaration et d'enregistrement. EODHD Free (ex-date et montant, 1 an) ou yfinance (ex-date) seront probablement le maximum disponible. Les dates d'annonce devront venir des communiqués (SEDAR+, sites émetteurs), ce qui sort du périmètre de ces notes.
- L'ajustement recalculé d'EODHD impose de stocker les prix bruts et les facteurs, pas seulement `adjusted_close`, pour que la base de connaissances reste reproductible.

### Gaps
- Champs exacts des endpoints DIVIDENDS et SPLITS d'Alpha Vantage, et leur caractère gratuit ou premium.
- Couverture TSX des opérations sur titres chez EODHD Free et Alpha Vantage.
- Endpoint officiel de changement de symbole (FMP `symbol-change`, Massive Ticker Events) et palier requis : non vérifiés.

---

## 4. Crypto-actifs (prix, on-chain, sentiment)

### Takeaway
CoinGecko Demo reste la meilleure base gratuite (100 appels/min, 10 000 appels/mois, 1 an d'historique quotidien, attribution obligatoire, MCP officiel sans clé). Les API publiques d'échanges (Kraken, Coinbase) complètent sans clé. CoinDesk Data (ex-CryptoCompare) a supprimé son palier gratuit le 21 mai 2026, l'API v2 gratuite de CoinCap n'existe plus, et Binance renvoie 451 depuis les IP américaines (dont AWS US).

### Cited Findings
**CoinGecko**
- Demo : 0 $, sans carte, « a stable rate limit of 100 calls/min and a monthly cap of 10,000 calls ». 1 an d'historique quotidien et horaire, 1 jour en 5 min, pas d'historique à la minute. Plus de 60 endpoints, fraîcheur « from 60 sec ». « Attribution required » (« Data provided by CoinGecko »). La page ne précise pas de type de licence pour Demo. — [CoinGecko API Pricing](https://www.coingecko.com/en/api/pricing)
- Payants : Basic 35 $/mois (100 000 crédits, 300/min, 2 ans, licence commerciale) ; Analyst 129 $ (500 000 crédits, 13 ans) ; Lite 499 $ ; Pro 999 $. Dépassement facturé 0,0005 $ par appel. — [CoinGecko API Pricing](https://www.coingecko.com/en/api/pricing)
- MCP officiel : distant sans clé `https://mcp.api.coingecko.com/mcp` (limites partagées) ; Pro `https://mcp.pro-api.coingecko.com/mcp` avec clé ; local `@coingecko/coingecko-mcp` avec clé Demo ou Pro. Transports Streamable HTTP (`/mcp`) et SSE (`/sse`). — [CoinGecko MCP docs](https://docs.coingecko.com/ai-integration/mcp-server)

**CoinMarketCap**
- Basic gratuit : 15 000 crédits/mois, 50 req/min, plus de 60 endpoints. Historique : quotes intraday 1 mois, quotidiennes 1 an (tableau difficile à lire, à vérifier). FAQ : « Basic through Professional all include commercial use rights ». Attribution non mentionnée. — [CMC API Pricing](https://coinmarketcap.com/api/pricing/)
- Payants : Builder 29 $/mois (150 000 crédits, 300/min), Startup 79 $, Growth 299 $, Professional 699 $. — [CMC API Pricing](https://coinmarketcap.com/api/pricing/)

**CoinDesk Data (ex-CryptoCompare)**
- Billet du 17 avril 2026 : « As of May 21, 2026, we will be retiring our free API tier and accounts without a subscription will no longer have API access ». — [CoinDesk Data blog](https://data.coindesk.com/blogs/changes-to-coindesk-data-indices-api-free-tier-access)
- CoinDesk a acquis CCData en octobre 2024 et l'a renommé CoinDesk Data en février 2025. `min-api.cryptocompare.com` et `data-api` répondent 401 sans abonnement ; prix uniquement sur demande au service commercial. Sources tierces. — [CoinMarketCap Academy (concurrent)](https://coinmarketcap.com/api/resources/coindesk-api-alternatives-7-crypto-data-feeds-compared-in-2026) ; [CoinGecko learn (concurrent)](https://www.coingecko.com/learn/coindesk-api-alternatives)

**CoinPaprika**
- Free : « 20,000 calls a month per IP », 10 req/s, 1 an d'historique quotidien (OHLCV gratuit limité au dernier jour complet, horaire sur 24 h), 2 000 actifs. Usage personnel uniquement, crédit « Powered by CoinPaprika » obligatoire. Starter 99 $, Pro 199 $, Business 799 $/mois. — [CoinPaprika API Pricing](https://coinpaprika.com/api/pricing/)

**CoinCap**
- L'API v2 gratuite sans clé ne répond plus sur `api.coincap.io`. La v3 (`rest.coincap.io/v3`, docs sur pro.coincap.io) exige une clé (401 sans) et fonctionne au crédit. — [CoinPaprika, guide de migration (concurrent)](https://coinpaprika.com/education/migrating-from-coincap-api-to-coinpaprika/)
- Free : 500 crédits/mois, 5 req/min, REST seulement (source unique). — [splash.coincap.io](https://splash.coincap.io/)

**Binance**
- HTTP 451 (« Unavailable For Legal Reasons ») depuis les IP de juridictions restreintes, y compris des instances AWS EC2 aux États-Unis. Contournement pour le spot : `https://data-api.binance.vision` (données de marché seulement, sans clé), qui ne fonctionne pas pour les Futures. — [Binance dev forum](https://dev.binance.vision/t/api-error-451-unavailable-for-legal-reasons/13828) ; [Binance dev forum (futures)](https://dev.binance.vision/t/error-451-when-accessing-the-futures-api-from-us/16725) ; [logiover (tiers)](https://logiover.pages.dev/guides/binance-market-data-without-api-keys/)
- Binance a quitté le Canada en 2023 : positions à fermer avant le 30 septembre 2023, puis mode liquidation seule. — [BetaKit](https://betakit.com/binance-exits-canada-as-crypto-trading-platforms-feel-broader-impact-of-stricter-regulations/) ; [The Logic](https://thelogic.co/news/binance-to-exit-canada/)

**Kraken**
- Endpoints publics sans clé, limités par IP (et par paire pour Trades et OHLC). Aucun chiffre public, mais 1 appel/s reste dans les limites. OHLC : 720 bougies maximum par appel (environ 2 ans en quotidien). — [Kraken historical data](https://docs.kraken.com/exchange/guides/general/historical-data) ; [Kraken support](https://support.kraken.com/articles/206548367) ; [Kraken rate limits](https://docs.kraken.com/exchange/guides/rest/ratelimits)

**Coinbase**
- Advanced Trade : endpoints publics `https://api.coinbase.com/api/v3/brokerage/market/products…` sans authentification, environ 10 req/s par IP selon des tiers. Le changelog officiel indique un passage de 10 à 20 req/s en mai 2023 (portée incertaine, donc contradiction). WebSocket non authentifié : 8 messages/s par IP. Exchange API (ex-Pro) : 10 req/s, rafales à 15. — [apis.io (tiers)](https://apis.io/rate-limits/coinbase/coinbase-rate-limits/) ; [Advanced Trade changelog](https://docs.cloud.coinbase.com/advanced-trade/docs/changelog) ; [WS rate limits](https://docs.cloud.coinbase.com/advanced-trade/docs/ws-rate-limits) ; [Exchange rate limits](https://docs.cdp.coinbase.com/exchange/rest-api/rate-limits)

**On-chain, DeFi et sentiment**
- Glassnode : pas d'API gratuite, ou API dès 49 $/mois selon une autre source. Sources tierces contradictoires. — [spark.money](https://www.spark.money/tools/crypto-research-analytics-comparison) ; [costbench](https://costbench.com/software/onchain-analytics/glassnode/free-plan/)
- CryptoQuant : « Data API starts on a free plan, scales by credits » ; limites non publiées. — [cryptoquant.com/apis](https://cryptoquant.com/apis)
- Messari : palier gratuit avec clé et throttling à 200/min selon un tiers (non vérifié). — [spark.money (tiers)](https://www.spark.money/tools/crypto-api-pricing-comparison)
- DefiLlama : API gratuite `api.llama.fi`, majoritairement sans clé, sans quota officiel publié (un tiers avance environ 500 requêtes par 5 min). Pro : 1 000 req/min, jusqu'à 1 M d'appels/mois, clé dans l'URL `pro-api.llama.fi`. Prix incertain (300 $/mois contre un palier Supporter à 15 $). — [DefiLlama Pro API](https://defillama.com/pro-api) ; [docs.llama.fi Pro](https://docs.llama.fi/pro-api) ; [logiover (tiers)](https://logiover.pages.dev/guides/how-to-scrape-defillama-protocols-tvl-in-2026/)
- mempool.space : API gratuite sans authentification, limites non publiées (429 au-delà), offre Enterprise non plafonnée, projet AGPL-3.0 auto-hébergeable. — [mempool API intro (miroir)](https://www.mintlify.com/mempool/mempool/api/introduction) ; [mempool Enterprise](https://mempool.space/enterprise) ; [spark.money](https://www.spark.money/tools/bitcoin-api-comparison)
- Fear & Greed (alternative.me) : `https://api.alternative.me/fng/` répond sans clé. Au 15 novembre 2026 00:00 UTC, valeur 10, « Extreme Fear ». Aucune mention d'attribution dans le JSON. — [api.alternative.me/fng](https://api.alternative.me/fng/)

### Inferences
- Paire BTC/ETH recommandée pour A5 : CoinGecko Demo (via MCP sans clé ou REST avec clé) comme source principale, Kraken ou Coinbase public comme source de contrôle croisé. Binance est à éviter depuis AWS.
- Le palier gratuit de CoinMarketCap inclut des droits commerciaux (selon sa FAQ), ce qui en fait une alternative moins restrictive que CoinPaprika (usage personnel) pour une démo publique.
- Le départ de Binance du Canada et les 451 visant les IP restreintes laissent penser que les IP canadiennes (région AWS ca-central-1) peuvent aussi être bloquées. C'est une inférence non testée.

### Gaps
- Blockchain.com (charts et query API) : aucune donnée vérifiée.
- Exigence d'attribution d'alternative.me : non vérifiée sur la page de l'index.
- Quotas exacts du palier gratuit de Messari et CryptoQuant, et statut 2026 de Glassnode : sources tierces contradictoires.
- Conditions de licence et de redistribution de CoinMarketCap au-delà de la FAQ : non lues.

---

## 5. Licences, stockage et redistribution (exigences de traçabilité du brief)

### Takeaway
La plupart des paliers gratuits limitent l'usage au personnel ou à l'interne (Yahoo, Tiingo, EODHD, CoinPaprika). D'autres exigent une attribution visible (CoinGecko Demo, CoinPaprika). Twelve Data impose un plan Business à toute organisation. Seul CoinMarketCap Basic revendique explicitement des droits commerciaux. Pour une base de connaissances partagée, il faut stocker avec chaque donnée sa source, sa date d'extraction et sa licence.

### Cited Findings
- Yahoo / yfinance : « intended for personal use only » ; licence API Yahoo « personal… revocable ». — [PyPI yfinance](https://pypi.org/project/yfinance/) ; [Yahoo ToS, version antérieure](https://legal.yahoo.com/ie/en/yahoo/terms/otos/previousversion-2025-06-09/index.html)
- Tiingo : « Internal Use Only… for your own personal use » ; redistribution tarifée à part. — [Tiingo Pricing](https://www.tiingo.com/about/pricing)
- EODHD Free : « personal use » ; plans « Commercial / B2B » séparés. — [EODHD EOD API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes) ; [EODHD Pricing](https://eodhd.com/pricing)
- Massive : plans « Individual use only » sur la page de tarifs. — [massive.com/pricing](https://massive.com/pricing)
- Twelve Data : plan Business requis « even if the data is only used internally ». — [Twelve Data Business](https://twelvedata.com/pricing-business)
- CoinGecko Demo : « Attribution required ». Licence commerciale à partir de Basic (35 $). — [CoinGecko Pricing](https://www.coingecko.com/en/api/pricing)
- CoinMarketCap : « Basic through Professional all include commercial use rights ». — [CMC Pricing](https://coinmarketcap.com/api/pricing/)
- CoinPaprika Free : usage personnel, « Powered by CoinPaprika » requis. — [CoinPaprika Pricing](https://coinpaprika.com/api/pricing/)
- Google Finance : « solely for informational purposes, not for trading purposes ». — [Google Help](https://support.google.com/docs/answer/3093281?hl=en)
- TMX : prix pour « single end user », sans droits de redistribution. — [TMX Historical Market Data Online](https://tmxinfoservices.com/corporate-and-reference-data/historical-trading-data/tmx-historical-market-data-online-custom-queries)
- Alpha Vantage : les données temps réel et différées US sont réservées « for personal use » via Alpha X Terminal. — [Alpha Vantage Premium](https://www.alphavantage.co/premium/)
- mempool.space : code AGPL-3.0, auto-hébergeable. — [spark.money](https://www.spark.money/tools/bitcoin-api-comparison)

### Inferences
- Un datathon académique sponsorisé (BN et AWS) n'est probablement pas une « company » au sens de Twelve Data. Une démonstration publique à des juges pourrait en revanche dépasser « personal use » (Yahoo, Tiingo, EODHD Free, CoinPaprika). Mieux vaut le documenter comme risque et ne pas redistribuer les séries brutes ; on peut publier des dérivés agrégés ou des signaux.
- Champs minimaux recommandés par enregistrement dans la base OKF : `source_api`, `endpoint`, `retrieved_at` (UTC), `as_of` (date de marché et fuseau), `adjustment` (brut, split, split+dividende), `licence_url`, `attribution_text`, `redistribution` (oui/non/inconnu).

### Gaps
- Le texte actuel (2026) des conditions API Yahoo (`apiforydn`) n'a pas été récupéré.
- Les CGU d'Alpha Vantage (stockage et redistribution des données gratuites), de Finnhub, de Massive et de Marketstack n'ont pas été lues en détail.

---

## 6. SDK Python et serveurs MCP officiels

### Takeaway
Les serveurs MCP officiels confirmés sont Alpha Vantage (hébergé, clé gratuite), Massive (hébergé et open source, expérimental), CoinGecko (hébergé sans clé, ou Pro) et EODHD. Ils s'intègrent directement à un agent Strands, mais leurs quotas restent ceux du palier de la clé utilisée.

### Cited Findings
- Alpha Vantage MCP : `https://mcp.alphavantage.co/mcp?apikey=…`, avec des guides pour Claude, ChatGPT et OpenClaw. — [mcp.alphavantage.co](https://mcp.alphavantage.co/)
- Massive MCP : `massive-com/mcp_massive` (MIT, Python, « experimental »), hébergé sur `https://mcp.massive.com`. — [GitHub mcp_massive](https://github.com/massive-com/mcp_massive)
- CoinGecko MCP : distant sans clé, Pro, ou local `@coingecko/coingecko-mcp`. — [CoinGecko MCP docs](https://docs.coingecko.com/ai-integration/mcp-server)
- EODHD : « MCP Server For Financial Data by EODHD » (bandeau du site). — [EODHD exchange TO](https://eodhd.com/exchange/TO?page=27)
- SDK : `yfinance` (PyPI 1.8.0), `twelvedata-python` (officiel), SDK Python Alpaca (référence Corporate Actions). — [PyPI yfinance](https://pypi.org/project/yfinance/) ; [GitHub twelvedata-python](https://www.github.com/twelvedata/twelvedata-python) ; [Alpaca Python SDK](https://alpaca.markets/sdks/python/api_reference/trading/corporate-actions.html)
- Le MCP communautaire `calvernaz/alphavantage` (uvx, `ALPHAVANTAGE_API_KEY`) n'est pas le serveur officiel hébergé. — [jsDelivr README calvernaz](https://cdn.jsdelivr.net/gh/calvernaz/alphavantage@main/README.md)
- `@cyanheads/coingecko-mcp-server` est un serveur tiers non affilié. — [CoinGecko MCP docs](https://docs.coingecko.com/ai-integration/mcp-server.md)

### Inferences
- Pour A5, le MCP CoinGecko sans clé consomme des « limites partagées » : il est fragile pour une démo. Mieux vaut une clé Demo personnelle.
- Le MCP Alpha Vantage avec une clé gratuite reste plafonné à 25 requêtes/jour, ce qui est insuffisant pour une boucle agentique. Il faut l'utiliser derrière un cache.

### Gaps
- Le caractère officiel des MCP de Twelve Data, Financial Datasets, FMP, Finnhub, Alpaca et CoinMarketCap n'a pas été vérifié durant cette session.
- La version précise et les outils exposés par `mcp_massive` en novembre 2026 ne sont pas connus (une installation mentionne v0.10.0).

---

## 7. Pièges 2025–2026 (réductions de paliers, blocages, acquisitions)

### Takeaway
2025–2026 a été une période de fermetures et de restrictions : fin du gratuit chez CoinDesk Data, clé obligatoire chez Stooq, disparition de CoinCap v2, renommage de Polygon en Massive, persistance des 429 Yahoo depuis le cloud et 451 Binance depuis les États-Unis. Une architecture multi-sources avec cache local s'impose.

### Cited Findings
- CoinDesk Data : palier gratuit retiré le 21 mai 2026. — [CoinDesk Data blog](https://data.coindesk.com/blogs/changes-to-coindesk-data-indices-api-free-tier-access)
- Stooq : clé API requise depuis mars ou avril 2026 ; lecteur retiré de pandas-datareader 0.11.0 en juin 2026. — [pandas-datareader #1012](https://github.com/pydata/pandas-datareader/issues/1012) ; [FXMacroData](https://fxmacrodata.com/articles/fxmacrodata-vs-stooq)
- CoinCap : v2 gratuite hors service, v3 avec clé et quota de 500 crédits/mois. — [CoinPaprika migration guide](https://coinpaprika.com/education/migrating-from-coincap-api-to-coinpaprika/) ; [splash.coincap.io](https://splash.coincap.io/)
- Polygon.io devenu Massive (30 octobre 2025 selon un communiqué ; dates contradictoires ailleurs). — [apicostcalc](https://apicostcalc.com/blog/polygon-massive-rebrand-api-pricing.html)
- IEX Cloud fermé le 31 août 2024. — [WatersTechnology](https://waterstechnology.com/data-management/7951882/iex-cloud-closure-forces-fintech-clients-to-seek-data-alternatives)
- Yahoo : 429 et `YFRateLimitError` toujours rapportés en 2026, avec des blocages plus marqués depuis AWS et les IP cloud partagées. — [TradingAgents #1386](https://github.com/TauricResearch/TradingAgents/issues/1386) ; [PythonAnywhere](https://www.pythonanywhere.com/forums/topic/36371/)
- Binance : 451 depuis les IP américaines et AWS US ; sortie du Canada en 2023. — [Binance dev forum](https://dev.binance.vision/t/api-error-451-unavailable-for-legal-reasons/13828) ; [BetaKit](https://betakit.com/binance-exits-canada-as-crypto-trading-platforms-feel-broader-impact-of-stricter-regulations/)
- Alpha Vantage : 25 requêtes/jour, historique complet réservé au premium. — [Alpha Vantage Premium](https://www.alphavantage.co/premium/) ; [Documentation](https://www.alphavantage.co/documentation/)
- Twelve Data : chiffres incohérents sur sa propre page de tarifs. — [Twelve Data Pricing](https://twelvedata.com/pricing)
- CoinGecko Demo : limite à 100 appels/min selon la page de tarifs de novembre 2026, alors que des sources plus anciennes citaient 30/min. Le plafond de 10 000 appels/mois reste le facteur limitant. — [CoinGecko Pricing](https://www.coingecko.com/en/api/pricing)

### Inferences
- Il faut un cache local horodaté (Parquet ou S3) alimenté hors ligne pour l'historique (yfinance en local, EODHD, Tiingo pour les US), et réserver les appels en direct de A5 aux mises à jour incrémentales via des API à clé.
- Avec un quota mensuel plutôt que journalier (CoinGecko 10 000/mois, CMC 15 000/mois, Marketstack 100/mois), il faut budgéter les appels sur toute la durée du datathon.
- Il faut distinguer `YFRateLimitError` d'un symbole introuvable dans le code de A5, comme le recommande l'issue TradingAgents.

### Gaps
- Aucune annonce officielle de Yahoo sur le blocage des IP cloud n'a été trouvée : seulement des rapports communautaires.
- Date officielle de mise en place de la clé Stooq : sources communautaires seulement (mars contre avril 2026).
- Les changements de paliers gratuits en 2026 chez Finnhub, FMP et Marketstack n'ont pas été vérifiés.
