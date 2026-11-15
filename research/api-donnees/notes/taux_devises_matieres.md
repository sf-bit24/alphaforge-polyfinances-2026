# API gratuites : taux d'intérêt et obligations, devises (FX), matières premières et or (état au 14 novembre 2026)

> Méthode : vérification en direct (appels `curl` le 2026-11-14, samedi) chaque fois que c'était possible. Pour ces faits, la source citée est l'URL d'appel elle-même ; ils sont marqués **[testé 2026-11-14]**. Le reste vient de la documentation officielle et des pages de tarifs, consultées le même jour. Ce qui n'a pas pu être vérifié est signalé « non vérifié » ou rangé dans les lacunes.
> Les bases de Valet (USD/CAD, 2/10 ans, taux directeur) et de FRED (DGS2, DGS10, fed funds) sont considérées comme connues. Seuls les compléments sont détaillés ici.

---

## 1. Taux d'intérêt, obligations et courbes de rendement (Canada, États-Unis, Europe, crédit, hypothèques, indexé à l'inflation)

### Takeaway
Pour le Canada et les États-Unis, tout l'essentiel est gratuit, sans clé et redistribuable avec attribution : rendements de référence, courbe zéro-coupon, CORRA, adjudications, par yield curve nominale et réelle, SOFR/EFFR/OBFR, adjudications TreasuryDirect, PMMS, ECB, BoE. Il y a trois exceptions majeures. Les écarts de crédit ICE BofA sur FRED sont limités à 3 ans d'historique depuis avril 2026 et leur redistribution est interdite sans permission d'ICE. Les données TRACE au niveau des transactions et les flux automatisés de MSRB EMMA sont réservés aux abonnés ou soumis à des ententes. La Banque d'Angleterre n'offre aucune API pour ses courbes (fichiers ZIP seulement).

### Cited Findings

