# Sources de nouvelles, communications de banques centrales et décisions politiques/réglementaires (APIs et fils gratuits, état au 14-15 novembre 2026)

> Périmètre : agent A4 (spécialiste presse) d'AlphaForge AI → base de connaissances OKF (Markdown + YAML) supervisée par A6. Pour chaque source : URL de base, auth, quotas, profondeur, langues (FR), champs de date, licence (stockage / citation / redistribution). Mention « vérifié (curl) » = la requête a été exécutée le 2026-11-14/15 (UTC) depuis l'environnement de recherche et a renvoyé le statut et la date indiqués. Tarifs en USD sauf mention contraire.

## 1. APIs de nouvelles généralistes (GDELT, NewsAPI.org, GNews, NewsData.io, Mediastack, Currents, TheNewsAPI, World News API, Event Registry/NewsAPI.ai, Common Crawl News)

### Takeaway
GDELT est la seule source généraliste à la fois gratuite, sans clé, commerciale et redistribuable (avec citation), mais elle fournit des URL et des métadonnées, pas le texte intégral. Les offres gratuites des agrégateurs commerciaux sont presque toutes limitées à un usage « dev/test/non commercial », avec un délai de 12 à 24 h et un contenu tronqué. Pour A4, il faut stocker **titre + extrait court + URL + dates**, jamais le texte intégral.

### Cited Findings

