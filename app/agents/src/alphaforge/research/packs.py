"""Registre des hôtes, paquets de sources et sujets des experts.

Sources : Brain, « Sources de données », « Collecte Web et presse » et « Signaux prospectifs » (2026-11-15), et la
liste ``reports/web-sources-general-okf.html`` du volet recherche. Phase 1 : sources sans clé seulement.

- ``HOSTS`` : licence, lien de la licence et texte d'attribution de chaque hôte, écrits par le code dans chaque
  constat (jamais par le modèle), plafond de requêtes par session et exception assumée au robots.txt.
- ``PACKS`` : un paquet = des hôtes permis, des sources de recherche (``search_source``), des points d'accès connus
  et les pièges notés par la recherche. Un chercheur ne reçoit que les paquets de sa mission.
- ``SUBJECTS`` : les sept experts, leurs paquets, leur plan permanent de veille et leurs plafonds.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HostInfo:
    licence: str
    licence_url: str
    attribution: str
    max_requests: int = 25
    robots_exception: bool = False
    note: str = ""


_STATCAN = HostInfo(
    "Licence ouverte de Statistique Canada",
    "https://www.statcan.gc.ca/en/terms-conditions/open-licence",
    "Source : Statistique Canada",
    max_requests=40,
)
_OGL = HostInfo(
    "Licence du gouvernement ouvert – Canada 2.0",
    "https://open.canada.ca/en/open-government-licence-canada",
    "Contient de l'information visée par la Licence du gouvernement ouvert – Canada",
)
_SEC = HostInfo(
    "Données publiques de la SEC (accès équitable : 10 requêtes par seconde, User-Agent déclaré)",
    "https://www.sec.gov/about/developer-resources",
    "Source : U.S. Securities and Exchange Commission, EDGAR",
    max_requests=40,
    note="Exige ALPHAFORGE_CONTACT_EMAIL dans le User-Agent, sinon 403.",
)
_FED_PUBLIC = HostInfo(
    "Domaine public (Réserve fédérale)", "https://www.federalreserve.gov/disclaimer.htm", "Source : Federal Reserve"
)
_PERSONAL = "Usage personnel et non commercial (position de l'équipe du 2026-11-15)"

HOSTS: dict[str, HostInfo] = {
    # Canada
    "www.bankofcanada.ca": HostInfo(
        "Conditions de la Banque du Canada (copie et distribution avec attribution; contenu de tiers exclu)",
        "https://www.bankofcanada.ca/terms/",
        "Source : Banque du Canada",
        max_requests=40,
    ),
    "www150.statcan.gc.ca": _STATCAN,
    "open.canada.ca": _OGL,
    "data-donnees.ec.gc.ca": _OGL,
    "gazette.gc.ca": HostInfo(
        "Gazette du Canada (gouvernement du Canada)",
        "https://www.canada.ca/en/transparency/terms.html",
        "Source : Gazette du Canada",
    ),
    "www.parl.ca": HostInfo(
        "Parlement du Canada (LEGISinfo)",
        "https://www.parl.ca/legisinfo/en/overview",
        "Source : LEGISinfo, Parlement du Canada",
    ),
    # États-Unis et international
    "fred.stlouisfed.org": HostInfo(
        "Conditions de FRED (séries de tiers soumises à leur propriétaire)",
        "https://fred.stlouisfed.org/docs/api/terms_of_use.html",
        "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.",
    ),
    "home.treasury.gov": HostInfo(
        "Département du Trésor des États-Unis (domaine public probable)",
        "https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics",
        "Source : U.S. Department of the Treasury",
    ),
    "markets.newyorkfed.org": HostInfo(
        "Conditions de la Fed de New York",
        "https://www.newyorkfed.org/terms-of-use",
        "Source : Federal Reserve Bank of New York",
    ),
    "www.federalreserve.gov": _FED_PUBLIC,
    "www.philadelphiafed.org": HostInfo(
        "Fed de Philadelphie (conditions non vérifiées)",
        "https://www.philadelphiafed.org/",
        "Source : Federal Reserve Bank of Philadelphia",
    ),
    "www.atlantafed.org": HostInfo(
        "Fed d'Atlanta (conditions non vérifiées)",
        "https://www.atlantafed.org/cqer/research/gdpnow",
        "Source : Federal Reserve Bank of Atlanta, GDPNow",
    ),
    "www.clevelandfed.org": HostInfo(
        "Fed de Cleveland (conditions non vérifiées)",
        "https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting",
        "Source : Federal Reserve Bank of Cleveland",
    ),
    "www.frbsf.org": HostInfo(
        "Fed de San Francisco (conditions non vérifiées)",
        "https://www.frbsf.org/",
        "Source : Federal Reserve Bank of San Francisco",
    ),
    "www.federalregister.gov": HostInfo(
        "Contenu fédéral américain",
        "https://www.federalregister.gov/reader-aids/developer-resources/rest-api",
        "Source : Federal Register",
    ),
    "api.imf.org": HostInfo(
        "Conditions du FMI (attribution; téléchargement massif automatisé interdit sans accord)",
        "https://www.imf.org/en/about/copyright-and-terms",
        "Source : Fonds monétaire international",
        max_requests=15,
    ),
    "sdmx.oecd.org": HostInfo(
        "CC BY 4.0 (OCDE)", "https://www.oecd.org/en/about/terms-conditions.html", "Source : OCDE", max_requests=3
    ),
    "data-api.ecb.europa.eu": HostInfo(
        "Politique d'utilisation du SEBC (citation, données non modifiées)",
        "https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html",
        "Source : Banque centrale européenne",
    ),
    "www.ecb.europa.eu": HostInfo(
        "Politique d'utilisation du SEBC",
        "https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html",
        "Source : Banque centrale européenne",
    ),
    "api.worldbank.org": HostInfo(
        "CC BY 4.0 (Banque mondiale)", "https://data.worldbank.org/summary-terms-of-use", "Source : Banque mondiale"
    ),
    "stats.bis.org": HostInfo(
        "Conditions de la BRI (usage libre sans suggérer d'aval)",
        "https://www.bis.org/terms_conditions.htm",
        "Source : Banque des règlements internationaux",
    ),
    "api.frankfurter.dev": HostInfo(
        "Frankfurter (usage commercial permis; taux soumis aux conditions de chaque banque centrale)",
        "https://frankfurter.dev/",
        "Source : Frankfurter, d'après la banque centrale indiquée",
    ),
    # Marchés et sociétés
    "query1.finance.yahoo.com": HostInfo(
        f"Conditions de Yahoo, {_PERSONAL}",
        "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
        "Source : Yahoo Finance",
        robots_exception=True,
        note="Exception assumée de l'équipe au robots.txt (Disallow: /), faute de source officielle gratuite pour la TSX.",
    ),
    "www.sec.gov": _SEC,
    "data.sec.gov": _SEC,
    "api.gleif.org": HostInfo("CC0 (GLEIF)", "https://www.gleif.org/en/meta/lei-data-terms-of-use", "Source : GLEIF"),
    "api.kraken.com": HostInfo(
        "Conditions de Kraken", "https://www.kraken.com/legal", "Source : Kraken", max_requests=10
    ),
    "api.exchange.coinbase.com": HostInfo(
        "Conditions de Coinbase", "https://www.coinbase.com/legal", "Source : Coinbase", max_requests=10
    ),
    # Fonds et durabilité
    "www.blackrock.com": HostInfo(
        f"Conditions d'iShares (reproduction interdite), {_PERSONAL}; expositions agrégées seulement",
        "https://www.ishares.com/us/compliance/factor-box-terms",
        "Source : iShares by BlackRock",
        max_requests=6,
    ),
    "www.ssga.com": HostInfo(
        f"Conditions de State Street (divulgation interdite), {_PERSONAL}; expositions agrégées seulement",
        "https://www.ssga.com/",
        "Source : State Street Global Advisors (SPDR)",
        max_requests=6,
    ),
    "api.climatetrace.org": HostInfo(
        "CC BY 4.0 (Climate TRACE), sauf champs « license restricted »",
        "https://climatetrace.org/terms",
        "Source : Climate TRACE",
    ),
    "data.epa.gov": HostInfo(
        "EPA Envirofacts (conditions non vérifiées)", "https://www.epa.gov/enviro", "Source : U.S. EPA Envirofacts"
    ),
    # Logement et conjoncture
    "www.fhfa.gov": HostInfo(
        "Agence fédérale (domaine public probable)",
        "https://www.fhfa.gov/data/hpi/datasets",
        "Source : Federal Housing Finance Agency",
    ),
    "raw.githubusercontent.com": HostInfo(
        "CC BY 4.0 (Indeed Hiring Lab)",
        "https://github.com/hiring-lab/job_postings_tracker",
        "Source : Indeed Hiring Lab",
    ),
    "reports-public.ieso.ca": HostInfo(
        "IESO (conditions non citées)", "https://www.ieso.ca/", "Source : IESO", max_requests=5
    ),
    "www.policyuncertainty.com": HostInfo(
        "Baker, Bloom et Davis (conditions non lues)",
        "https://www.policyuncertainty.com/",
        "Source : Economic Policy Uncertainty (Baker, Bloom et Davis)",
    ),
    "www.sca.isr.umich.edu": HostInfo(
        "Université du Michigan (conditions non lues)",
        "https://www.sca.isr.umich.edu/",
        "Source : University of Michigan, Surveys of Consumers",
    ),
    # Marchés prédictifs et positionnement
    "external-api.kalshi.com": HostInfo(
        f"Developer Agreement de Kalshi NON LU (429 au 2026-11-15), {_PERSONAL}",
        "https://kalshi.com/developer-agreement",
        "Source : Kalshi",
    ),
    "gamma-api.polymarket.com": HostInfo(
        f"Conditions de Polymarket (clause « Capital Market Client »), {_PERSONAL}",
        "https://polymarket.com/tos",
        "Source : Polymarket",
    ),
    "clob.polymarket.com": HostInfo(
        f"Conditions de Polymarket, {_PERSONAL}", "https://polymarket.com/tos", "Source : Polymarket"
    ),
    "www.m-x.ca": HostInfo(
        f"Conditions de la Bourse de Montréal (usage strictement personnel), {_PERSONAL}",
        "https://www.m-x.ca/en/terms-of-use",
        "Source : Bourse de Montréal",
        max_requests=6,
    ),
    "publicreporting.cftc.gov": HostInfo(
        "CFTC (agence fédérale, domaine public par inférence)",
        "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm",
        "Source : CFTC, Commitments of Traders",
    ),
    "api.finra.org": HostInfo(
        "FINRA (« not intended for commercial purposes »)", "https://developer.finra.org/docs", "Source : FINRA"
    ),
    "cdn.finra.org": HostInfo("FINRA", "https://developer.finra.org/docs", "Source : FINRA"),
    "www.deribit.com": HostInfo("Conditions de Deribit (non lues)", "https://www.deribit.com/", "Source : Deribit"),
    "www.okx.com": HostInfo("Conditions d'OKX (non lues)", "https://www.okx.com/", "Source : OKX"),
    "stablecoins.llama.fi": HostInfo(
        f"Conditions de DefiLlama (republication sur permission), {_PERSONAL}",
        "https://defillama.com/terms",
        "Source : DefiLlama",
    ),
    "mba.tuck.dartmouth.edu": HostInfo(
        f"Copyright Fama et French, {_PERSONAL}",
        "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html",
        "Source : Kenneth R. French Data Library",
    ),
    # Presse, attention, communications officielles
    "www.newswire.ca": HostInfo(
        "Conditions de Cision (métadonnées et résumé maison seulement)",
        "https://www.prnewswire.com/terms-of-use/",
        "Source : Newswire.ca (Cision)",
    ),
    "www.prnewswire.com": HostInfo(
        "Conditions de Cision (métadonnées et résumé maison seulement)",
        "https://www.prnewswire.com/terms-of-use/",
        "Source : PR Newswire (Cision)",
    ),
    "api.gdeltproject.org": HostInfo(
        "GDELT (usage libre avec citation et lien; métadonnées seulement)",
        "https://www.gdeltproject.org/about.html",
        "Source : The GDELT Project",
        max_requests=6,
    ),
    "wikimedia.org": HostInfo(
        "CC0 (pages vues Wikimédia)",
        "https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html",
        "Source : Wikimedia Foundation, pages vues",
    ),
    "fr.wikipedia.org": HostInfo(
        "API MediaWiki (titres seulement)",
        "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use",
        "Source : Wikipédia",
    ),
    "en.wikipedia.org": HostInfo(
        "API MediaWiki (titres seulement)",
        "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use",
        "Source : Wikipedia",
    ),
    "rss.marketingtools.apple.com": HostInfo(
        "Apple Marketing Tools (conditions non lues)",
        "https://rss.marketingtools.apple.com/",
        "Source : Apple Marketing Tools",
    ),
    "trends.google.com": HostInfo(
        "Google Trends « Trending now » (conditions non lues)",
        "https://policies.google.com/terms",
        "Source : Google Trends",
        max_requests=4,
    ),
    "hn.algolia.com": HostInfo(
        "Hacker News via Algolia (comptes agrégés seulement)", "https://hn.algolia.com/api", "Source : Hacker News"
    ),
    "api.bsky.app": HostInfo(
        "Bluesky (contenu aux auteurs : comptes agrégés seulement)",
        "https://bsky.social/about/support/tos",
        "Source : Bluesky",
    ),
    "ici.radio-canada.ca": HostInfo(
        f"Radio-Canada, usage à titre personnel, {_PERSONAL}; titre, lien et résumé maison",
        "https://ici.radio-canada.ca/rss",
        "Source : Radio-Canada",
        max_requests=5,
    ),
}


@dataclass(frozen=True)
class Pack:
    name: str
    hosts: tuple[str, ...]
    sources: tuple[str, ...]  # adaptateurs de search_source
    endpoints: tuple[str, ...]  # points d'accès connus (gabarits)
    traps: tuple[str, ...]
    phase2: tuple[str, ...] = ()
    feeds: tuple[tuple[str, str], ...] = ()


PACKS: dict[str, Pack] = {
    "canada-macro": Pack(
        "canada-macro",
        ("www.bankofcanada.ca", "www150.statcan.gc.ca", "open.canada.ca"),
        ("valet_groups", "valet_series", "statcan_tables", "ckan"),
        (
            "https://www.bankofcanada.ca/valet/observations/{SERIES[,SERIES]}/json?recent=12",
            "https://www.bankofcanada.ca/valet/observations/group/{GROUP}/json?recent=4",
            "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorByReferencePeriodRange?vectorIds=%22{VECTOR}%22&startRefPeriod=YYYY-MM-DD&endReferencePeriod=YYYY-MM-DD",
            "statcan_table(product_id) then statcan_data(product_id, coordinate, latest_n) for tables",
            "https://www150.statcan.gc.ca/n1/dai-quo/ssi/homepage/schedule-key_indicators-eng.json (release calendar)",
            "https://open.canada.ca/data/api/3/action/datastore_search?resource_id={ID}&limit=50",
        ),
        (
            "WDS releaseTime is the LAST release, overwritten by revisions: take publication dates from the calendar.",
            "Valet observation dates are the start of the reference period; Valet CPI is StatCan content (cite both).",
            "Never call WDS between 00:00 and 08:30 ET (409).",
            "Edition groups MPR_*, BOS_*, CSCE_* are de facto vintages.",
        ),
        phase2=("StatCan SDMX",),
    ),
    "us-intl-macro": Pack(
        "us-intl-macro",
        (
            "fred.stlouisfed.org",
            "www.philadelphiafed.org",
            "api.imf.org",
            "sdmx.oecd.org",
            "data-api.ecb.europa.eu",
            "api.worldbank.org",
            "stats.bis.org",
        ),
        ("oecd_dataflows", "imf_dataflows"),
        (
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES} (no key; latest revised values only)",
            "https://api.imf.org/external/sdmx/2.1/data/{AGENCY},{FLOW}/{KEY}?startPeriod=YYYY-MM",
            "https://sdmx.oecd.org/public/rest/data/{AGENCY},{FLOW},{VERSION}/{KEY}?lastNObservations=3&format=csvfilewithlabels",
            "https://data-api.ecb.europa.eu/service/data/{FLOW}/{KEY}?lastNObservations=3&format=csvdata",
            "https://api.worldbank.org/v2/country/{ISO2}/indicator/{INDICATOR}?format=json&per_page=10",
            "https://stats.bis.org/api/v1/data/{FLOW}/{KEY}/all?lastNObservations=3&format=csv",
        ),
        (
            "BLS October 2025 values are '-' (shutdown): missing, never interpolated.",
            "Never store ICE BofA series (reproduction prohibited), even from FRED.",
            "FRED and publisher copies differ (OECD CLI, EPU): record the exact source and vintage.",
            "IMF forbids automated bulk download: targeted keys only. OECD: at most 3 downloads per session.",
        ),
        phase2=("FRED API and ALFRED vintages", "BLS v2", "BEA", "Census", "UN Comtrade"),
    ),
    "rates-fx-commodities": Pack(
        "rates-fx-commodities",
        (
            "www.bankofcanada.ca",
            "home.treasury.gov",
            "markets.newyorkfed.org",
            "api.frankfurter.dev",
            "data-api.ecb.europa.eu",
            "api.imf.org",
        ),
        ("valet_groups", "valet_series"),
        (
            "https://www.bankofcanada.ca/valet/observations/group/bond_yields_benchmark/json?recent=5",
            "https://www.bankofcanada.ca/valet/observations/group/FX_RATES_DAILY/json?recent=5",
            "https://www.bankofcanada.ca/valet/observations/M.BCPI/json?recent=6",
            "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value_month=YYYYMM",
            "https://markets.newyorkfed.org/api/rates/secured/sofr/last/5.json",
            "https://api.frankfurter.dev/v2/rates?base=USD&quotes=CAD&providers=boc",
            "https://data-api.ecb.europa.eu/service/data/EXR/D.CAD.EUR.SP00.A?lastNObservations=5&format=csvdata",
            "https://api.imf.org/external/sdmx/2.1/data/IMF.RES,PCPS/G001.PGOLD.USD.M?startPeriod=YYYY-MM",
        ),
        (
            "Stopped FX series (RUB, SAR since May 2026) return an old date with recent=1: check the date.",
            "Frankfurter mixes providers unless providers=boc or ecb is set.",
            "LBMA gold is excluded (members only); use GLD, IMF PGOLD or central-bank gold.",
        ),
        phase2=("EIA (oil, gas)",),
    ),
    "markets-companies": Pack(
        "markets-companies",
        (
            "query1.finance.yahoo.com",
            "www.sec.gov",
            "data.sec.gov",
            "api.gleif.org",
            "api.kraken.com",
            "api.exchange.coinbase.com",
        ),
        ("edgar_company",),
        (
            "https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?range=1mo&interval=1d&events=div,split",
            "https://data.sec.gov/submissions/CIK{CIK10}.json (filings: form, accessionNumber, acceptanceDateTime)",
            "https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK10}.json (facts carry end, filed, accn)",
            "https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]={NAME}",
            "https://api.kraken.com/0/public/OHLC?pair=XBTCAD&interval=1440",
        ),
        (
            "Store raw close and adjustment factors, never adj_close alone. A 429 is not a delisting.",
            "SEC: never use the frames endpoint (latest restated value). Mixed taxonomies: ifrs-full for RY, TD, CNQ, MFC; us-gaap for ENB, SHOP, CNI, FTS.",
            "CN is filed as CNI; ExxonMobil changed CIK on 2026-07-01 (history under 34088).",
            "ATD and CSU are not in EDGAR (seeds in general/societes/). Never use SEDAR+ or Binance.",
        ),
        phase2=("Alpha Vantage", "EODHD", "Massive", "CoinGecko Demo", "CoinMarketCap", "OpenFIGI key"),
    ),
    "funds-sustainability": Pack(
        "funds-sustainability",
        (
            "www.blackrock.com",
            "www.ssga.com",
            "www.sec.gov",
            "open.canada.ca",
            "data-donnees.ec.gc.ca",
            "api.climatetrace.org",
            "data.epa.gov",
        ),
        ("ckan",),
        (
            "https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf/1464253357814.ajax?fileType=csv&fileName=XIU_holdings&dataType=fund",
            "https://open.canada.ca/data/api/3/action/package_show?id=a8ba14b7-7f23-462a-bdbb-83b0ef629823 (GHGRP)",
            "https://open.canada.ca/data/api/3/action/package_show?id=7dffedc4-23fa-440c-a36d-adf5a6cc09f1 (CER pipeline incidents)",
            "https://api.climatetrace.org/v7/metadata",
            "https://data.epa.gov/efservice/pub_dim_facility/parent_company/CONTAINING/{NAME}/rows/0:5/JSON",
        ),
        (
            "ETF holdings: record aggregated exposures only (by sector or issuer), dated as-of; never GICS labels.",
            "Climate TRACE gives about 10x less than GHGRP for Canadian Natural (incomplete owner mapping): record both.",
            "Envirofacts stops at reporting year 2023. Sustainalytics via Yahoo returns 404. MSCI and GOGEL are excluded.",
            "NBIM exclusions and ESGV ground rules are seeds, not fetched.",
        ),
    ),
    "housing": Pack(
        "housing",
        ("www150.statcan.gc.ca", "www.bankofcanada.ca", "www.fhfa.gov"),
        ("statcan_tables", "valet_groups"),
        (
            "statcan_table(18100205) new housing price index; 46100092 asking and paid rents; 34100127/34100133/34100154 CMHC mirrors; 34100292 permits",
            "https://www.bankofcanada.ca/valet/observations/group/FVI_MORTGAGE_DEBT_SERVICE_RATIO/json?recent=4",
        ),
        (
            "18-10-0251 is NOT a housing index; the RPPI 18-10-0169 has been inactive since 2021.",
            "46-10-0092 republishes its whole history at each release: record the release, never compare vintages silently.",
            "NHPI measures new homes (builders), not resale. Teranet-NB resale history is a seed.",
            "FHFA hpi_master.csv is 17 MB, above the 3 MB response cap: phase 2.",
        ),
    ),
    "cycle": Pack(
        "cycle",
        (
            "fred.stlouisfed.org",
            "sdmx.oecd.org",
            "www.bankofcanada.ca",
            "raw.githubusercontent.com",
            "reports-public.ieso.ca",
            "www.sca.isr.umich.edu",
            "www.policyuncertainty.com",
        ),
        ("valet_groups", "oecd_dataflows"),
        (
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SAHMREALTIME (also RECPROUSM156N, NFCI, STLFSI4, T10YIE, EXPINF10YR)",
            "https://www.bankofcanada.ca/valet/observations/group/BOS_ACTIVITY_PRICE_DATA/json?recent=4",
            "https://www.bankofcanada.ca/valet/observations/group/CES_C1_DEMOGRAPHICS/json?recent=1",
            "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,/CAN.M.LI...AA...H?lastNObservations=2&format=csvfilewithlabels",
            "https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/CA/aggregate_job_postings_CA.csv",
            "https://reports-public.ieso.ca/public/Demand/PUB_Demand.csv",
            "https://www.sca.isr.umich.edu/files/tbmics.csv",
        ),
        (
            "Survey dates are the survey quarter: the publication date comes weeks later (use retrieved_at as upper bound).",
            "OECD CLI and Chauvet-Piger are revised or smoothed ex post; SAHMREALTIME is real-time by design.",
            "GDPNow and SPF are XLSX, and the Cleveland Fed nowcast JSON sits behind an HTML chart: phase 2.",
        ),
    ),
    "market-implied": Pack(
        "market-implied",
        (
            "external-api.kalshi.com",
            "gamma-api.polymarket.com",
            "clob.polymarket.com",
            "www.m-x.ca",
            "www.deribit.com",
            "www.okx.com",
        ),
        ("kalshi_series", "polymarket"),
        (
            "https://external-api.kalshi.com/trade-api/v2/markets?series_ticker={SERIES}&status=open",
            "https://external-api.kalshi.com/trade-api/v2/markets/{TICKER} (yes_bid, yes_ask, volume, open_interest, rules_primary)",
            "https://gamma-api.polymarket.com/markets?slug={SLUG} (question, outcomePrices, volume, description = rules)",
            "https://clob.polymarket.com/prices-history?market={TOKEN_ID}&interval=1w&fidelity=60",
            "https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC&resolution=86400&start_timestamp={MS}&end_timestamp={MS}",
            "https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP",
        ),
        (
            "Always record the resolution rules verbatim (field resolution_rules) and the bid and ask; use the mid-quote.",
            "Polymarket prices-history appends the current point after endTs: drop t > endTs. Data API v1 is retired (410).",
            "Only BoC, Fed and recession markets are shown by default; never quote odds in the last hours before settlement.",
            "KXRECSSNBER-27 settles on two negative BEA GDP quarters, not on NBER dating.",
        ),
    ),
    "positioning": Pack(
        "positioning",
        (
            "publicreporting.cftc.gov",
            "www.sec.gov",
            "api.finra.org",
            "cdn.finra.org",
            "stablecoins.llama.fi",
            "fred.stlouisfed.org",
        ),
        (),
        (
            "https://publicreporting.cftc.gov/resource/6dca-aqww.json?$where=cftc_contract_market_code='090741'&$order=report_date_as_yyyy_mm_dd%20DESC&$limit=2 (legacy COT, CAD)",
            "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest?limit=5",
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS (VIX, J+1; Cboe is excluded)",
            "https://stablecoins.llama.fi/stablecoins?includePrices=true",
        ),
        (
            "COT data are dated Tuesday and published Friday 15:30 ET (later after holidays): publication date = that Friday, never the Tuesday.",
            "FINRA daily ShortVolume is not short interest. 13F: use FILING_DATE, not PERIODOFREPORT.",
            "SEC insider and 13F data sets are quarterly ZIP files: not readable in phase 1.",
        ),
    ),
    "factors": Pack(
        "factors",
        ("mba.tuck.dartmouth.edu",),
        (),
        ("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html (ZIP files: phase 2)",),
        ("Factors explain an exposure; they never predict a return.", "Most factor files are ZIP or XLSX: phase 2."),
    ),
    "issuer-events": Pack(
        "issuer-events",
        ("www.newswire.ca", "www.prnewswire.com"),
        ("feeds",),
        ("feeds: Newswire.ca general and financial-services RSS, PR Newswire RSS",),
        (
            "Metadata and our own summary only: never the body. Match issuers on dc:contributor and 'TSX: XXX'.",
            "Newswire.ca has no per-issuer feed and no French feed.",
        ),
        phase2=("Benzinga Basic on AWS Data Exchange (pending)",),
        feeds=(
            ("Newswire.ca, all news releases", "https://www.newswire.ca/rss/news-releases-list.rss"),
            (
                "Newswire.ca, financial services",
                "https://www.newswire.ca/rss/financial-services-latest-news/financial-services-latest-news-list.rss",
            ),
            (
                "PR Newswire, financial services",
                "https://www.prnewswire.com/rss/financial-services-latest-news/financial-services-latest-news-list.rss",
            ),
        ),
    ),
    "official-comms": Pack(
        "official-comms",
        (
            "www.bankofcanada.ca",
            "www.federalreserve.gov",
            "www.ecb.europa.eu",
            "www150.statcan.gc.ca",
            "gazette.gc.ca",
            "www.parl.ca",
            "www.federalregister.gov",
        ),
        ("feeds",),
        (
            "https://www.parl.ca/legisinfo/en/bills/json",
            "https://www.federalregister.gov/api/v1/documents.json?per_page=5&conditions[term]={TERM}&order=newest",
        ),
        (
            "Official text may be quoted with attribution (licences allow it), unlike press.",
            "BLS feed dates precede the official 08:30 release; Federal Register returns future publication_date values.",
        ),
        phase2=("api.data.gov (Congress.gov, GovInfo, Regulations.gov)",),
        feeds=(
            ("Banque du Canada, communiqués", "https://www.bankofcanada.ca/content_type/press-releases/feed/"),
            ("Federal Reserve, monetary policy", "https://www.federalreserve.gov/feeds/press_monetary.xml"),
            ("ECB, press releases", "https://www.ecb.europa.eu/rss/press.html"),
            ("StatCan, Le Quotidien (FR)", "https://www150.statcan.gc.ca/n1/rss/dai-quo/0-fra.rss"),
            ("StatCan, The Daily (EN)", "https://www150.statcan.gc.ca/n1/rss/dai-quo/0-eng.rss"),
        ),
    ),
    "attention": Pack(
        "attention",
        (
            "api.gdeltproject.org",
            "wikimedia.org",
            "fr.wikipedia.org",
            "en.wikipedia.org",
            "rss.marketingtools.apple.com",
            "trends.google.com",
            "hn.algolia.com",
            "api.bsky.app",
        ),
        ("gdelt", "wikipedia", "hn_mentions", "bluesky_mentions", "feeds"),
        (
            "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{LANG}.wikipedia/all-access/user/{TITLE}/daily/YYYYMMDD/YYYYMMDD",
            "https://rss.marketingtools.apple.com/api/v2/ca/apps/top-free/25/apps.json",
            "https://trends.google.com/trending/rss?geo=CA",
        ),
        (
            "Attention is context, never a buy signal. Store aggregates only: never post text, handles or profiles.",
            "Resolve the canonical Wikipedia title first: a redirect returns 0 views.",
            "Keep a Google Trends term only if it matches an issuer or executive of the brief.",
            "GDELT: one request every 5 s, 3-month window; seendate is detection, not publication.",
        ),
        feeds=(
            ("Apple, top free apps (CA)", "https://rss.marketingtools.apple.com/api/v2/ca/apps/top-free/25/apps.json"),
            ("Apple, top paid apps (CA)", "https://rss.marketingtools.apple.com/api/v2/ca/apps/top-paid/25/apps.json"),
            ("Google Trends, trending now (CA)", "https://trends.google.com/trending/rss?geo=CA"),
            ("Google Trends, trending now (QC)", "https://trends.google.com/trending/rss?geo=CA-QC"),
        ),
    ),
    "context-press": Pack(
        "context-press",
        ("ici.radio-canada.ca",),
        ("feeds",),
        (),
        (
            "Title, link and our own summary only; never the article body; no automatic ticker link.",
            "Grey zone: Radio-Canada blocks some AI agents in robots.txt (checked by the code before each fetch).",
        ),
        feeds=(("Radio-Canada, économie", "https://ici.radio-canada.ca/info/rss/info/economie/en-continu"),),
    ),
}


@dataclass(frozen=True)
class Subject:
    code: str
    slug: str
    name: str
    scope: str
    packs: tuple[str, ...]
    sweep: tuple[dict, ...] = field(default_factory=tuple)


SUBJECTS: dict[str, Subject] = {
    "E1": Subject(
        "E1",
        "macro-politique",
        "Macro and policy",
        "Monetary policy, inflation, activity, jobs, trade and public finances; Canada first, then the US and the world; official communications.",
        ("canada-macro", "us-intl-macro", "official-comms"),
        (
            {
                "objective": "Latest Canadian policy rate, CPI measures and the next StatCan releases",
                "packs": ["canada-macro"],
            },
            {
                "objective": "Latest US and international macro releases relevant to Canadian investors",
                "packs": ["us-intl-macro"],
            },
            {
                "objective": "New official communications (BoC, Fed, ECB, StatCan) since the run window",
                "packs": ["official-comms"],
            },
        ),
    ),
    "E2": Subject(
        "E2",
        "taux-change-matieres",
        "Rates, FX and commodities",
        "Yield curves, CORRA and SOFR, FX against CAD, gold, oil, commodity prices and volatility.",
        ("rates-fx-commodities", "us-intl-macro", "positioning"),
        (
            {
                "objective": "Canadian and US yield curves and overnight rates, latest values",
                "packs": ["rates-fx-commodities"],
            },
            {
                "objective": "USD/CAD and EUR/CAD, gold and commodity price index, latest values",
                "packs": ["rates-fx-commodities"],
            },
        ),
    ),
    "E3": Subject(
        "E3",
        "societes-marches",
        "Companies and markets",
        "The starter universe and any held asset: prices, corporate actions, filings, reported facts, issuer press releases, crypto.",
        ("markets-companies", "issuer-events"),
        (
            {"objective": "New filings and reported facts for the run's tickers", "packs": ["markets-companies"]},
            {"objective": "Issuer press releases about the run's tickers", "packs": ["issuer-events"]},
            {"objective": "Latest closes and corporate actions of the run's tickers", "packs": ["markets-companies"]},
        ),
    ),
    "E4": Subject(
        "E4",
        "fonds-durabilite",
        "Funds and sustainability",
        "ETF holdings and exposures, ESG facts (emissions, incidents, exclusion rules), sector classification. Facts, never scores.",
        ("funds-sustainability", "markets-companies"),
        (
            {
                "objective": "Aggregated exposures of XIU and XBB holdings, dated as-of",
                "packs": ["funds-sustainability"],
            },
            {
                "objective": "Reported facility GHG emissions (GHGRP) of the universe's energy issuers: one fact per "
                "issuer and year, esg_kind emissions, esg_metric ghg_tonnes_co2e",
                "packs": ["funds-sustainability"],
            },
            {
                "objective": "CER pipeline incidents since 2023 of the universe's pipeline operators: one count per "
                "issuer and year, esg_kind incident, esg_metric pipeline_incidents",
                "packs": ["funds-sustainability"],
            },
            {
                "objective": "Fossil fuel activity of universe issuers from official industry classifications (NAICS, "
                "NPRI): esg_kind sector_activity, esg_metric fossil_fuels",
                "packs": ["funds-sustainability"],
            },
        ),
    ),
    "E5": Subject(
        "E5",
        "logement-economie-reelle",
        "Housing and real economy",
        "Prices and rents by region, starts, permits, household debt, real-time jobs, nowcasts and surveys.",
        ("housing", "cycle", "canada-macro"),
        (
            {
                "objective": "Latest regional housing prices, rents and starts (Montreal, Toronto, Vancouver, Canada)",
                "packs": ["housing"],
            },
            {
                "objective": "Business and consumer surveys, real-time job postings and cycle indicators",
                "packs": ["cycle"],
            },
        ),
    ),
    "E6": Subject(
        "E6",
        "attentes-positionnement",
        "Market expectations and positioning",
        "Prediction markets on BoC, Fed and recession; CORRA futures; COT positioning; short interest; crypto derivatives; factors.",
        ("market-implied", "positioning", "factors"),
        (
            {
                "objective": "Market-implied odds for the next Bank of Canada and Fed decisions and for a US recession",
                "packs": ["market-implied"],
            },
            {
                "objective": "Latest COT positioning on CAD, crude oil and S&P 500 futures, and VIX",
                "packs": ["positioning"],
            },
        ),
    ),
    "E7": Subject(
        "E7",
        "actualites-attention",
        "News and attention",
        "Media volume and tone per issuer, Wikipedia attention, app ranks, trending terms and French economic context.",
        ("attention", "context-press"),
        (
            {
                "objective": "Media volume and tone, and Wikipedia attention, for the run's issuers",
                "packs": ["attention"],
            },
            {
                "objective": "French-language economic context and trending terms matching issuers",
                "packs": ["context-press", "attention"],
            },
        ),
    ),
}

DEPTH_CAPS = {"quick": 3, "standard": 6, "deep": 10}
MAX_ROUNDS = 2
MAX_RESEARCHERS_PER_RUN = 24
RESEARCHER_BUDGET_S = 240
RESEARCHER_MAX_BUDGET_S = 300
RESEARCHER_MAX_TOOL_CALLS = 20


def pack_hosts(names: list[str] | tuple[str, ...]) -> frozenset[str]:
    hosts: set[str] = set()
    for name in names:
        hosts.update(PACKS[name].hosts)
    return frozenset(hosts)


def pack_sources(names: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for name in names:
        for source in PACKS[name].sources:
            if source not in out:
                out.append(source)
    return tuple(out)


def describe_packs(names: list[str] | tuple[str, ...]) -> str:
    """Description des paquets pour l'invite d'un chercheur (en anglais, comme les invites)."""
    lines = []
    for name in names:
        pack = PACKS[name]
        lines.append(f"## Pack {name}")
        lines.append("Allowed hosts: " + ", ".join(pack.hosts))
        if pack.sources:
            lines.append("search_source sources: " + ", ".join(pack.sources))
        for endpoint in pack.endpoints:
            lines.append(f"- endpoint: {endpoint}")
        for title, url in pack.feeds:
            lines.append(f"- feed: {title}: {url}")
        for trap in pack.traps:
            lines.append(f"- trap: {trap}")
        if pack.phase2:
            lines.append("Not available yet (phase 2): " + ", ".join(pack.phase2))
    return "\n".join(lines)


def _pack_problems(pack: Pack) -> list[str]:
    problems = [f"{pack.name}: host without licence entry {host}" for host in pack.hosts if host not in HOSTS]
    for _, url in pack.feeds:
        host = url.split("/")[2]
        if host not in pack.hosts:
            problems.append(f"{pack.name}: feed host not in pack {host}")
    return problems


def _subject_problems(subject: Subject) -> list[str]:
    problems = [f"{subject.code}: unknown pack {name}" for name in subject.packs if name not in PACKS]
    for brief in subject.sweep:
        problems += [
            f"{subject.code}: sweep pack {name} not in subject packs"
            for name in brief["packs"]
            if name not in subject.packs
        ]
    return problems


def check_registry() -> list[str]:
    """Incohérences du registre (testées) : hôte de paquet sans licence, paquet de sujet inconnu."""
    problems = [problem for pack in PACKS.values() for problem in _pack_problems(pack)]
    problems += [problem for subject in SUBJECTS.values() for problem in _subject_problems(subject)]
    return problems