#### 1.1 Banque du Canada : compléments Valet (au-delà de USD/CAD, 2 ans/10 ans et taux directeur)
- **Base URL :** `https://www.bankofcanada.ca/valet/` (docs Swagger : `/valet/docs`). Sans clé. Chaque réponse JSON contient `"terms": {"url": "https://www.bankofcanada.ca/terms/"}` **[testé 2026-11-14]**. Sources : [Valet group](https://www.bankofcanada.ca/valet/groups/bond_yields_benchmark/json), [Valet docs](https://www.bankofcanada.ca/valet/docs).
- **Rendements de référence (groupe `bond_yields_benchmark`, 7 séries, « Business daily », %) :** `BD.CDN.2YR.DQ.YLD`, `BD.CDN.3YR.DQ.YLD`, `BD.CDN.5YR.DQ.YLD`, `BD.CDN.7YR.DQ.YLD`, `BD.CDN.10YR.DQ.YLD`, `BD.CDN.LONG.DQ.YLD` et `BD.CDN.RRB.DQ.YLD` (rendement des obligations à rendement réel, long terme). Dernière observation le 2026-11-12 : 2 ans 3,33 ; 3 ans 3,41 ; 5 ans 3,53 ; 7 ans 3,61 ; 10 ans 3,78 ; long 4,09 ; RRB 1,94 **[testé 2026-11-14]**. Source : [Valet bond_yields_benchmark](https://www.bankofcanada.ca/valet/observations/group/bond_yields_benchmark/json?recent=1).
- **Rendements moyens des obligations négociables (groupe `bond_yields_all`) :** `CDN.AVG.1YTO3Y.AVG`, `CDN.AVG.3YTO5Y.AVG`, `CDN.AVG.5YTO10Y.AVG`, `CDN.AVG.OVER.10.AVG` (11 séries avec les séries de référence) **[testé 2026-11-14]**. Source : [Valet bond_yields_all](https://www.bankofcanada.ca/valet/observations/group/bond_yields_all/json?recent=1).
- **Bons du Trésor (groupe `TBILL_ALL`, hebdomadaire) :** 3 mois `V80691303` (2,61), 6 mois `V80691304` (2,80), 1 an `V80691305` (3,05). Dernière observation le 2026-11-03, la série 1 mois étant vide **[testé 2026-11-14]**. Source : [Valet TBILL_ALL](https://www.bankofcanada.ca/valet/observations/group/TBILL_ALL/json?recent=1).
- **CORRA :** série `AVG.INTWO`, 2,53 % au 2026-11-12. Le 2026-11-11 (jour férié) est absent **[testé 2026-11-14]**. Le groupe `CORRA` contient 14 séries : volume total et volume tronqué, nombre de contributeurs (14), percentiles 5/25/75/95, moyenne pondérée, mode, `CORRA_PUBLICATION_STATUS` (« Published ») et `CORRA_CALCULATION_METHODOLOGY` (« Standard »). Il existe aussi les groupes `CORRA_COMPOUNDED_INDEX` et `CORRA_TRANSPARENCY` (« summary of errors detected after publication »). Sources : [Valet CORRA](https://www.bankofcanada.ca/valet/observations/group/CORRA/json?recent=1), [liste des groupes Valet](https://www.bankofcanada.ca/valet/lists/groups/json).
- **Adjudications du gouvernement du Canada (dans Valet) :** les groupes `AUC_BOND_RESULTS` (24 séries : date d'adjudication, heure limite 12:00, échéance, coupon, ISIN, montant, prix et rendement moyens, rendements bas et haut, couverture, « tail »), `AUC_TBILL_RESULTS` (22 séries, heure limite 10:30), `AUC_BOND_RR_RESULTS`, `AUC_BOND_U_RESULTS` (ultra-long), `AUC_BOND_S_*` (rachats/échanges), `AUC_SCHED` (calendrier) et les groupes `*_UPCOMING_*`. Exemple : l'adjudication 5 ans prévue le 2026-11-19 (ISIN CA135087V434, 5 000 M$, coupon 3,500, échéance 2032-03-01) a des champs de résultats vides avant l'adjudication. La dernière adjudication d'obligations à rendement réel listée date du 2022-09-01 (30 ans, CA135087M433) **[testé 2026-11-14]**. Sources : [Valet AUC_BOND_RESULTS](https://www.bankofcanada.ca/valet/observations/group/AUC_BOND_RESULTS/json?recent=1), [Valet AUC_BOND_RR_RESULTS](https://www.bankofcanada.ca/valet/observations/group/AUC_BOND_RR_RESULTS/json?recent=1).
- **Hypothèque conventionnelle 5 ans (BdC) :** série `V80691335` « Conventional mortgage, 5-year », hebdomadaire. Valeur 6,19 % au 2026-11-11 **[testé 2026-11-14]**. Les groupes `A4_RATES_MORTGAGES` et `A4_RATES_VARIABLE` donnent les taux effectifs des prêts hypothécaires des banques à charte. Sources : [Valet V80691335](https://www.bankofcanada.ca/valet/observations/V80691335/json?recent=1), [liste des groupes](https://www.bankofcanada.ca/valet/lists/groups/json).
- **Courbe zéro-coupon (hors Valet) :** fichier CSV produit par un formulaire. URL directe testée : `https://www.bankofcanada.ca/stats/results/csv?lookupPage=lookup_yield_curve.php&startRange=1986-01-01&searchRange=&dFrom=AAAA-MM-JJ&dTo=AAAA-MM-JJ`. Colonnes `ZC025YR` à `ZC3000YR` (0,25 à 30 ans, 120 colonnes), valeurs en décimales (0,0500 = 5 %). La dernière date disponible le 2026-11-14 était le **2026-10-28** **[testé 2026-11-14]**. La BdC indique : « typically updated each Thursday by 16:30 ET, with a two-week lag » ; les données manquantes s'affichent « na » (par exemple 1986–1990) ; méthodologie de Bolder, Johnson et Metzler (2004). Source : [BdC, Yield curves for zero-coupon bonds](https://www.bankofcanada.ca/rates/interest-rates/bond-yield-curves/).
- **Licence BdC :** la BdC « permits you to freely use, copy, distribute and transmit its website content ». Il faut l'attribuer comme source et indiquer les modifications, sans laisser entendre une approbation. Le contenu de tiers est exclu. Il est interdit de « circumvent such limit or limits imposed by the Bank with respect to the number or frequency of requests… (e.g., the Bank of Canada Valet API) ». Aucun quota chiffré n'est publié. Source : [BdC Terms](https://www.bankofcanada.ca/terms/).
- **Horodatage :** les observations Valet ne portent qu'une date d'observation (`"d"`), sans date de publication ni vintage **[testé 2026-11-14]**. Source : [Valet CORRA](https://www.bankofcanada.ca/valet/observations/AVG.INTWO/json?recent=2).

#### 1.2 Département du Trésor américain : par yield curve nominale et réelle
- **Flux XML (Atom/OData) :** `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value_month=202611`. Les valeurs de `data=` documentées sont les courbes par nominale et réelle, les taux des bons et les taux à long terme (nominaux et réels). Le paramètre `field_tdr_date_value=AAAA` donne une année complète. Sans clé. Sources : [Treasury XML feed](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed), [flux testé](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value_month=202611).
- **CSV :** `…/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv`. Pour la courbe réelle, il renvoie les colonnes 5, 7, 10, 20 et 30 ans. Au 11/13/2026 : 2,68 ; 2,78 ; 2,91 ; 3,15 ; 3,28 **[testé 2026-11-14]**. Source : [CSV Treasury real yield](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv).
- **Méthodologie et heure de référence :** cotations indicatives « obtained by the Federal Reserve Bank of New York at approximately 3:30 PM each business day ». La courbe réelle (TIPS) est publiée depuis le 2 janvier 2004. Source : [Treasury Interest Rate Statistics](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics). La courbe par est estimée par « monotone convex spline » et le Trésor « does not create or publish daily zero-coupon curve rates ». Source : [Treasury Interest Rates FAQ](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/interest-rates-frequently-asked-questions).
- **Horodatage :** le flux Atom contient un `<updated>2026-11-14T01:01:25Z</updated>`, c'est-à-dire l'heure de génération du flux et non une date de publication par observation **[testé 2026-11-14]**. Source : [flux testé](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value_month=202611).

#### 1.3 TreasuryDirect et Fiscal Data (adjudications et taux moyens)
- **API TreasuryDirect « TA_WS » (toujours fonctionnelle) :** `https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json&type=Note&pagesize=1` renvoie du JSON (CUSIP, `announcementDate`, `competitiveAuctionCloseDate`, `bidToCoverRatio` 2,46, etc.). Sans clé **[testé 2026-11-14]**. Source : [TA_WS testé](https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json&type=Note&pagesize=1).
- **Documentation déplacée :** la page historique de documentation indique « This information has moved to a new location ». Elle renvoie vers le portail « US Treasury Marketable Securities Experience API » du Fiscal Service. Sources : [ancienne page TreasuryDirect](https://www.treasurydirect.gov/webapis/webapisecurities.htm), [nouveau portail](https://api-community.fiscal.treasury.gov/s/communityapi/a01Qo00000pDeK7IAK/enterprise-apisustreasurymarketablesecuritiesexperienceapi).
- **Fiscal Data API :** `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/`. La doc dit : « Our API is open, meaning that it does not require a user account or registration for a token ». Le format par défaut est JSON ; CSV et XML s'obtiennent avec le paramètre `format`. Source : [Fiscal Data API docs](https://fiscaldata.treasury.gov/api-documentation/). Exemple `v2/accounting/od/avg_interest_rates` : record_date 2026-10-31, Treasury Bills 4,014 % **[testé 2026-11-14]**. Source : [appel testé](https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates?sort=-record_date&page[size]=1).

#### 1.4 Fed de New York : SOFR, EFFR, OBFR (Markets Data API)
- **Endpoints :** `https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json`, `…/unsecured/effr/last/1.json`, `…/unsecured/obfr/last/1.json`. Sans clé. La réponse contient `effectiveDate`, `percentRate`, les percentiles 1/25/75/99, `volumeInBillions`, `revisionIndicator`, et pour l'EFFR `targetRateFrom/To`. Au 2026-11-12 : SOFR 3,90 ; EFFR 3,88 (cible 3,75–4,00) ; OBFR 3,88 **[testé 2026-11-14]**. Sources : [SOFR](https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json), [EFFR](https://markets.newyorkfed.org/api/rates/unsecured/effr/last/1.json), [OBFR](https://markets.newyorkfed.org/api/rates/unsecured/obfr/last/1.json).
- **Heures de publication :** SOFR vers 8:00 ET (les SOFR Averages et l'Index suivent peu après) ; EFFR et OBFR « at approximately 9:00 a.m. ET ». Les révisions ont lieu vers 14:30 ET le jour même, seulement si l'écart dépasse 1 point de base. Source : [NY Fed, Additional information about reference rates](https://www.newyorkfed.org/markets/reference-rates/additional-information-about-reference-rates).
- **Licence :** l'utilisation des taux de référence est régie par les Terms of Use de la NY Fed (avertissements, limitations et obligations d'indemnisation). Source : [NY Fed Operating Policy](https://www.newyorkfed.org/markets/opolicy/operating_policy_200302). Le texte exact des clauses d'attribution n'a pas été récupéré (voir Gaps).

#### 1.5 FINRA (TRACE) et MSRB EMMA : marché obligataire de détail
- **Plateforme FINRA API :** le credential **Public coûte 0 $ par mois**. Les credentials Firm et Organization coûtent 1 650 $ par mois. Pour le Fixed Income, la grille indique un accès « Limited » à des jeux comme Corporate Debt Market Breadth/Sentiment, Corporate 144A, Agency Debt Market Breadth/Sentiment, Treasury Daily/Monthly Aggregates, « TRACE », TBA/MBS/CMO Pricing, etc. Source : [FINRA Developer, Fees](https://developer.finra.org/fees).
- **Limites FINRA :** 1 200 requêtes/min par IP en synchrone ; 20 requêtes/min par jeu de données en asynchrone ; 5 000 enregistrements par requête synchrone et 100 000 en asynchrone (1 000 par défaut) ; 3 Mo par charge utile synchrone ; 10 Go/mois par credential FIRM. Les comptes Individual sont « not intended for commercial purposes at this time ». Les conditions sont régies par les FINRA API Terms of Service. Source : [FINRA Developer docs](https://developer.finra.org/docs).
- **Authentification obligatoire :** `https://api.finra.org/data/group/fixedIncomeMarket/name/treasuryDailyAggregates` renvoie HTTP 401 sans jeton. Les métadonnées sont publiques : `https://api.finra.org/metadata/group/fixedIncomeMarket/name/corporateMarketBreadth` décrit « Trace Corporate Market Breadth » (champ `tradeReportDate`) **[testé 2026-11-14]**. Sources : [appel data](https://api.finra.org/data/group/fixedIncomeMarket/name/treasuryDailyAggregates?limit=1), [métadonnées](https://api.finra.org/metadata/group/fixedIncomeMarket/name/corporateMarketBreadth).
- **Service de fichiers TRACE :** l'API web « TRACE Corporate and Agency Debt » est un service de téléchargement de fichiers de fin de journée (Market Aggregates, Market Breadth, Most Active). Source : [TRACE CA debt web API specs](https://www.finra.org/sites/default/files/2023-03/TRACE-CA-debt-web-api-Specs-v4.11.pdf).
- **Serveur MCP tiers FINRA :** il exige un client ID et un secret provisionnés dans l'API Console. Certains jeux exigent d'accepter des ententes de données supplémentaires. Source : [finra-mcp-server](https://mcpservers.org/servers/cmaurer/finra-mcp-server.git).
- **MSRB EMMA :** consultation gratuite sur le site web. Les flux automatisés (« computer-to-computer ») passent par un abonnement payant régi par la Data Access Fee Policy. Aucune API publique gratuite n'a été trouvée. Source : [MSRB Data Access Fee Policy](https://msrb.org/node/13302).

#### 1.6 BCE (courbes de la zone euro) et Banque d'Angleterre
- **API BCE (Data Portal, SDMX) :** `https://data-api.ecb.europa.eu/service/data/{flow}/{key}`, sans clé. Exemple : la courbe `YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y` (spot 10 ans, obligations AAA) en `format=csvdata` vaut 3,3672 au 2026-11-12 **[testé 2026-11-14]**. Source : [appel YC testé](https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y?lastNObservations=3&format=csvdata).
- **Vintages BCE :** les paramètres `updatedAfter` (« latest version of changed values… updates and revisions »), `includeHistory=true` (« the version currently in production and all previous versions »), `If-Modified-Since`, `lastNObservations` et `format` sont documentés. Source : [ECB Data Portal API, data](https://data.ecb.europa.eu/help/api/data).
- **Calendrier BCE :** les courbes sont mises à jour « every TARGET business day at noon (12:00 CET) ». Source : [ECB euro area yield curves](https://www.ecb.europa.eu/stats/financial_markets_and_interest_rates/euro_area_yield_curves/html/index.en.html).
- **Licence BCE :** la réutilisation est gratuite, y compris commerciale, « on the condition that the source is quoted (e.g. "Source: ECB statistics.") and that the statistics (including metadata) are not modified ». Les données de tiers sont exclues. Source : [ESCB reuse policy](https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html).
- **Banque d'Angleterre :** courbes nominales, réelles et d'inflation implicite basées sur les gilts, plus des courbes OIS (nominales seulement). Les courbes de banques commerciales ont été abandonnées fin 2021. Publication « by noon on the following business day » en ZIP. La BoE précise : « **Our yield curve data are not available over an API** ». Méthode de Waggoner ajustée ; révisions possibles. Source : [BoE Yield curves](https://www.bankofengland.co.uk/statistics/yield-curves). Le package R `boe` lit ces ZIP (nominal, real, inflation, OIS) et l'archive des gilts nominaux remonterait à 1979. Source : [CRAN boe vignette](https://cran.r-project.org/web/packages/boe/vignettes/yield-curves.html).

#### 1.7 Écarts de crédit ICE BofA (FRED) : restrictions
- Sur FRED, la série `BAMLH0A0HYM2` affiche : « **Starting in April 2026, this series will only include 3 years of observations** ». L'avis de droits d'auteur dit : « Reproduction of this data in any form is prohibited except with the prior written permission of ICE Data Indices » et « you are not authorized or permitted to publish, distribute or otherwise furnish Top Level Data to any third-party ». La série est quotidienne (clôture) ; dernière valeur 3,20 au 2026-11-12. Source : [FRED BAMLH0A0HYM2](https://fred.stlouisfed.org/series/BAMLH0A0HYM2).
- **Conditions générales de l'API FRED :** une clé est obligatoire. Pour les séries appartenant à des tiers, toute utilisation autre que personnelle exige de « contact the data owner to obtain permission ». Mention obligatoire : « This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis ». Aucun quota chiffré n'apparaît dans les conditions. Source : [FRED API Terms of Use](https://fred.stlouisfed.org/docs/api/terms_of_use.html).
- **Alternative gratuite :** FINRA publie Corporate Debt Market Breadth et Sentiment (statistiques agrégées TRACE) sous un credential à 0 $. Source : [FINRA Fees](https://developer.finra.org/fees).

#### 1.8 Taux hypothécaires américains (Freddie Mac PMMS)
- **Fichier CSV complet :** `https://www.freddiemac.com/pmms/docs/PMMS_history.csv` contient les colonnes `date, pmms30, pmms30p, pmms15, pmms15p, pmms51, pmms51p, pmms51m, pmms51spread` et commence le 4/2/1971 **[testé 2026-11-14]**. Source : [PMMS_history.csv](https://www.freddiemac.com/pmms/docs/PMMS_history.csv).
- **Calendrier :** publication « weekly on Thursdays at 12 p.m. ET » ; moyenne des taux du jeudi précédent au mercredi ; publication le mercredi si le jeudi est férié. Le taux fixe 30 ans valait 7,11 % au 12 novembre 2026. Source : [Freddie Mac PMMS](https://www.freddiemac.com/pmms).

#### 1.9 Obligations indexées à l'inflation et points morts d'inflation
- **Canada :** `BD.CDN.RRB.DQ.YLD` (rendement réel long) et `BD.CDN.LONG.DQ.YLD` (nominal long) sont disponibles dans Valet **[testé 2026-11-14]**. Source : [Valet bond_yields_benchmark](https://www.bankofcanada.ca/valet/observations/group/bond_yields_benchmark/json?recent=1).
- **États-Unis :** la par real yield curve couvre les échéances de 5 à 30 ans (section 1.2). Source : [CSV Treasury real](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv).
- **Royaume-Uni :** la BoE publie une courbe d'inflation implicite. Source : [BoE Yield curves](https://www.bankofengland.co.uk/statistics/yield-curves).

### Inferences
- **Point mort canadien :** il peut s'approximer par `BD.CDN.LONG.DQ.YLD − BD.CDN.RRB.DQ.YLD` (environ 2,15 pts au 2026-11-12). L'approximation est fragile : les échéances ne sont pas identiques et aucune nouvelle RRB n'a été adjugée depuis septembre 2022 selon Valet, ce qui réduit la liquidité.
- **Courbe américaine :** la par yield curve du Trésor (gratuite, domaine public américain) remplace facilement les séries DGS* de FRED. Elle évite la dépendance à la clé FRED.
- **Dates d'observation et de publication à enregistrer dans l'OKF :**
  - BdC zéro-coupon : observation T, publiée environ T+14 jours, un jeudi à 16:30 ET.
  - NY Fed : observation T, publiée T+1 vers 8:00 ou 9:00 ET.
  - BCE YC : l'observation du 11-12 était la plus récente le samedi 11-14 ; cohérent avec une publication à midi CET le jour ouvré TARGET suivant.
  - PMMS : publié le jeudi midi pour la semaine du jeudi au mercredi.
  - Trésor : cotations de 15:30 ET ; le flux a été régénéré vers 20:00 ET le jour même (01:01 UTC).
- **ETF obligataires :** pour XBB, ZAG, ZST, AGG et TLT, les séries Valet (2 ans à long terme) et la courbe du Trésor (1 mois à 30 ans) suffisent pour construire des facteurs de duration et de taux. Les écarts ICE BofA ne doivent pas être redistribués dans la base de connaissances partagée : au mieux, un indicateur dérivé avec citation, sous réserve de la permission d'ICE.

### Gaps
- L'heure exacte de publication quotidienne des rendements de référence BdC (`BD.CDN.*`) et de CORRA (habituellement T+1 en matinée) n'a pas été trouvée dans une source officielle.
- Le texte exact des Terms of Use de la NY Fed (attribution, redistribution) n'a pas pu être extrait : la page renvoie du HTML sans contenu lisible.
- Le contenu précis du credential Public FINRA reste incertain : on ne sait pas si l'accès aux transactions TRACE corporatives est inclus ou s'il se limite aux agrégats, ni à quelles conditions (le tableau des frais est ambigu, « Limited »).
- Les tarifs actuels de MSRB (Subscription Services Price List) n'ont pas été consultés.
- Licence Freddie Mac PMMS : aucune clause de réutilisation n'a été trouvée sur la page PMMS (il y a un lien « Terms of Use » non lu).
- La gratuité ou non des séries Moody's sur FRED (DBAA, BAA10Y) comme alternatives aux écarts ICE n'a pas été vérifiée dans cette session.
- Le quota exact de l'API FRED (souvent cité à 120 requêtes/min) n'apparaît pas dans les conditions ; non vérifié. Les vintages ALFRED (`realtime_start`/`realtime_end`) n'ont pas été revérifiés.
- La BoE IADB (séries de rendements de gilts hors courbes) n'a pas été testée ; l'accès par bot est souvent bloqué.

---

## 2. Devises (FX) : sources officielles et commerciales, niveaux gratuits, licences

### Takeaway
Pour convertir CAD↔USD sans ambiguïté juridique, la meilleure source reste la BdC Valet (taux unique quotidien publié à 16:30 ET, attribution exigée). Frankfurter v2 est l'alternative à surveiller : gratuite, sans clé, sans quota, usage commercial permis, MCP officiel. Il agrège désormais 111 banques centrales, dont la BdC (taux identique à Valet au 2026-11-13), la BCE et la Fed H.10. Côté commercial, les niveaux gratuits sont faibles (100 à 1 500 requêtes/mois) et souvent non commerciaux ou non redistribuables. Twelve Data gratuit interdit tout affichage public.

### Cited Findings

#### 2.1 Banque du Canada : taux quotidien unique
- **Série et groupe :** `FXUSDCAD` « Daily average exchange rate », 1,4257 au 2026-11-13 **[testé 2026-11-14]**. Le groupe `FX_RATES_DAILY` décrit les taux comme « typically published once each business day by 16:30 (ET)… indicative rates only ». Source : [Valet FX_RATES_DAILY CSV](https://www.bankofcanada.ca/valet/observations/group/FX_RATES_DAILY/csv?start_date=2026-11-01).
- **Changement de mai 2026 :** la BdC a commencé à publier le ringgit, le zloty et le baht, et a cessé de publier le rouble et le riyal saoudien. Depuis 2017, le taux est quotidien ; avant, il y avait les taux « noon » et « closing ». Source : [BdC Daily exchange rates](https://www.bankofcanada.ca/rates/exchange/daily-exchange-rates/). Vérifié dans Valet : `FXRUBCAD` et `FXSARCAD` s'arrêtent au 2026-04-30 et `FXVNDCAD` au 2019-12-31 **[testé 2026-11-14]**. Source : [Valet FX_RATES_DAILY recent=1](https://www.bankofcanada.ca/valet/observations/group/FX_RATES_DAILY/json?recent=1).
- **Avertissement des conditions :** les taux de la BdC sont « indicative rates only… do not necessarily reflect the rates at which actual market transactions have been or could be conducted ». Source : [BdC Terms](https://www.bankofcanada.ca/terms/).

#### 2.2 BCE : taux de référence de l'euro
- `EXR/D.CAD.EUR.SP00.A` vaut 1,5758 CAD/EUR au 2026-11-13. Le titre complet indique « ECB reference exchange rate, Canadian dollar/Euro, 2.15 pm (C.E.T.) ». Sans clé ; CSV ou JSON **[testé 2026-11-14]**. Source : [appel EXR](https://data-api.ecb.europa.eu/service/data/EXR/D.CAD.EUR.SP00.A?lastNObservations=1&format=csvdata). Les vintages et la licence sont ceux de la section 1.6. Source : [ESCB reuse policy](https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html).

#### 2.3 Frankfurter (v2, multi-banques centrales)
- **Couverture :** « free exchange rate API for 219 currencies and 39 other assets from 111 central banks and official sources… Daily history goes back to 1948 ». API publique `api.frankfurter.dev`, sans clé, open source et auto-hébergeable (Docker). Taux de référence et non cotations en direct ; taux « mid-market ». Source : [frankfurter.dev](https://frankfurter.dev/).
- **Quotas :** « There are no quotas. Requests are rate-limited to prevent abuse, but there are no monthly or daily caps ». La mise en cache et le stockage local sont « encouraged ». Source : [frankfurter.dev FAQ](https://frankfurter.dev/).
- **Licence :** « Is the API free for commercial use? Yes. Blended rates are Frankfurter's own calculation… Direct queries to individual provider endpoints remain subject to each provider's terms ». Source : [frankfurter.dev FAQ](https://frankfurter.dev/).
- **Endpoints v2 :** `/v2/rates`, `/v2/rate/{base}/{quote}`, `providers=`, `expand=providers` (attribution par fournisseur), CSV et NDJSON. Le v1 est « deprecated… but remains available indefinitely ». Pour les données BCE : `/v2/providers/ecb/rates`. Les métaux précieux (XAU, XAG, XPT, XPD) viennent de plusieurs banques centrales. Source : [frankfurter.dev](https://frankfurter.dev/).
- **Fournisseurs (`/v2/providers`, 111 entrées) :**
  - `BOC` : « indicative rate », début 2017-01-03, `terms_url` pointant vers les conditions BdC.
  - `ECB` : début 1999-01-04.
  - `FRED` (H.10) : début 1971-01-04, « publish_cadence: weekly ».
  - `/v2/rate/usd/cad?providers=boc` renvoie 1,4257 au 2026-11-13, identique à Valet.
  - `api.frankfurter.app/latest` redirige (301) vers `https://api.frankfurter.dev/v1/latest`.
  **[testé 2026-11-14]**. Sources : [providers](https://api.frankfurter.dev/v2/providers), [rate BOC](https://api.frankfurter.dev/v2/rate/usd/cad?providers=boc).
- **MCP officiel :** « Add https://mcp.frankfurter.dev/ as a remote HTTP server. No API key or registration required ». Source : [Frankfurter MCP](https://frankfurter.dev/mcp/).

#### 2.4 Fed H.10 (taux de change de la Réserve fédérale)
- **Data Download Program :** export CSV ; série CAD `H10/H10/RXI_N.B.CA`. Dernière observation 2026-11-06 (1,4106) alors que la diffusion était datée du 9 novembre 2026, donc hebdomadaire **[testé 2026-11-14]**. Sources : [DDP CSV](https://www.federalreserve.gov/datadownload/Output.aspx?rel=H10&series=60f32914ab61dfab590e0e470153e3ae&lastobs=3&from=&to=&filetype=csv&label=include&layout=seriescolumn), [H.10 current](https://www.federalreserve.gov/releases/h10/current/).
- **⚠️ Retrait du DDP :** « On March 31, 2027, the preformatted data package feature in the Data Download Program (DDP) will be retired in preparation for the July 1, 2027, DDP page removal ». Les utilisateurs sont renvoyés vers FRED. Source : [H.10 current](https://www.federalreserve.gov/releases/h10/current/).

#### 2.5 ExchangeRate-API (open.er-api.com et clé gratuite)
- **Accès ouvert sans clé :** `https://open.er-api.com/v6/latest/USD` renvoie `time_last_update_utc` et `time_next_update_utc` (dernière mise à jour Sun, 15 Nov 2026 00:02:32 +0000) ainsi que des liens vers la doc et les conditions **[testé 2026-11-14]**. Source : [open.er-api.com](https://open.er-api.com/v6/latest/USD).
- **Conditions de l'accès ouvert :** attribution exigée ; cache permis ; usage personnel ou commercial permis pour la conversion, mais « **not allowed to re-distribute it** ». Mise à jour une fois par jour. Au-delà de la limite, réponses HTTP 429 pendant 20 minutes. Source : [ExchangeRate-API docs free](https://www.exchangerate-api.com/docs/free).
- **Plans :** gratuit avec clé à 1 500 requêtes/mois (mise à jour quotidienne, sans attribution) ; Pro à 10 $/mois (30 000 requêtes, mise à jour horaire) ; tarifs annuels de 100 $ (Pro), 300 $ (Business) et 700 $ (Volume). Source : [ExchangeRate-API pricing](https://www.exchangerate-api.com/#pricing).

#### 2.6 Open Exchange Rates
- **Gratuit :** 1 000 requêtes/mois, mises à jour horaires, base USD seulement. Developer à 12 $/mois (10 000 requêtes) ; Enterprise à 47 $ (100 000) ; Unlimited à 97 $. Source : [OXR signup/pricing](https://openexchangerates.org/signup).
- **Conditions :** la licence a été remplacée en 2013 par les Terms and Conditions. Les clauses de redistribution n'ont pas été lues (voir Gaps). Source : [OXR License](https://openexchangerates.org/license).

#### 2.7 Produits APILayer : exchangerate.host et Fixer
- **exchangerate.host :** « a product built and maintained by APILayer ». Gratuit à **100 requêtes/mois**, mises à jour quotidiennes, **usage non commercial** ; Basic à 14,99 $/mois (10 000). Historique de fin de journée disponible à 00:05 GMT, « time stamped at one second before midnight ». Source : [exchangerate.host pricing](https://exchangerate.host/product). L'ancien endpoint sans clé `api.exchangerate.host/latest` redirige (301) vers `docs.apilayer.com/exchangerate/…` **[testé 2026-11-14]**. Source : [appel testé](https://api.exchangerate.host/latest).
- **Fixer :** gratuit à 100 appels/mois, horaire, non commercial, sans support ; Basic à 14,99 $/mois (10 000) ; Professional à 59,99 $ ; « an APILayer product ». Source : [Fixer pricing](https://fixer.io/product).

#### 2.8 CurrencyAPI (currencyapi.com)
- **Gratuit :** 300 requêtes/mois, 10 requêtes/min, mises à jour quotidiennes, historique inclus. L'usage commercial exige un plan payant : Small à 10,83 $/mois en facturation annuelle (129,90 $/an, 15 000 requêtes, horaire) ; Pro à 299,90 $/an (100 000 requêtes, 15 min). Le titre de la page indique « Paid Plans from $12.99 ». Source : [currencyapi pricing](https://currencyapi.com/pricing/).

#### 2.9 fawazahmed0 exchange-api (jsDelivr)
- **Accès :** licence **CC0-1.0**, « No Rate limits », « Daily Updated ». URL `https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{date}/v1/currencies/{base}.json` ; secours Cloudflare `https://{date}.currency-api.pages.dev/v1/…`. L'auteur recommande d'implémenter ce secours. Source : [GitHub exchange-api](https://github.com/fawazahmed0/exchange-api).
- **Test :** données datées du 2026-11-14 ; inclut des cryptos (1inch, aave…) **[testé 2026-11-14]**. Source : [jsDelivr usd.min.json](https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.min.json).

#### 2.10 Alpha Vantage (FX)
- **Gratuit :** 25 requêtes/jour pour la plupart des jeux de données ; illimité pour les projets open source ou éducatifs vérifiés. Source : [Alpha Vantage support](https://www.alphavantage.co/support/).
- **Fonctions FX :** `FX_DAILY`, `FX_WEEKLY`, `FX_MONTHLY` et `CURRENCY_EXCHANGE_RATE`. `FX_INTRADAY` est marqué **Premium**. Source : [Alpha Vantage documentation](https://www.alphavantage.co/documentation/).

#### 2.11 Twelve Data
- **Plan Basic à 0 $ :** 8 crédits/min (800 par jour). « **Internal non-display usage** — Data may be used internally for testing, evaluation, or development purposes only. The data cannot be displayed to users, shared externally, or used in production systems ». Plans payants affichés à 79 $, 229 $ et 999 $ par mois (noms non capturés). Source : [Twelve Data pricing](https://twelvedata.com/pricing).

#### 2.12 OANDA
- **Exchange Rates API :** pas de niveau gratuit permanent, essai de 7 jours. Prix cités par des concurrents (environ 450 $/mois ou 4 850 $/an, chiffres contradictoires selon les sources, peu fiables). L'API v20 est une API de trading liée à un compte fxTrade, pas une source de données. Sources : [allratestoday, is OANDA API free](https://allratestoday.com/blog/is-oanda-api-free/), [currencyfreaks blog](https://currencyfreaks.com/blog/Currency-Conversion-Api-Oanda-Pricing).

### Inferences
- **Recommandation pour l'agent A5 :** prendre la BdC Valet (`FXUSDCAD`, plus `FXEURCAD` si besoin) comme taux « officiel » de conversion CAD↔USD de la base de connaissances, avec observation date = `d` et publication ≈ `d` 16:30 ET. Frankfurter (`providers=boc`) sert de miroir sans quota et de source pour les autres devises ; ExchangeRate-API (accès ouvert) sert de contrôle croisé qui fournit des horodatages de mise à jour.
- **Sources à exclure de la base partagée :** Twelve Data Basic (pas d'affichage), exchangerate.host et Fixer gratuits (non commerciaux, 100 requêtes/mois) et l'accès ouvert ExchangeRate-API (redistribution interdite) ne conviennent pas à une base redistribuée à d'autres agents ou affichée dans l'interface.
- **fawazahmed0 :** pratique (CC0, sans limite) mais la provenance des taux n'est pas documentée. Le brief exige de documenter l'origine : à éviter comme source primaire.

### Gaps
- Les Terms and Conditions d'Open Exchange Rates (redistribution, affichage) n'ont pas été lues.
- La licence et les sources des taux de CurrencyAPI ne sont pas documentées dans la page de tarifs.
- La Fed H.10 décrit des « noon buying rates in New York » : non revérifié dans cette session.
- Les tarifs officiels d'OANDA n'ont pas été consultés directement (seulement des blogs concurrents).
- Les Terms d'Alpha Vantage (redistribution des données FX gratuites) n'ont pas été lus.

---

## 3. Matières premières et or

### Takeaway
L'or est le point juridiquement le plus délicat. Le LBMA Gold Price est un indice de référence administré par IBA (ICE) : usage commercial et redistribution sous licence. FRED l'a retiré en janvier 2022 et le LBMA a placé ses tableaux historiques derrière un portail membres en novembre 2025. Les options gratuites et redistribuables sont des moyennes mensuelles (FMI PCPS, Banque mondiale Pink Sheet), le BCPI de la BdC, les cours de l'or publiés par certaines banques centrales via Frankfurter, l'EIA pour l'énergie (domaine public) et, en quotidien, des API commerciales à petits quotas (GoldAPI 150 requêtes/mois, metals.dev 100, Alpha Vantage 25/jour).

### Cited Findings

#### 3.1 LBMA Gold Price (IBA) : licence
- **Déplacement des tableaux historiques :** à partir de la semaine du 24 novembre 2025, ils passent du site public au **Members' Portal**. L'accès est réservé aux détenteurs de licence et aux usages non commerciaux ou éducatifs, sur autocertification vérifiée par le LBMA. Le prix quotidien le plus récent reste publié le jour ouvrable suivant, en accès libre. « Any use of the benchmark for commercial purposes » exige une licence IBA. Platine et palladium sont administrés par la LME. Source : [LBMA, benchmark prices data tables are moving](https://www.lbma.org.uk/articles/lbma-benchmark-prices-data-tables-are-moving).
- **Licences IBA :** licence d'usage (valorisation, produits financiers), licence de redistribution (« real-time or delayed ») et licence d'émetteur d'ETP pour les ETF qui s'y réfèrent. Barème de frais 2026 publié. Sources : [ICE IBA licensing](https://www.ice.com/iba/licensing), [IBA fee schedule 2026](https://www.ice.com/publicdocs/IBA_MLA_Licensing_Data_Fee_Schedule_2026.pdf).
- **Retrait de FRED :** « on January 31, 2022, FRED will no longer include data from ICE Benchmark Administration Limited (IBA) ». Les séries or et argent LBMA (dont `GOLDAMGBD228NLBM`) ont été supprimées de l'API et des autres services. Source : [FRED news, IBA data to be removed](https://news.research.stlouisfed.org/2022/01/ice-benchmark-administration-ltd-iba-data-to-be-removed-from-fred/).
- **World Gold Council :** il a lui aussi retiré l'historique du LBMA Gold Price à la demande d'IBA. Source : [gold.org gold prices](https://www.gold.org/goldhub/data/gold-prices).
- **DBnomics :** il a retiré les jeux LBMA. Source : [DBnomics forum](https://dbnomics.discourse.group/t/removal-of-lbma-datasets/999).
- **Platts :** un avis annonce l'arrêt de la republication des prix or et argent LBMA (année probablement 2026, d'après l'URL ; non confirmée). Source : [S&P Global Platts subscriber note](https://www.spglobal.com/energy/en/pricing-benchmarks/our-methodology/subscriber-notes/070926-platts-to-stop-republishing-lmba-gold-and-silver-prices-by-july-17).

#### 3.2 FMI : Primary Commodity Prices (PCPS)
- **Accès :** API SDMX 2.1 sans clé, `https://api.imf.org/external/sdmx/2.1/data/IMF.RES,PCPS/{COUNTRY}.{INDICATOR}.{DATA_TRANSFORMATION}.{FREQUENCY}`. Dataflow `IMF.RES:PCPS`, version 9.0.0.
- **Or mensuel :** `G001.PGOLD.USD.M` donne 4 419,42 en 2026-M08, 4 326,98 en 2026-M09 et 4 102,37 en 2026-M10 (USD).
- **Métadonnées utiles :** `PUBLICATION_DATE="2026-11-10T18:30:55Z"` et `UPDATE_DATE`, ce qui permet de distinguer observation et publication. `LICENSE="© International Monetary Fund Copyright. All Rights Reserved. https://www.imf.org/external/terms.htm"`. Citation suggérée fournie. Description : « 70+ commodities… monthly… dating back to the 1990s… All benchmark prices are denominated in USD ».
  **[testé 2026-11-14]**. Sources : [appel PCPS or](https://api.imf.org/external/sdmx/2.1/data/IMF.RES,PCPS/G001.PGOLD.USD.M?startPeriod=2026-08), [dataflow](https://api.imf.org/external/sdmx/3.0/structure/dataflow/IMF.RES/PCPS/+), [IMF PCPS dataset page](https://data.imf.org/en/datasets/IMF.RES:PCPS).
- **Mise à jour :** mensuelle, avec un fichier Excel et une documentation technique. Source : [IMF Primary Commodity Prices](https://www.imf.org/en/Research/commodity-prices).

#### 3.3 Banque mondiale : Pink Sheet (CMO)
- **Fichiers :** `https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx` (mensuel ; une version annuelle existe aussi) et le PDF « CMO-Pink-Sheet-November-2026 ». « Next update: December 2, 2026 ». La page renvoie à « Data Access and Licensing » vers `datacatalog.worldbank.org/public-licenses#cc-by`. Sources : [World Bank Commodity Markets](https://www.worldbank.org/en/research/commodity-markets), [Terms of use for datasets](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets).
- **Pas d'API officielle :** fichier XLSX seulement (voir Gaps).

#### 3.4 EIA (WTI, Brent, gaz naturel)
- **Accès :** API v2 `https://api.eia.gov/v2/{route}/data/?api_key=…`, clé gratuite par courriel. Sans clé, l'API répond `API_KEY_MISSING` **[testé 2026-11-14]**. Sources : [appel testé](https://api.eia.gov/v2/petroleum/pri/spt/data/?frequency=daily&data[0]=value&facets[series][]=RWTC&sort[0][column]=period&sort[0][direction]=desc&length=1), [EIA API documentation](https://www.eia.gov/opendata/documentation.php).
- **Limites :** maximum de 5 000 lignes par requête. Il faut réguler les requêtes par seconde et par heure, faute de quoi la clé est « automatically but temporarily suspended ». Aucun chiffre n'est publié. Source : [EIA API documentation](https://www.eia.gov/opendata/documentation.php).
- **Licence :** « U.S. government publications are in the public domain… You may use and/or distribute any of our data » ; un remerciement est demandé. Source : [EIA Copyrights and Reuse](https://www.eia.gov/about/copyrights_reuse.php).

#### 3.5 Indice des prix des produits de base de la BdC (BCPI)
- **Valet :** `M.BCPI` (« Monthly BCPI Total - v52673496 ») vaut 731,58 en 2026-10. Groupes `BCPI_WEEKLY`, `BCPI_MONTHLY`, `BCPI_ANNUAL` et `BCPI_WEIGHTS` **[testé 2026-11-14]**. Sources : [Valet M.BCPI](https://www.bankofcanada.ca/valet/observations/M.BCPI/json?recent=1), [liste des groupes](https://www.bankofcanada.ca/valet/lists/groups/json).

#### 3.6 API commerciales pour les métaux précieux
- **GoldAPI.io :** gratuit à 150 requêtes/mois ; XAU, XAG, XPT, XPD dans 72 devises, dont XAU/CAD ; historique quotidien ; WebSocket (1 connexion). Pro à 99 $/mois (illimité, sans MCP) ; Business à 169 $/mois (avec MCP). Sources des prix en direct : « FOREX, SAXO, OANDA and IDC ». Historique des fixings LBMA depuis 1968. Source : [goldapi.io](https://www.goldapi.io/).
- **metals.dev :** gratuit à 100 requêtes/mois, « maximum delay of 60 seconds » ; endpoints « Spot Metal Prices » et « LBMA Metal Prices ». Paliers payants de 2 000 à 500 000 requêtes/mois ; prix dans le JSON de la page : 1,79 $, 9,99 $, 19,99 $, 39,99 $ par mois… (correspondance avec les paliers inférée). Source : [metals.dev pricing](https://metals.dev/pricing).
- **Metals-API :** aucun plan gratuit affiché. Bronze à 39,99 $/mois (5 000 appels, mises à jour 10 min) ; Silver à 79,99 $ (10 000 appels, avec endpoints historiques LME et LBMA) ; Gold à 149,99 $ ; Platinum à 219,99 $. Source : [Metals-API pricing](https://metals-api.com/pricing).
- **MetalpriceAPI :** 100 requêtes/mois gratuites. Source : [metalpriceapi.com](https://www.metalpriceapi.com).
- **Alpha Vantage (matières premières) :** `GOLD_SILVER_SPOT`, `GOLD_SILVER_HISTORY` (quotidien, hebdomadaire, mensuel), `WTI`, `BRENT`, `NATURAL_GAS`, `COPPER` et `ALL_COMMODITIES`. WTI vient de l'EIA via FRED, avec la mention « By using this data feed, you agree to be bound by the FRED® API Terms of Use ». Source : [Alpha Vantage documentation](https://www.alphavantage.co/documentation/).
- **Frankfurter :** « Several central banks publish daily rates for gold (XAU)… per troy ounce ». Source : [frankfurter.dev FAQ](https://frankfurter.dev/).

#### 3.7 CME/COMEX, Nasdaq Data Link, USDA
- **CME :** cotations retardées « at least 10 minutes » en affichage web uniquement, sans API gratuite. DataMine est payant (identifiants requis). Sources : [CME Delayed Quotes](https://www.cmegroup.com/market-data/delayed-quotes.html), [CME DataMine List API](https://www.cmegroup.com/datamine/datamine-list-api.html).
- **Nasdaq Data Link :** l'API renvoie **HTTP 403 (Incapsula)** à un client automatisé sur `LBMA/GOLD` **[testé 2026-11-14]**. Le package Python `nasdaq-data-link` n'a pas été mis à jour depuis le 2022-08-29. Sources : [appel testé](https://data.nasdaq.com/api/v3/datasets/LBMA/GOLD.json?rows=1), [PyPI nasdaq-data-link](https://pypi.org/pypi/nasdaq-data-link/json).
- **USDA AMS MyMarketNews (MARS API) :** clé personnelle obtenue après inscription (« My Profile »). Source : [MyMarketNews basic instructions](https://mymarketnews.ams.usda.gov/mars-api/getting-started/basic-instructions).

### Inferences
- **Or quotidien redistribuable :** pour les ETF GLD et IAU, il est plus simple et plus sûr juridiquement de ne pas stocker de prix LBMA. On utilise le prix de clôture des ETF eux-mêmes (autre famille de sources) et, comme facteur macro, le PGOLD mensuel du FMI ou la Pink Sheet, avec citation. Si un prix spot quotidien est indispensable, prendre l'or publié par une banque centrale via Frankfurter (vérifier les `terms_url` du fournisseur) ou GoldAPI ou metals.dev en usage interne, sans redistribution, et sous réserve de leurs conditions (non lues).
- **Pétrole :** l'EIA (domaine public) est la source primaire. L'endpoint Alpha Vantage WTI n'est qu'un relais de FRED.

### Gaps
- Licence de la Pink Sheet : la page renvoie vers l'ancre CC BY du catalogue, mais aucune mention CC BY 4.0 explicite n'a été lue sur la fiche du jeu.
- Les conditions d'utilisation des données du FMI (`imf.org/external/terms.htm`, HTTP 403 pour les bots) n'ont pas été lues. Le champ LICENSE indique « All Rights Reserved », ce qui contredit l'usage libre généralement admis. À vérifier.
- Le statut actuel des jeux gratuits de matières premières sur Nasdaq Data Link n'a pas pu être vérifié (blocage du bot).
- Les CGU de GoldAPI.io et metals.dev (redistribution, usage commercial) ne sont pas lues ; la correspondance palier/prix de metals.dev n'est pas certaine.
- Les heures de publication de PGOLD (FMI) et de la Pink Sheet sont déduites (vers le 10 du mois pour le FMI, d'après PUBLICATION_DATE ; 2 décembre pour la Banque mondiale).
- Les identifiants EIA de séries Brent et Henry Hub (RBRTE, RNGWHHD) n'ont pas été testés : une clé est requise.

---

## 4. Clients Python et serveurs MCP

### Takeaway
Il existe des MCP officiels pour Frankfurter (sans clé), Alpha Vantage (clé gratuite) et Twelve Data (connexion OAuth au compte). Pour FRED, FINRA et la BdC, il n'existe que des serveurs communautaires. Côté Python, `sdmx1` (actif, 2026) couvre la BCE et le FMI. `pyvalet`, `fredapi`, `ecbdata` et `alpha_vantage` sont utilisables mais peu mis à jour ; pour la BdC, appeler Valet directement est trivial.

### Cited Findings
- **Versions PyPI au 2026-11-14 [testé 2026-11-14] :**

  | Package | Version | Date |
  |---|---|---|
  | `fredapi` | 0.5.2 | 2024-05-05 |
  | `pyfredapi` | 0.10.2 | 2025-07-27 |
  | `pyvalet` (« BoC Valet API Wrapper ») | 1.1.1 | 2024-01-31 |
  | `ecbdata` | 0.1.1 | 2025-03-23 |
  | `sdmx1` | 2.28.0 | 2026-10-18 |
  | `pandasdmx` | 1.10.0 | 2023-02-25 (inactif) |
  | `twelvedata` | 1.4.0 | 2026-04-27 |
  | `alpha_vantage` | 3.0.0 | 2024-07-18 |
  | `eiapy` | 0.1.6 | 2022-02-18 |
  | `nasdaq-data-link` | 1.0.4 | 2022-08-29 |
  | `wbgapi` | 1.0.14 | 2026-02-27 |
  | `pandas-datareader` | 0.11.1 | 2026-06-24 |
  | `fred-mcp-server` | 0.2.2 | 2026-04-05 |

  Sources : [PyPI sdmx1](https://pypi.org/pypi/sdmx1/json), [PyPI pyvalet](https://pypi.org/pypi/pyvalet/json), [PyPI fredapi](https://pypi.org/pypi/fredapi/json), [PyPI ecbdata](https://pypi.org/pypi/ecbdata/json), [PyPI twelvedata](https://pypi.org/pypi/twelvedata/json), [PyPI fred-mcp-server](https://pypi.org/pypi/fred-mcp-server/json).
- **MCP Frankfurter :** `https://mcp.frankfurter.dev/`, sans clé. Source : [Frankfurter MCP](https://frankfurter.dev/mcp/).
- **MCP Alpha Vantage (officiel) :** `https://mcp.alphavantage.co/mcp` ; l'ancienne forme `?apikey=` est dépréciée au profit d'une authentification par fenêtre contextuelle. Source : [mcp.alphavantage.co](https://mcp.alphavantage.co/).
- **MCP Twelve Data (officiel) :** `https://mcp.twelvedata.com/mcp`, connexion par navigateur au compte Twelve Data. Les conditions d'usage du plan Basic (section 2.11) restent applicables. Source : [GitHub twelvedata/mcp](https://github.com/twelvedata/mcp).
- **MCP FRED (communautaire) :** stefanoamorelli/fred-mcp-server, non affilié à la Fed, clé FRED requise. Source : [glama, fred-mcp-server](https://glama.ai/mcp/servers/stefanoamorelli/fred-mcp-server/schema).
- **MCP BdC (communautaire) :** bank-of-canada-mcp (koleharv) et boc-valet-mcp (Python), sans clé. Pipeworx propose une passerelle hébergée plafonnée à 50 appels/jour en anonyme. Sources : [mcpmarket Bank of Canada](https://mcpmarket.com/server/bank-of-canada-1), [Claude Marketplaces pipeworx bank-of-canada](https://claudemarketplaces.com/mcp/io.github.pipeworx-io/bank-of-canada).
- **MCP FINRA (communautaire) :** cmaurer/finra-mcp-server, identifiants de l'API Console requis. Source : [mcpservers.org finra-mcp-server](https://mcpservers.org/servers/cmaurer/finra-mcp-server.git).
- **MCP GoldAPI :** inclus dans le plan Business (le plan gratuit partage une allocation mensuelle). Source : [goldapi.io](https://www.goldapi.io/).
- **Package R `boe` :** il lit les ZIP de courbes de la BoE. Source : [CRAN boe](https://cran.r-project.org/web/packages/boe/vignettes/yield-curves.html).

### Inferences
- **Pour A5 :** un client `httpx` maison (Valet, NY Fed, Trésor, Fiscal Data, Frankfurter, ECB et IMF via `sdmx1`) évite des dépendances peu maintenues. Les MCP communautaires ne doivent pas servir de source primaire documentée : il faut tracer l'URL officielle d'origine.
- **`eiapy` :** sa date (2022) laisse penser qu'il vise l'APIv1 ; préférer des appels directs à l'API v2.

### Gaps
- Le maintien actif des MCP communautaires (BdC, FRED, FINRA) n'a pas été évalué.
- La couverture effective de l'API FMI 2025+ par `sdmx1` n'a pas été testée.

---

## 5. Pièges 2025–2026 (niveaux gratuits supprimés, migrations, fermetures)

### Takeaway
Les ruptures récentes touchent surtout les données sous licence ICE (écarts ICE BofA plafonnés à 3 ans sur FRED depuis avril 2026 ; or LBMA retiré du public), les migrations de portails (Fed DDP retiré en 2027, documentation TreasuryDirect déplacée, nouvelle API FMI, Frankfurter v2) et le basculement de services gratuits vers APILayer (exchangerate.host). Il faut aussi tenir compte des changements de couverture BdC (devises ajoutées ou retirées en mai 2026).

### Cited Findings
- **FRED et ICE BofA :** les séries sont plafonnées à 3 ans d'observations depuis avril 2026 ; reproduction interdite sans permission écrite. Source : [FRED BAMLH0A0HYM2](https://fred.stlouisfed.org/series/BAMLH0A0HYM2).
- **LBMA :** l'historique est passé derrière le Members' Portal (semaine du 24 novembre 2025). Source : [LBMA article](https://www.lbma.org.uk/articles/lbma-benchmark-prices-data-tables-are-moving). L'or LBMA a disparu de FRED depuis le 31 janvier 2022. Source : [FRED news](https://news.research.stlouisfed.org/2022/01/ice-benchmark-administration-ltd-iba-data-to-be-removed-from-fred/).
- **Fed Data Download Program :** les paquets préformatés sont retirés le 31 mars 2027 et la page disparaît le 1er juillet 2027. Source : [H.10 current](https://www.federalreserve.gov/releases/h10/current/).
- **TreasuryDirect :** la documentation des Web APIs a été déplacée vers le portail du Fiscal Service ; `TA_WS` répond toujours. Sources : [ancienne page](https://www.treasurydirect.gov/webapis/webapisecurities.htm), [TA_WS testé](https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json&type=Note&pagesize=1).
- **Frankfurter :** `api.frankfurter.app` redirige (301) vers `api.frankfurter.dev/v1`. Le v1 est déprécié au profit du v2, qui mélange les fournisseurs par défaut : il faut passer `providers=ecb` ou `boc` pour obtenir des taux officiels. Sources : [frankfurter.dev](https://frankfurter.dev/), [appel testé](https://api.frankfurter.app/latest).
- **exchangerate.host :** désormais APILayer, clé requise, 100 requêtes/mois non commerciales ; l'ancien endpoint sans clé redirige vers la doc APILayer. Sources : [exchangerate.host pricing](https://exchangerate.host/product), [appel testé](https://api.exchangerate.host/latest).
- **Metals-API :** aucun plan gratuit affiché (à partir de 39,99 $/mois). Source : [Metals-API pricing](https://metals-api.com/pricing).
- **Twelve Data :** le plan gratuit est limité à un usage interne sans affichage. Source : [Twelve Data pricing](https://twelvedata.com/pricing).
- **Alpha Vantage :** 25 requêtes/jour ; FX intrajournalier premium. Sources : [AV support](https://www.alphavantage.co/support/), [AV documentation](https://www.alphavantage.co/documentation/).
- **BdC Valet :** RUB et SAR arrêtés après le 2026-04-30 ; MYR, PLN et THB ajoutés en mai 2026. Avec `recent=N` sur un groupe, les séries arrêtées renvoient d'anciennes dates (VND 2019-12-31), ce qui fausse le « dernier jour » si on lit la dernière ligne naïvement **[testé 2026-11-14]**. Sources : [BdC Daily exchange rates](https://www.bankofcanada.ca/rates/exchange/daily-exchange-rates/), [Valet FX_RATES_DAILY recent=1](https://www.bankofcanada.ca/valet/observations/group/FX_RATES_DAILY/json?recent=1).
- **FMI :** la nouvelle API SDMX (`api.imf.org/external/sdmx/2.1|3.0`) est active ; dataflow PCPS mis à jour en 2025 (`lastUpdatedAt` 2025-06-16). Source : [IMF dataflow PCPS](https://api.imf.org/external/sdmx/3.0/structure/dataflow/IMF.RES/PCPS/+).
- **Blocages anti-bot :** FRED (`fredgraph.csv`) n'a pas répondu à `curl` dans cet environnement (HTTP 000). Nasdaq Data Link a renvoyé 403 (Incapsula) **[testé 2026-11-14]**. Sources : [fredgraph BAMLH0A0HYM2](https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2), [Nasdaq LBMA/GOLD](https://data.nasdaq.com/api/v3/datasets/LBMA/GOLD.json?rows=1).

### Inferences
- **Grille « date d'observation / date de publication » pour l'OKF :**
  - **Publication explicite dans la réponse :** FMI (PUBLICATION_DATE, UPDATE_DATE), BCE (vintages par `includeHistory` et `updatedAfter`), ExchangeRate-API (`time_last_update_utc`), NY Fed (`revisionIndicator`), FINRA (`tradeDate` et `tradeReportDate`).
  - **Publication implicite (déduite du calendrier) :** BdC Valet (date d'observation seule), Frankfurter (date seule ; `publish_cadence` par fournisseur), Trésor (`<updated>` au niveau du flux), PMMS (jeudi midi), BdC zéro-coupon (décalage de 2 semaines).
- **Cache local systématique :** il est encouragé par Frankfurter et permis par ExchangeRate-API. Il évite les blocages et respecte la clause BdC sur le contournement des limites de requêtes.

### Gaps
- Aucune annonce officielle de retrait du niveau gratuit d'Alpha Vantage, de Frankfurter ou de l'accès ouvert ExchangeRate-API pour 2026 n'a été trouvée. L'absence d'annonce n'est pas une preuve de stabilité.
- La date de retrait des anciennes URL `TA_WS` de TreasuryDirect est inconnue.