**GDELT (DOC 2.0 API, Events/Mentions/GKG 2.0, BigQuery)**
- URL de base de DOC 2.0 : `https://api.gdeltproject.org/api/v2/doc/doc`. Opérateurs disponibles : `domain:`, `domainis:`, `sourcecountry:`, `sourcelang:`, `theme:`, `tone`, `near`, `repeat`. Modes : ArtList, TimelineVol, TimelineTone, TimelineLang, TimelineSourceCountry, ToneChart, etc. Formats : HTML, CSV, RSS, JSON, JSONFeed — [GDELT DOC 2.0 API debuts](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
- 75 résultats par défaut, 250 au maximum (`maxrecords`). L'API « searches a rolling window of the last 3 months of coverage ». `STARTDATETIME`/`ENDDATETIME` au format YYYYMMDDHHMMSS, qui doivent tomber dans ces 3 mois. `timespan` d'au moins 15 min — [GDELT DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
- 65 langues sont traduites automatiquement et l'on cherche en anglais sur toutes. `sourcelang:french` ou un code à 3 lettres est accepté — [GDELT DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
- Limite d'usage observée (vérifié par curl le 2026-11-15) : l'API répond « Please limit requests to one every 5 seconds… All high-traffic users should switch to our ngrams dataset ». Ce message est arrivé dès la première requête depuis notre IP — [api.gdeltproject.org](https://api.gdeltproject.org/api/v2/doc/doc?query=%22Bank%20of%20Canada%22&mode=artlist&format=json)
- Événements et GKG 2.0 : « the data updates every 15 minutes », 65 langues traduites en direct. « all GDELT datasets are available in Google BigQuery, with live datasets updated every 15 minutes » — [GDELT Data](https://www.gdeltproject.org/data.html)
- Le flux est actif. `lastupdate.txt` pointait le 2026-11-15 vers `20261115004500.export.CSV.zip`, `.mentions.CSV.zip` et `.gkg.csv.zip` (vérifié par curl) — [lastupdate.txt](https://data.gdeltproject.org/gdeltv2/lastupdate.txt)
- **Licence** : « available for unlimited and unrestricted use for any academic, commercial, or governmental use of any kind without fee ». En contrepartie, « any use or redistribution of the data must include a citation to the GDELT Project and a link to this website » — [GDELT About](https://www.gdeltproject.org/about.html)
- BigQuery sandbox : utilisable sans carte de crédit, avec « 1 TiB of processed query data each month ». Stockage plafonné à « lifetime limit of 10 GiB ». Les tables expirent après 60 jours. Pas de DML ni de streaming — [BigQuery sandbox](https://docs.cloud.google.com/bigquery/docs/sandbox)

**NewsAPI.org**
- Plan Developer gratuit : 100 requêtes/jour, « Articles have a 24 hour delay », recherche limitée aux articles d'un mois au plus, CORS restreint à localhost. Le plan « cannot be used in a staging or production environment (including internally) ». Premier palier payant, Business : 449 $/mois pour 250 000 requêtes, puis 0,0018 $ par requête supplémentaire. Il donne le temps réel et 5 ans d'historique — [NewsAPI pricing](https://newsapi.org/pricing)
- Les CGU précisent : « The Developer plan may be used for development and testing in a development environment only ». Il est interdit d'utiliser le service pour « reproduce or republish copyrighted material ». Publier les données requiert une autorisation expresse — [NewsAPI terms](https://newsapi.org/terms)
- `/v2/everything` accepte `language` (ar, de, en, es, **fr**, he, it, nl, no, pt, ru, sv, ud, zh), `from`/`to` en ISO 8601, `pageSize` jusqu'à 100. Champs renvoyés : `source{id,name}`, `author`, `title`, `description`, `url`, `urlToImage`, `publishedAt` (UTC), `content` « truncated to 200 chars » — [NewsAPI docs everything](https://newsapi.org/docs/endpoints/everything)

**GNews (gnews.io)**
- Plan gratuit à 0 € : 100 requêtes/jour, 10 articles par requête, 30 jours d'historique, « 12-hour delay », « Content cut to 250 characters ». Il est réservé à un usage « personal, academic, evaluation, and other non-commercial ». Plan Essential : 49,99 €/mois, 1 000 requêtes/jour, temps réel, historique depuis 2020, texte intégral, usage commercial — [GNews pricing](https://gnews.io/pricing)
- Couverture : 41 langues et 71 pays. Les top headlines suivent « Google News rankings ». La documentation annonce « Up to 100 » articles par requête sur les plans payants, alors que la page tarifs indique 25 pour Essential (incohérence à signaler) — [GNews docs](https://docs.gnews.io/) ; [GNews pricing](https://gnews.io/pricing)
- CGU : « Reasonable caching of API responses for application performance is permitted ». L'attribution est « appreciated but not required ». Il est interdit de « Redistribute, resell, or sublicense access to the API ». Le contenu tiers appartient aux ayants droit. Après la fin d'un abonnement payant, on n'est pas obligé de supprimer les données, sauf résiliation pour faute — [GNews terms](https://gnews.io/terms)

**NewsData.io**
- Plan gratuit : 200 crédits/jour, 1 à 10 articles par crédit, « Access to past 48 hours », « Data delayed by 12 hours », réservé au « testing & personal projects ». Les tags IA et le sentiment sont inclus. Un appel à l'Archive coûte 5 crédits. Le prix du plan Basic est **vide** sur la page, qui affiche aussi des valeurs « undefined » — [NewsData pricing](https://newsdata.io/pricing)
- CGU : l'attribution est obligatoire, sous la forme « Powered by NewsData.io API » avec un lien. La licence API couvre « personal or internal business purposes ». Le contenu tiers « remains the sole property of those who make it available » — [NewsData terms](https://newsdata.io/terms)

**Mediastack**
- Gratuit : 100 appels/mois, « Delayed News Data », « Non-Commercial Use ». Standard : 24,99 $/mois (22,99 $ en annuel), 10 000 appels, données en direct, historique, usage commercial — [Mediastack pricing](https://mediastack.com/pricing)

**Currents API**
- Gratuit : 250 requêtes/jour, 30 jours d'historique, 7 jours maximum par recherche, 34 langues. La page affirme que « every self-service plan, including Free, allows commercial use with attribution and a link to the original article », mais que « AI summaries or republication of article text need separate terms ». Builder : 69 $/mois, 2 500 requêtes/jour, 6 mois d'historique. Page mise à jour le 2026-10-27 — [Currents pricing](https://currentsapi.services/en/product/price)

**TheNewsAPI**
- Gratuit : 100 requêtes/jour, **3 articles par requête**. Basic : 19 $/mois (16 $ en annuel), 2 500 requêtes/jour, 25 articles par requête. La profondeur de l'historique, le texte intégral et l'usage commercial ne sont pas précisés — [TheNewsAPI pricing](https://www.thenewsapi.com/pricing). La page `/terms` renvoie une 404 — [thenewsapi.com/terms](https://www.thenewsapi.com/terms)

**World News API (worldnewsapi.com)**
- Gratuit : 50 points/jour, 1 requête/s, 1 mois d'historique, « Backlink Required ». Reporter : 39 $/mois, 500 points/jour, historique « Unlimited » selon le tableau mais depuis le « 1st of January 2022 » selon la FAQ (contradiction interne) — [World News API pricing](https://worldnewsapi.com/pricing/)
- CGU : cache de **1 h maximum**, et seulement avec une autorisation écrite. Revente interdite. Pas de stockage de données dérivées, même « hashed, or transformed ». Les droits restent aux propriétaires des contenus. La clause de backlink renvoie par erreur à « our food API page », copiée d'un autre produit — [World News API terms](https://worldnewsapi.com/terms/)

**Event Registry / NewsAPI.ai**
- Gratuit : 2 000 recherches, sans carte de crédit. Premier plan payant, « 5K » : 90 $/mois, avec « articles since 2014 ». Plus de 50 langues, contenu intégral (« Full content ») et sentiment sont listés dans « Included in every package » — [NewsAPI.ai plans](https://newsapi.ai/plans)
- CGU : « Free access is intended solely for evaluation and testing ». Le client peut « Store the data you retrieve in your own systems ». Il est interdit de redistribuer le contenu « without the appropriate rights ». L'affichage autorisé se limite aux « headlines, short excerpts, the source name ». « Articles and images belong to their publishers », y compris pour le traitement IA — [NewsAPI.ai terms](https://newsapi.ai/terms)

**Common Crawl News (CC-NEWS)**
- Fichiers WARC publiés « on a daily basis » depuis 2016, dans `s3://commoncrawl/crawl-data/CC-NEWS/` — [Common Crawl news dataset](https://commoncrawl.org/blog/news-dataset-available)
- CGU : aucun droit n'est accordé sur le contenu crawlé (« sole responsibility of the individual or entity from which such Crawled Content originated »). L'utilisateur s'engage à « respect the copyrights ». Il doit indemniser Common Crawl en cas d'usage en « artificial intelligence, machine learning » — [Common Crawl terms](https://commoncrawl.org/terms-of-use)

### Inferences
- Pour la base OKF : GDELT est la seule source qui autorise explicitement la redistribution, mais elle porte sur ses **métadonnées** (URL, titre, date de détection, ton, thèmes). Le texte des articles reste sous droit d'auteur des éditeurs. On peut donc stocker et citer un titre, une URL et un extrait bref avec citation de GDELT, mais pas le corps de l'article.
- Le plan gratuit NewsAPI.org est techniquement inutilisable pour une démo jugée en « production » (datathon), à cause de la clause dev-only et du délai de 24 h. GNews gratuit (12 h de délai, 250 caractères, non commercial) et Currents (commercial avec attribution) sont plus défendables dans un contexte académique.
- La fenêtre glissante de 3 mois de DOC 2.0 oblige à **archiver soi-même** les résultats au fil de l'eau (ou à utiliser BigQuery ou les fichiers bruts 15 min) pour des backtests plus longs.
- Sur la langue française : GDELT (`sourcelang:french`, `sourcecountry:CA`), NewsAPI (`language=fr`), GNews, Marketaux (`language=fr`) et Event Registry la couvrent. La qualité de couverture des médias québécois n'a pas été mesurée.

### Gaps
- Le schéma JSON exact d'ArtList (noms des champs `seendate`, `domain`, `language`, `sourcecountry`) n'est pas documenté dans le billet de 2017. Notre test JSON a été bloqué par la limite de débit, il faut le confirmer par un appel réel. Point clé : `seendate` est la date de détection par GDELT, pas la date de publication. C'est une connaissance antérieure, non revérifiée ici.
- NewsData.io : le prix du plan Basic n'est pas affiché (page cassée ou dynamique).
- TheNewsAPI et Mediastack : CGU non récupérées (404 pour TheNewsAPI, page non consultée pour Mediastack).
- Event Registry : la profondeur d'historique exacte du plan gratuit n'est pas indiquée (probablement 30 jours, non confirmé).

## 2. APIs de nouvelles financières (Marketaux, Finnhub, Alpha Vantage NEWS_SENTIMENT, Massive ex-Polygon, Benzinga/Alpaca, Tiingo)

### Takeaway
Marketaux (entités et sentiment, `countries=ca`, `language=fr`) et Finnhub company-news (1 an d'historique gratuit, Amérique du Nord) sont les meilleures options gratuites à étiquetage par ticker. **Alpha Vantage NEWS_SENTIMENT est désormais marqué « Premium »** dans la documentation, alors qu'il était gratuit auparavant. Toutes ces sources interdisent la redistribution : utilisation interne seulement, avec citation de l'URL d'origine.

### Cited Findings

**Marketaux**
- Gratuit : 100 requêtes/jour, **3 articles par requête**. Basic : 29 $/mois (24 $/mois en annuel), 2 500 requêtes/jour, 20 articles par requête. L'historique et l'usage commercial ne sont pas précisés — [Marketaux pricing](https://www.marketaux.com/pricing)
- `GET https://api.marketaux.com/v1/news/all?api_token=…`. Paramètres : `symbols`, `countries` (ex. `us,ca`), `language` (dont `fr`), `published_after`/`published_before`, `filter_entities`, `must_have_entities`. Champs : `published_at`, `source` (domaine), `url`, `title`, `description`, `snippet` (« A short snippet of the article body »), `entities[].sentiment_score`, `highlights[]` avec `sentiment`. Pas de texte intégral. Ensemble de résultats limité à 20 000 — [Marketaux documentation](https://www.marketaux.com/documentation)
- Les CGU sont introuvables : `/terms`, `/terms-and-conditions` et `/legal` renvoient des 404 (vérifié par curl), et la page d'accueil ne lie que la politique de confidentialité — [marketaux.com/privacy](https://www.marketaux.com/privacy)

**Finnhub**
- `/company-news` : « List latest company news by symbol. This endpoint is only available for North American companies ». Palier gratuit : « 1 year of historical news and new updates ». `/news?category=general` donne les nouvelles de marché — [Finnhub docs company-news](https://finnhub.io/docs/api/company-news) (texte extrait du JSON embarqué dans la page)
- Le plan gratuit est annoncé à 60 appels/minute (source secondaire, la page de tarifs étant rendue en JS) — [Finnhub pricing (via recherche)](https://finnhub.io/pricing) ; [NexusFi](https://nexusfi.com/d/data-providers/finnhub/)
- CGU : « You hereby agree to not redistribute or share access to data or derived results from the data obtained from Finnhub with anyone or any 3rd party without written approval ». « All plan listed on Finnhub website is strictly for personal use unless explicitly stated otherwise. Personal plan can't be used by any business even internally » — [Finnhub terms](https://finnhub.io/terms-of-service)

**Alpha Vantage NEWS_SENTIMENT**
- La section porte le libellé « Market News & Sentiment Trending **Premium** », avec la mention « Tip: this is a premium API function. Subscribe to a premium membership plan to instantly unlock all premium APIs » (vérifié par curl le 2026-11-14) — [Alpha Vantage docs](https://www.alphavantage.co/documentation/#news-sentiment)
- Paramètres : `tickers` (ex. `COIN,CRYPTO:BTC,FOREX:USD`), `topics` (`economy_monetary`, `economy_fiscal`, `economy_macro`, `financial_markets`, `earnings`, `ipo`, `mergers_and_acquisitions`…), `time_from`/`time_to` au format YYYYMMDDTHHMM, `sort` (LATEST, EARLIEST, RELEVANCE), `limit` 50 par défaut et 1000 au maximum — [Alpha Vantage docs](https://www.alphavantage.co/documentation/#news-sentiment)
- Clé gratuite : 25 requêtes/jour. Premium à partir de 49,99 $/mois (75 requêtes/min). Un serveur MCP officiel Alpha Vantage existe — [Alpha Vantage support](https://www.alphavantage.co/support/) ; [Alpha Vantage premium](https://www.alphavantage.co/premium/)

**Massive (ex-Polygon.io)**
- `GET /v2/reference/news` : `ticker`, `published_utc.gte/.lte` (RFC 3339), `limit` jusqu'à 1000. Champs : `published_utc`, `article_url`, `publisher`, `description`, `insights[].sentiment` et `sentiment_reasoning`. Inclus dans tous les plans Stocks, « including Stocks Basic ». Mise à jour horaire. Données depuis le 22 juin 2016, avec **2 ans** d'historique pour Basic — [Massive news docs](https://massive.com/docs/rest/stocks/news)
- Le plan Basic gratuit serait limité à 5 requêtes/min. `api.polygon.io` et `api.massive.com` coexisteraient avec les mêmes clés (source secondaire, non confirmé sur la page officielle) — [QVeris guide](https://qveris.ai/guides/polygon-pricing-optimized/)
- La page tarifs ne montre pas de plan gratuit. Les produits individuels sont marqués « Individual use only » (Stocks Advanced à 199 $/mois) — [Massive pricing](https://massive.com/pricing)

**Benzinga / Alpaca**
- Benzinga « Basic News API » est en palier gratuit sur AWS Marketplace : titre, accroche (« body teaser ») et lien vers benzinga.com. Le corps intégral est réservé aux paliers payants — [AWS Marketplace Benzinga](https://aws.amazon.com/marketplace/pp/prodview-xwgvhwowjmw3g)
- Alpaca News : `https://data.alpaca.markets/v1beta1/news`, avec `start`/`end` (RFC 3339), `symbols`, `limit` de 1 à 50, `include_content`, `sort` sur la date de mise à jour. Champs : `created_at`, `updated_at`, `headline`, `author`, `summary`, `content` (HTML, peut être vide), `url`, `source`. Les exemples montrent les sources « benzinga » et « fiscal.ai ». Sans accès temps réel, `end` vaut par défaut « 15 minutes before the current time » — [Alpaca news reference](https://docs.alpaca.markets/us/reference/news-3)

**Tiingo News**
- `https://api.tiingo.com/tiingo/news?tickers=…`. Champs : `publishedDate` (« Tiingo may substitute its crawl time if the source lacks a date »), `crawlDate`, `title`, `description`, `url`, `source`, `tickers`, `tags` — [Tiingo news docs](https://www.tiingo.com/documentation/news)
- Starter gratuit : 50 requêtes/h, 1 000/jour, 500 symboles par mois. Power : 30 $/mois (50 $ pour un usage commercial interne). « News API allows 3 Months of queryable history ». La licence est « Internal Use Only » (« you may not display or share the data ») — [Tiingo pricing](https://www.tiingo.com/about/pricing)

### Inferences
- Pour l'agent A4, le couple **Marketaux (sentiment par entité) + Finnhub company-news (historique d'un an)** couvre bien les actions CA/US. Les clauses « personal use » de Finnhub et « internal use » de Tiingo rendent toutefois la diffusion d'une démo publique risquée. Il faut afficher titre + lien, jamais le texte, et prévoir une demande d'autorisation si la démo devient publique.
- Le passage d'Alpha Vantage NEWS_SENTIMENT en Premium casse beaucoup de tutoriels FinBERT et LLM antérieurs à 2026. À signaler comme piège.
- Benzinga gratuit (via AWS Marketplace) cadre bien avec un projet AWS (datathon BN + AWS), mais il ne donne qu'un titre, une accroche et un lien.

### Gaps
- Finnhub : prix du premier palier payant incluant les nouvelles non trouvé (page JS).
- Marketaux : profondeur d'historique gratuite et CGU de stockage et redistribution introuvables.
- Tiingo : le tableau ne permet pas de savoir si la News API est incluse dans le plan gratuit (cases illisibles).
- Alpaca : conditions d'accès gratuit à la news et profondeur historique non confirmées sur la page consultée.
- Massive : existence et quotas exacts du plan gratuit « Stocks Basic » non confirmés sur la page officielle.

## 3. Agrégateurs et sources sociales (Google News RSS, Yahoo Finance RSS, Reddit, Hacker News, Stocktwits, X/Twitter)

### Takeaway
Google News RSS et Yahoo Finance RSS fonctionnent encore en novembre 2026, mais leurs conditions limitent l'usage au personnel et non commercial. Reddit a fermé l'accès libre à son API le 11 novembre 2025. X est passé au paiement à l'usage en février 2026. Stocktwits interdit le scraping. Hacker News reste ouvert mais n'a guère d'intérêt pour la finance canadienne.

### Cited Findings
- **Google News RSS** fonctionne (vérifié par curl, HTTP 200, éléments datés du 2026-11-10) avec `https://news.google.com/rss/search?q=…&hl=fr-CA&gl=CA&ceid=CA:fr` — [Google News RSS](https://news.google.com/rss/search?q=Banque+du+Canada&hl=fr-CA&gl=CA&ceid=CA:fr)
- Les conditions Google News (version ancienne) n'autorisent l'affichage que « for your own personal use (i.e., non-commercial use) ». Les flux doivent être attribués à Google News et à chaque éditeur — [Google News Terms](https://www.google.com/intl/en_us/terms_google_news.html) ; [Search Engine Journal](https://www.searchenginejournal.com/google-news-offers-rss-and-atom-feeds/2022)
- **Yahoo Finance RSS** fonctionne (vérifié par curl, HTTP 200, élément du 2026-11-14) avec `https://feeds.finance.yahoo.com/rss/2.0/headline?s=RY.TO&region=CA&lang=en-CA` — [Yahoo Finance RSS](https://feeds.finance.yahoo.com/rss/2.0/headline?s=RY.TO&region=CA&lang=en-CA)
- Les conditions des API Yahoo interdisent de « derive income from the use or provision of the Yahoo APIs » sans permission écrite et imposent l'« Attribution Policy ». Yahoo « may terminate the license at any time » — [Yahoo API Terms](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html)
- **Reddit** : la « Responsible Builder Policy » du 11 novembre 2025 a mis fin à l'accès libre : « self-service access to Reddit's public data API will be closed ». Tout développeur ou chercheur doit désormais demander une approbation, avec un délai visé de 7 jours — [r/redditdev (miroir)](https://r.datuan.dev/r/redditdev/s/gquSJqMgrM)
- Le palier gratuit resterait à 100 requêtes/min par client OAuth, en usage non commercial approuvé (sources secondaires dont les chiffres se contredisent) — [data365](https://data365.co/blog/reddit-api-pricing) ; [Techloy](https://www.techloy.com/reddit-api-pricing-in-2026-complete-guide-for-developers-and-businesses/)
- Le JSON public non authentifié `reddit.com/r/…/new.json` renvoie une 403 (vérifié par curl le 2026-11-15) — [reddit.com](https://www.reddit.com/r/CanadianInvestor/new.json?limit=1)
- **Hacker News** : `https://hacker-news.firebaseio.com/v0/`, sans authentification, « There is currently no rate limit ». Le champ `time` est un horodatage Unix. Le dépôt est sous licence MIT — [HackerNews/API](https://github.com/HackerNews/API)
- **Stocktwits** : les CGU révisées le 10 juillet 2026 interdisent tout accès « Automated, or Scraping » sans autorisation écrite ou API approuvée — [Stocktwits terms](https://stocktwits.com/terms). L'accès à l'API a été restreint au fil du temps — [API Evangelist](https://providers.apievangelist.com/providers/stocktwits/)
- **X/Twitter** : le paiement à l'usage est devenu la règle le 6 février 2026. Le palier gratuit est de fait supprimé, réservé à des apps d'utilité publique approuvées au cas par cas. Le Basic à 200 $/mois est fermé aux nouveaux inscrits (sources secondaires) — [Roboin](https://roboin.io/article/en/2026/02/08/x-transitions-api-to-pay-per-use-model-ending-free-plan/) ; [Gigazine](https://gigazine.net/gsc_news/en/20260209-x-api-pay-per-use) ; [Postproxy](https://postproxy.dev/blog/x-api-pricing-2026)

### Inferences
- Il faut exclure X, Reddit et Stocktwits du MVP : approbation, coût et CGU anti-scraping. Si le jury exige du « sentiment social », la voie la plus sûre est un jeu de données Hugging Face sous licence (section 7).
- Google News RSS peut servir de **découverte d'URL** en français canadien (`hl=fr-CA&gl=CA`). On stocke seulement le titre, l'éditeur, l'URL et `pubDate`, et l'on cite l'éditeur d'origine.

### Gaps
- Le texte actuel (2026) des conditions Google News n'a pas été trouvé : la page citée est une version ancienne (« Google, Inc. »).
- Les prix officiels de X (docs.x.com) n'ont pas été consultés directement. Les montants par lecture varient selon les sources.
- La date de fin du palier gratuit Reddit (« mars 2027 ») n'est rapportée que par des tiers, non confirmée.

## 4. Sources canadiennes : médias et communiqués (CBC/Radio-Canada, La Presse, Globe and Mail, Financial Post, Cision/Newswire.ca, GlobeNewswire, TMX)

### Takeaway
Les fils RSS de CBC, Radio-Canada, La Presse, Globe and Mail et Newswire.ca sont actifs. Radio-Canada et le Globe limitent explicitement l'usage au personnel et non commercial. Financial Post n'expose pas de RSS public trouvable, et GlobeNewswire bloque les clients automatisés. Les communiqués d'entreprise (Newswire.ca/Cision) constituent la meilleure source « événement daté » pour les titres TSX.

### Cited Findings
- **CBC** : flux Business RSS actif (vérifié par curl, élément du 2026-11-14) à `https://www.cbc.ca/webfeed/rss/rss-business` — [CBC business RSS](https://www.cbc.ca/webfeed/rss/rss-business). La page de conditions RSS renvoie une 403 aux clients automatisés — [cbc.ca/rss](https://www.cbc.ca/rss/) ; [CBC using RSS](https://www.cbc.ca/rss/usingrss)
- **Radio-Canada** : flux `/info/rss/info/economie/en-continu`, `/politique/en-continu`, `/international/en-continu` et `/info/rss/info/en-continu`. Les conditions encouragent un usage « à titre personnel seulement ». Un usage commercial exige de contacter distribution@radio-canada.ca. Radio-Canada peut exiger le retrait — [Radio-Canada RSS](https://ici.radio-canada.ca/rss)
- Le flux économie est actif (vérifié par curl, élément du 2026-11-15) — [Radio-Canada économie](https://ici.radio-canada.ca/info/rss/info/economie/en-continu)
- **La Presse** : `https://www.lapresse.ca/affaires/rss` est actif (vérifié par curl, élément du 2026-11-14) — [La Presse Affaires RSS](https://www.lapresse.ca/affaires/rss). La page des fils RSS et des conditions renvoie une 403 — [lapresse.ca/fils-rss](https://www.lapresse.ca/fils-rss/)
- **Globe and Mail** : `https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/` est actif (vérifié par curl, éléments du 2026-11-14) — [Globe business RSS](https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/)
- Une page d'aide archivée de 2006 indiquait des flux réservés à un « personal use in an RSS reader or as part of a non-commercial website », avec attribution — [BAC archive 2006](https://bac-lac.wayback.archive-it.org/web/20061121064628/http://www.theglobeandmail.com/help). La page actuelle « Licensing and Permissions » permet de reprendre le titre avec un lien vers l'article, à titre non commercial — [Globe Licensing](https://www.theglobeandmail.com/privacy-terms/licensing-and-permissions/)
- **Financial Post** : `https://financialpost.com/feed` et `/category/news/feed` redirigent vers des pages HTML (vérifié par curl). Aucun RSS public n'a été trouvé — [financialpost.com](https://financialpost.com/)
- **Cision / Canada Newswire** : `https://www.newswire.ca/rss/news-releases-list.rss` est actif (vérifié par curl, élément du 2026-11-15) — [Newswire.ca RSS](https://www.newswire.ca/rss/news-releases-list.rss). La version française `/fr/rss/news-releases-list.rss` renvoie une 404, et `/terms-of-use/` aussi — [newswire.ca](https://www.newswire.ca/terms-of-use/)
- **GlobeNewswire** : `RssFeed/country/Canada` renvoie une 403 au client de recherche (vérifié par curl) — [GlobeNewswire RSS](https://www.globenewswire.com/RssFeed/country/Canada). La page média annonce des flux RSS/ATOM personnalisés par sujet, secteur, lieu ou bourse, livrés « with a GlobeNewswire subscription or via our specialized content providers » — [GlobeNewswire Media Relations](https://www.globenewswire.com/home/about/media-relations)

### Inferences
- Les communiqués de presse sont écrits pour être diffusés. Les citer avec un lien présente donc un risque juridique plus faible que citer un article de presse, mais les CGU des diffuseurs n'ont pas pu être lues. Par prudence, on stocke titre, date, URL et émetteur, plus un résumé maison.
- Pour la couverture francophone, Radio-Canada économie et La Presse Affaires sont les deux fils actifs vérifiés. Usage personnel ou non commercial seulement, donc ils conviennent pour un prototype de datathon, pas pour une redistribution.

### Gaps
- Conditions RSS actuelles de CBC, La Presse, Globe (version 2026) et Cision : pages bloquées (403) ou introuvables (404).
- TMX (TMX Money, TSX) : aucun flux de nouvelles ni API gratuite documentée n'a été trouvé. Les conditions TSX existent ([tsx.com terms](https://www.tsx.com/terms-of-use?lang=fr)) mais n'ont pas été lues.
- Filtrage des fils Newswire.ca et GlobeNewswire par ticker : non vérifié (GlobeNewswire bloqué, motif d'URL Newswire par organisation non testé).

## 5. Banques centrales et communications statistiques (Banque du Canada, Fed, BCE, StatCan Le Quotidien, BLS)

### Takeaway
Ce sont les sources les plus sûres juridiquement. Elles sont gratuites, sans clé, avec des flux RSS actifs au 14 novembre 2026, et réutilisables avec attribution (domaine public pour la Fed, licence ouverte pour StatCan). Elles peuvent être stockées **en texte intégral** dans la base OKF avec citation, sauf contenus tiers.

### Cited Findings

**Banque du Canada**
- Flux principaux : communiqués `https://www.bankofcanada.ca/content_type/press-releases/feed/`, discours `…/content_type/speeches/feed/`, annonces `…/content_type/announcements/feed/`, Rapport sur la politique monétaire `…/content_type/mpr/feed/`, résumé des délibérations `…/content_type/summary-of-deliberations/feed/`, Enquête sur les perspectives des entreprises `…/content_type/bos/feed/`, Revue du système financier `…/content_type/fsr/feed/`, avis de marché `…/content_type/notices/feed/`, plus des flux de change Valet `https://www.bankofcanada.ca/valet/fx_rss/FXUSDCAD`. La page ne liste **pas** de flux distinct pour les annonces de taux — [BoC RSS feeds](https://www.bankofcanada.ca/rss-feeds/)
- Le flux des communiqués est actif (vérifié par curl). Il expose `dc:date` (ex. `2026-11-14T18:31:38+00:00`) — [BoC press-releases feed](https://www.bankofcanada.ca/content_type/press-releases/feed/)
- Version française : page `https://www.banqueducanada.ca/fils-rss/`. Le motif `banqueducanada.ca/content_type/press-releases/feed/` redirige vers une page HTML (vérifié par curl) — [BoC RSS](https://www.bankofcanada.ca/rss-feeds/)
- Conditions : « the Bank permits you to freely use, copy, distribute and transmit its website content ». Il faut « attribute the Bank of Canada as the source… and indicate if changes were made ». Exceptions : contenu tiers, logos, billets de banque. Il est interdit de contourner les limites de fréquence de Valet. Les taux de change sont « sourced from LSEG » — [BoC Terms](https://www.bankofcanada.ca/terms/)

**Réserve fédérale (Board)**
- Flux : `https://www.federalreserve.gov/feeds/press_all.xml`, `press_monetary.xml` (déclarations FOMC, calendrier), `speeches.xml`, `testimony.xml`, `speeches_and_testimony.xml`, des flux par gouverneur, et des flux de données (`h15.xml`, `g17.xml`, `prates.xml`, etc.). Pas de flux FOMC ni Beige Book distinct listé — [Fed feeds](https://www.federalreserve.gov/feeds/feeds.htm)
- `press_monetary.xml` est actif (vérifié par curl, titre récent : « Federal Reserve announces revised tentative schedule of FOMC… ») — [Fed press_monetary](https://www.federalreserve.gov/feeds/press_monetary.xml)
- Licence : « Unless otherwise indicated, information on Board's website is in the public domain and may be copied and distributed without permission ». La Fed demande de la citer comme source — [Fed disclaimer](https://www.federalreserve.gov/disclaimer.htm)

**BCE**
- Flux : `https://www.ecb.europa.eu/rss/press.html` (communiqués, discours, interviews, conférences de presse), `/rss/blog.html`, `/rss/statpress.html`, `/rss/operations.html`, `/rss/pub.html`. Pas de flux dédié aux décisions de politique monétaire — [ECB RSS](https://www.ecb.europa.eu/home/html/rss.en.html)
- `press.html` est actif (vérifié par curl, éléments du 2026-11-13 et du 2026-11-10) — [ECB press RSS](https://www.ecb.europa.eu/rss/press.html)
- Conditions : « may make free use of the information », à condition qu'elle apparaisse « accurately and the ECB must be cited as the source ». Les modifications doivent être signalées. Les documents signés par des auteurs (Working Papers) exigent une autorisation pour être republiés — [ECB Disclaimer & Copyright](https://www.ecb.europa.eu/services/disclaimer/html/index.en.html)

**Statistique Canada, Le Quotidien**
- URL qui fonctionnent (vérifié par curl, élément du 2026-11-13 08:30 HNE) : `https://www150.statcan.gc.ca/n1/rss/dai-quo/0-eng.rss` et **`…/0-fra.rss`** (tous sujets). Les numéros de sujet sont 3956 (prix), 2621 (travail), 3764 (comptes économiques), 1130 (commerce international), etc. — [StatCan Daily RSS](https://www150.statcan.gc.ca/n1/dai-quo/rss-eng.htm) ; [flux FR](https://www150.statcan.gc.ca/n1/rss/dai-quo/0-fra.rss)
- **Piège** : les liens relatifs de la page RSS (`https://www.statcan.gc.ca/rss/dai-quo/0-eng.rss`) redirigent vers une page 404 (vérifié par curl) — [StatCan RSS FR](https://www150.statcan.gc.ca/n1/dai-quo/rss-fra.htm)
- Licence ouverte de Statistique Canada : licence mondiale, gratuite et non exclusive pour utiliser, reproduire et distribuer, y compris « sell the Information ». Mention obligatoire : « Source: Statistics Canada, name of product, reference date » — [StatCan Open Licence](https://www.statcan.gc.ca/en/terms-conditions/open-licence)

**BLS**
- Flux : `https://www.bls.gov/feed/cpi.rss`, `empsit.rss`, `ppi.rss`, `jolts.rss`, plus des flux « latest » (`cpi_latest.rss`, `bls_latest.rss`…). Pas de flux « toutes publications » — [BLS feeds](https://www.bls.gov/feed/)
- `cpi.rss` est actif (vérifié par curl). L'entrée « CPI for all items increases 0.4% in October » porte `published`/`updated` = 2026-11-10T07:55:47-05:00 — [BLS CPI feed](https://www.bls.gov/feed/cpi.rss)

### Inferences
- Le flux BLS utilise des balises Atom (`<published>`, `<updated>`) malgré son extension `.rss`. Le parseur doit gérer les deux formats (feedparser le fait).
- L'heure de l'entrée BLS (07:55 HNE pour une publication officielle à 08:30) montre que **la date du flux peut précéder l'heure officielle de publication**. Pour éviter le look-ahead, il faut utiliser l'heure officielle du calendrier de publication comme « date de disponibilité » et non `published`. Ce point est à vérifier sur d'autres publications.
- Les annonces de taux de la BdC passent par le flux des communiqués (absence de flux dédié). Il faut filtrer sur le titre (« Bank of Canada maintains/lowers/raises policy rate »).

### Gaps
- URL exactes des flux français de la Banque du Canada : non confirmées, car le motif testé redirige vers du HTML.
- Pas de vérification d'un flux FOMC « minutes » distinct (inclus en principe dans `press_monetary.xml`).
- Les conditions de réutilisation du BLS (page « copyright ») n'ont pas été lues. Le statut fédéral américain suggère le domaine public, mais ce n'est pas vérifié ici.

## 6. Décisions politiques et réglementaires (Gazette du Canada, LEGISinfo, OpenParliament, API nouvelles Canada.ca/Finances, Federal Register, Congress.gov, GovInfo, Regulations.gov, SEC/EDGAR, OSC/CSA/AMF, Maison-Blanche, USTR, ASFC)

### Takeaway
Presque tout est gratuit et ouvert. Pas de clé pour la Gazette du Canada, LEGISinfo, OpenParliament, l'API Canada.ca (FR/EN, Atom/JSON), le Federal Register et les flux SEC. Une clé api.data.gov gratuite suffit pour Congress.gov, GovInfo et Regulations.gov. Deux pièges anti-look-ahead majeurs : la **`publication_date` future du Federal Register** et la **dissemination différée d'EDGAR**.

### Cited Findings

**Canada**
- **Gazette du Canada** : `https://www.gazette.gc.ca/rss/p1-eng.xml` (Partie I, avis et projets de règlement), `p2-eng.xml` (Partie II, règlements), `en-ls-eng.xml` (Partie III), plus les versions `-fra`. Les flux sont gratuits depuis 2008 — [Gazette RSS](https://gazette.gc.ca/rss/sc-rb-eng.html) ; [version FR](https://gazette.gc.ca/rss/sc-rb-fra.html)
- `p1-eng.xml` est actif (vérifié par curl, élément du 2026-11-14) et `p2-fra.xml` aussi (élément du 2026-11-04) — [Gazette P1](https://www.gazette.gc.ca/rss/p1-eng.xml) ; [Gazette P2 FR](https://www.gazette.gc.ca/rss/p2-fra.xml)
- **LEGISinfo (Parlement)** : `https://www.parl.ca/legisinfo/en/bills/json` renvoie la liste des projets de loi en JSON, avec des champs bilingues `LongTitleEn`/`LongTitleFr`, `StatusNameEn`… `…/en/bills/rss` donne un RSS 2.0 et `…/en/overview/json/recentlyintroduced` (ou `/xml/`) les projets récents (vérifié par curl, HTTP 200) — [LEGISinfo overview](https://www.parl.ca/legisinfo/en/overview) ; [bills JSON](https://www.parl.ca/legisinfo/en/bills/json) ; [bills RSS](https://www.parl.ca/legisinfo/en/bills/rss)
- **OpenParliament.ca** : `api.openparliament.ca` en JSON, pour les projets de loi, votes, députés, débats et comités. Filtres `gt`/`gte`/`lt`/`lte` sur les dates. En-tête `API-Version: v1`, avec l'adresse courriel dans le `User-Agent`. Une limite de débit existe (HTTP 429). « This site holds no copyright on any data accessible through this API ». Le contenu reste la propriété de la Couronne (« Speaker's Permission »). Aucune garantie de stabilité ; vidage de base disponible pour les gros volumes — [OpenParliament API](https://openparliament.ca/api/)
- **API Nouvelles du gouvernement du Canada (dont le ministère des Finances)** : `https://api.io.canada.ca/io-server/gc/news/en/v2`, avec les filtres `dept=` (ex. `departmentfinance`), `type=` (`newsreleases`, `statements`, `backgrounders`, `speeches`, `mediaadvisories`), `topic=`, `minister=`, `location=`, plus `sort=publishedDate&orderBy=desc&pick=N&format=atom` — [Canada.ca web feeds](https://www.canada.ca/en/news/web-feeds.html)
- La variante **`/fr/v2`** fonctionne (titres en français, vérifié par curl). `format=json` renvoie `link` et `teaser` (vérifié par curl). L'élément le plus récent du ministère des Finances date du 2026-11-14T10:00:14-05:00 — [API FR Finances](https://api.io.canada.ca/io-server/gc/news/fr/v2?dept=departmentfinance&sort=publishedDate&orderBy=desc&pick=2&format=atom)
- Conditions Canada.ca : reproduction **non commerciale** permise « without charge or further permission », avec exactitude, titre complet et mention de la copie. La reproduction « for the purposes of commercial redistribution » exige une autorisation écrite — [Canada.ca terms](https://www.canada.ca/en/transparency/terms.html)
- **OSC / ACVM** : le flux FeedBurner `https://feeds.feedburner.com/rss_osc_headlines_en` est actif (vérifié par curl, élément du 2026-11-12). Il couvre les avis de l'OSC et les communiqués OSC et ACVM — [OSC headlines feed](https://feeds.feedburner.com/rss_osc_headlines_en) ; [OSC RSS index](https://www.osc.gov.on.ca/en/rss_index.htm). `osc.ca/en/rss.xml` et les flux `securities-administrators.ca/feed/` renvoient une 403 (défi Cloudflare, vérifié par curl) — [CSA](https://www.securities-administrators.ca/feed/)
- **AMF (Québec)** : la page des fils RSS renvoie une 403 au client de recherche — [AMF fils RSS](https://lautorite.qc.ca/grand-public/fils-rss)

**États-Unis**
- **Federal Register API v1** : `https://www.federalregister.gov/api/v1/documents.json` fonctionne **sans clé** (vérifié par curl). On peut choisir les champs (`publication_date`, `signing_date`, `effective_on`, `type`, `agencies`, `raw_text_url`…). La réponse indique `count: 10000` et `total_pages: 50`, soit un plafond pratique de 10 000 résultats par requête. La page de documentation redirige les robots vers `unblock.federalregister.gov` — [Federal Register API](https://www.federalregister.gov/api/v1/documents.json?per_page=1) ; [docs](https://www.federalregister.gov/developers/documentation/api/v1)
- **Constat de look-ahead** : le 2026-11-14, l'API renvoyait déjà des documents avec `publication_date: "2026-11-16"` (ex. « Certain Railway Tank Cars… From Mexico: Initiation of Countervailing Duty Investigation »), qui sont en inspection publique avant publication (vérifié par curl) — [Federal Register API (tariff)](https://www.federalregister.gov/api/v1/documents.json?per_page=1&conditions%5Bterm%5D=tariff&order=newest)
- **Congress.gov API v3** : « An API key is required » (via api.data.gov). « The rate limit is set to 5,000 requests per hour ». XML ou JSON, 20 résultats par défaut et 250 au maximum. Citation facultative : « Data retrieved from Congress.gov » — [LibraryOfCongress/api.congress.gov](https://github.com/LibraryOfCongress/api.congress.gov)
- **api.data.gov** (GovInfo, Regulations.gov…) : par défaut « 1,000 requests per hour ». DEMO_KEY : 30 requêtes/h et 50/jour par IP. En-têtes `X-RateLimit-Remaining` — [api.data.gov manual](https://api.data.gov/docs/developer-manual/)
- **Regulations.gov API v4** : `https://api.regulations.gov/v4`, clé dans `X-Api-Key`, endpoints `/documents`, `/dockets`, `/comments`. Filtre `filter[postedDate][ge]`. `lastModifiedDate` est « in beta and may be removed ». L'API de dépôt de commentaires est limitée à 50 requêtes/min et 500/h — [Regulations.gov API](https://open.gsa.gov/api/regulationsgov/)
- **SEC** : le flux des communiqués `https://www.sec.gov/news/pressreleases.rss` est actif (vérifié par curl, élément du 2026-11-13). Les 8-K récents sont disponibles en Atom via `browse-edgar?action=getcurrent&type=8-K&output=atom` (vérifié par curl, mis à jour le 2026-11-14). La recherche plein texte `efts.sec.gov/LATEST/search-index?q=…&forms=8-K` renvoie du JSON (vérifié par curl) — [SEC press RSS](https://www.sec.gov/news/pressreleases.rss) ; [EDGAR 8-K Atom](https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&company=&dateb=&owner=include&start=0&count=40&output=atom)
- Politique d'accès équitable EDGAR : 10 requêtes/s et un `User-Agent` déclaré (format « Sample Company Name AdminContact@… »). Les dépôts commencés après 17 h 30 HE sont diffusés le jour ouvrable suivant. Les données sont gratuites pour tous — [SEC Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
- **Maison-Blanche** : `https://www.whitehouse.gov/presidential-actions/feed/` est actif (vérifié par curl, élément du 2026-11-12) — [WH presidential actions feed](https://www.whitehouse.gov/presidential-actions/feed/)
- **USTR** : `https://ustr.gov/rss.xml` est actif (vérifié par curl, élément du 2026-11-13, « Weekly Trade Focus: APEC ») — [USTR RSS](https://ustr.gov/rss.xml)

### Inferences
- Pour l'anti-look-ahead, il faut stocker deux dates par document : `published_at` (date officielle) et `available_at` (première observation par A4, ou heure de mise en ligne). Pour le Federal Register, `available_at` correspond à l'heure d'inspection publique (endpoint `public-inspection-documents`), et `publication_date` peut être postérieure à la date d'observation. Pour EDGAR, il faut utiliser l'heure d'acceptance ou de dissemination et non la date du rapport.
- Le contenu gouvernemental américain (Federal Register, Congress, SEC) peut être stocké en texte intégral. Pour Canada.ca et la Gazette, le stockage et la citation non commerciaux sont permis avec attribution. Une démo commerciale demanderait une autorisation.
- Pour les tarifs et le commerce : côté États-Unis, Federal Register (`conditions[term]=tariff`), USTR RSS et Maison-Blanche (décrets). Côté Canada, Gazette Partie II (décrets de surtaxe) et API Canada.ca (`dept=departmentfinance`, `topic=taxes`).

### Gaps
- **ASFC (CBSA)** : aucun flux d'avis des douanes trouvé (motif `cbsa-asfc.gc.ca/rss/whatsnew-quoidneuf-eng.xml` en 404, vérifié par curl).
- GovInfo : documentation non rendue par l'outil (page JS). Les collections et endpoints n'ont pas été vérifiés ici.
- AMF et ACVM : flux RSS actuels non vérifiés (403). Celui de l'OSC passe par FeedBurner, un service hérité dont la pérennité est incertaine.
- Conditions de réutilisation propres à OpenParliament (permission du Président) non détaillées.
- Le paramètre de l'API Canada.ca n'a pas de documentation de référence officielle (seulement la page des fils), d'où un risque de changement non annoncé.

## 7. Jeux de données NLP prêts pour le sentiment (FinBERT, Hugging Face)

### Takeaway
Les jeux de sentiment financier les plus utilisés ont des licences restrictives (Financial PhraseBank en CC BY-NC-SA 3.0) ou absentes (FNSPID). Le modèle ProsusAI/finbert est désormais étiqueté CC BY-NC-SA 4.0. Aucun jeu francophone de sentiment financier sous licence claire n'a été identifié.

### Cited Findings
- `takala/financial_phrasebank` : **cc-by-nc-sa-3.0**, anglais (API Hugging Face consultée le 2026-11-15) — [HF financial_phrasebank](https://huggingface.co/datasets/takala/financial_phrasebank)
- `zeroshot/twitter-financial-news-sentiment` : **MIT**, anglais — [HF twitter-financial-news-sentiment](https://huggingface.co/datasets/zeroshot/twitter-financial-news-sentiment)
- `Zihan1004/FNSPID` (nouvelles et prix d'actions) : **aucune licence déclarée** dans les métadonnées — [HF FNSPID](https://huggingface.co/datasets/Zihan1004/FNSPID)
- `sujet-ai/Sujet-Finance-Instruct-177k` : **apache-2.0** — [HF Sujet-Finance-Instruct](https://huggingface.co/datasets/sujet-ai/Sujet-Finance-Instruct-177k)
- `Brianferrell787/financial-news-multisource` : licence « other » — [HF financial-news-multisource](https://huggingface.co/datasets/Brianferrell787/financial-news-multisource)
- `vblagoje/cc_news` : licence « unknown » — [HF cc_news](https://huggingface.co/datasets/vblagoje/cc_news)
- Modèle `ProsusAI/finbert` : métadonnées **cc-by-nc-sa-4.0** (lastModified 2026-10-12, environ 3,2 M téléchargements) — [HF ProsusAI/finbert](https://huggingface.co/ProsusAI/finbert). `yiyanghkust/finbert-tone` n'a aucune licence déclarée — [HF finbert-tone](https://huggingface.co/yiyanghkust/finbert-tone)

### Inferences
- Pour un datathon (non commercial), FinBERT et PhraseBank sont acceptables, mais **ShareAlike** impose de redistribuer sous la même licence tout jeu dérivé. Il faut le documenter dans la fiche OKF.
- Pour le français, le plus réaliste est un LLM multilingue (Bedrock) ou une traduction suivie de FinBERT. C'est un choix à justifier, faute de jeu de données FR licencié.

### Gaps
- Jeux de sentiment financier en français (Québec) : non trouvés dans le temps imparti.
- Le changement de licence de ProsusAI/finbert (date, raison) n'a pas été vérifié dans l'historique du dépôt.
- FiQA (TheFinAI) : appel à l'API Hugging Face en échec, licence non vérifiée.

## 8. Clients Python et serveurs MCP

### Takeaway
GDELT dispose d'un client Python maintenu (gdeltdoc) et de plusieurs serveurs MCP sans clé. Massive et Alpha Vantage ont des MCP officiels, mais leur accès aux nouvelles est payant ou limité. Pour les flux RSS gouvernementaux, un simple parseur RSS/Atom suffit.

### Cited Findings
- `gdeltdoc` (PyPI) : client de l'API GDELT 2.0 DOC (modes ArtList et Timeline, objet `Filters`), version 1.12.0, licence MIT — [PyPI gdeltdoc](https://pypi.org/project/gdeltdoc/) ; [GitHub gdelt-doc-api](https://github.com/kepler471/gdelt-doc-api)
- `cyanheads/gdelt-mcp-server` : serveur MCP TypeScript (stdio ou HTTP streamable), **sans clé API**. Il interroge les nouvelles mondiales et les transcriptions TV via GDELT. Installation : `npx -y @cyanheads/gdelt-mcp-server`. Une instance hébergée publique existe — [Glama](https://glama.ai/mcp/servers/rztestyor9) ; [LobeHub](https://lobehub.com/mcp/cyanheads-gdelt-mcp-server)
- Autres MCP GDELT : `guptaprakhariitr/gdelt-events-mcp` (événements géopolitiques, séries de ton) et GDELT Cloud MCP (service tiers hébergé, distinct du GDELT Project) — [getdrio](https://www.getdrio.com/mcp/io-github-guptaprakhariitr-gdelt-events-mcp) ; [GDELT Cloud MCP](https://docs.gdeltcloud.com/mcp/introduction)
- `mcp_massive` (ex `polygon-io/mcp_polygon`) : officiel, expérimental, Python 3.12+, variable `MASSIVE_API_KEY`, nouvelles Benzinga ou analystes limitées. Licence MIT (instantané tiers) — [Glama mcp_massive](https://glama.ai/mcp/servers/polygon-io/mcp_massive) ; [TypingMind](https://www.typingmind.com/mcp/polygon-io-mcp_polygon)
- Alpha Vantage mentionne son « official Alpha Vantage MCP server » — [Alpha Vantage premium](https://www.alphavantage.co/premium/)

### Inferences
- Pile suggérée pour A4 (non vérifiée ici) : `feedparser` (RSS/Atom : BoC, Fed, BCE, StatCan, BLS, Gazette, Canada.ca, SEC), `requests` (LEGISinfo JSON, Federal Register, OpenParliament), `gdeltdoc` (GDELT), puis normalisation en front-matter YAML OKF : `source`, `url`, `published_at`, `observed_at`, `licence`, `storage_rights`.
- Les MCP GDELT tiers ne sont pas audités. Par prudence pour un projet évalué par BN, mieux vaut appeler l'API GDELT directement depuis A4 plutôt que dépendre d'une instance MCP hébergée par un particulier.

### Gaps
- Statut de maintenance, nombre d'étoiles et licences exactes des dépôts MCP GDELT : non vérifiés sur GitHub.
- Clients et MCP pour Marketaux, Finnhub (`finnhub-python`), NewsAPI (`newsapi-python`) et EDGAR (`edgartools`) : non vérifiés dans ce lot.

## 9. Pièges 2025–2026 (plans supprimés, fermetures, prix, look-ahead)

### Takeaway
Le paysage s'est fermé en 2025–2026 : Alpha Vantage news devenu Premium, Reddit sur approbation, X au paiement à l'usage, Polygon rebaptisé Massive. Les sources gouvernementales et de banques centrales restent ouvertes. Les dates diffèrent fortement d'une source à l'autre, ce qui crée un risque concret de look-ahead.

### Cited Findings
- Alpha Vantage NEWS_SENTIMENT est marqué « Premium » au 2026-11-14 (vérifié par curl) — [Alpha Vantage docs](https://www.alphavantage.co/documentation/#news-sentiment)
- Reddit : accès libre fermé le 11 novembre 2025 — [r/redditdev (miroir)](https://r.datuan.dev/r/redditdev/s/gquSJqMgrM)
- X : paiement à l'usage par défaut depuis le 6 février 2026 — [Roboin](https://roboin.io/article/en/2026/02/08/x-transitions-api-to-pay-per-use-model-ending-free-plan/)
- Polygon.io est devenu Massive : nouvelles avec 2 ans d'historique en Basic, et MCP renommé — [Massive news docs](https://massive.com/docs/rest/stocks/news) ; [Glama mcp_massive](https://glama.ai/mcp/servers/polygon-io/mcp_massive)
- Délais des plans gratuits : NewsAPI.org 24 h ([pricing](https://newsapi.org/pricing)), GNews 12 h ([pricing](https://gnews.io/pricing)), NewsData.io 12 h ([pricing](https://newsdata.io/pricing)), Mediastack « Delayed » ([pricing](https://mediastack.com/pricing)), Alpaca sans temps réel −15 min ([reference](https://docs.alpaca.markets/us/reference/news-3))
- Ambiguïtés de dates :
  - Tiingo remplace `publishedDate` par l'heure de crawl si la source n'en a pas, et fournit `crawlDate` à part ([Tiingo news](https://www.tiingo.com/documentation/news)).
  - Alpaca trie sur `updated_at` et distingue `created_at` ([Alpaca](https://docs.alpaca.markets/us/reference/news-3)).
  - Le Federal Register expose des `publication_date` futures ([API](https://www.federalregister.gov/api/v1/documents.json?per_page=1&conditions%5Bterm%5D=tariff&order=newest)).
  - EDGAR diffuse le lendemain les dépôts commencés après 17 h 30 HE ([SEC](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)).
- URL obsolètes : liens RSS StatCan `www.statcan.gc.ca/rss/...` cassés, à remplacer par `www150.statcan.gc.ca/n1/rss/...` ([vérifié](https://www150.statcan.gc.ca/n1/rss/dai-quo/0-fra.rss)). Le RSS du Financial Post est introuvable ([financialpost.com](https://financialpost.com/)).
- Blocages anti-robots (403 ou Cloudflare) sur GlobeNewswire, ACVM, AMF, CBC/rss, La Presse/fils-rss et la doc du Federal Register (vérifié). La SEC impose un `User-Agent` déclaré ([SEC](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)). OpenParliament demande une adresse courriel dans le `User-Agent` ([OpenParliament](https://openparliament.ca/api/)).
- GDELT : limite d'une requête par 5 s sur DOC 2.0 (vérifié) — [GDELT DOC](https://api.gdeltproject.org/api/v2/doc/doc?query=%22Bank%20of%20Canada%22&mode=artlist&format=json)

### Inferences
- **Matrice de droits pour la base OKF (synthèse des sections 1 à 6)** :
  - *Texte intégral stockable et citable avec attribution* : Fed (domaine public), Banque du Canada, BCE (hors documents signés), StatCan (licence ouverte), BLS, Federal Register, Congress.gov, SEC/EDGAR. Également Canada.ca et la Gazette, mais en non commercial seulement.
  - *Métadonnées redistribuables, texte non* : GDELT (citation et lien obligatoires), OpenParliament (aucun droit revendiqué, contenu de la Couronne).
  - *Titre, extrait court et lien seulement, usage interne ou non commercial* : NewsAPI.org (dev seulement), GNews gratuit, NewsData (attribution obligatoire), Mediastack gratuit, Currents (commercial avec attribution, sans republication), World News API (cache 1 h, backlink), Event Registry (évaluation seulement), Marketaux (CGU introuvables), Finnhub (personnel, pas de redistribution des « derived results »), Tiingo (« Internal Use Only »), Google News et Yahoo RSS (personnel), Radio-Canada, Globe, La Presse, CBC (personnel).
  - *À éviter* : X, Reddit (approbation), Stocktwits (anti-scraping), Common Crawl en texte intégral (aucun droit sur le contenu, indemnité IA).
- La clause Finnhub sur les « derived results » pourrait viser jusqu'aux scores de sentiment dérivés. Elle mérite d'être signalée aux juges si Finnhub est utilisé dans une démo publique.

### Gaps
- Aucune annonce officielle de fermeture d'API de nouvelles (NewsAPI, GNews, Mediastack…) n'a été trouvée pour 2025–2026. Les changements notés viennent de la comparaison avec des connaissances antérieures, sauf Alpha Vantage, Reddit et X, qui sont documentés.
- Les CGU de plusieurs médias canadiens (CBC, La Presse, Cision) n'ont pas pu être lues (403/404). Il faudrait les consulter manuellement dans un navigateur avant de choisir.
