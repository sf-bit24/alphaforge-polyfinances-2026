# Univers large : sources gratuites testées (2026-11-14, sans clé)

Simulation uniquement. Toutes les sources ci-dessous ont été testées par de petites requêtes, sans clé d'API.
Chaque source intégrée doit documenter son origine, sa date, son traitement, ses limites et ses conditions d'utilisation (énoncé, p. 13-14).

## Retenu (ordre de priorité)

| # | Source | Ce qu'elle fournit | Licence et conditions |
|---|---|---|---|
| 1 | **FinanceDatabase** (`pip install financedatabase`, MIT) | 95 616 actions (secteur et industrie GICS, pays, bourse, MIC, ISIN, FIGI) ; 30 434 FNB (catégorie, famille) ; cryptos. Symboles au format Yahoo | MIT. Les bases Funds et Moneymarket ne sont plus maintenues |
| 2 | **yfinance** | Prix ajustés quotidiens et mensuels, tous marchés, depuis plus de 10 ans ; `funds_data` donne le ratio de frais, le top 10 et les secteurs | Recherche seulement, pas de redistribution. **La duration obligataire de yfinance est fausse** (TLT 3,64 contre 14,75) |
| 3 | **JSON du sélecteur de produits iShares US** (`product-screener-v3.1.jsn`) | 526 FNB : frais, `effectiveDuration`, rendement à l'échéance, OAS, pays, région, marché émergent ou développé | Usage informatif, pas de redistribution |
| 4 | **CSV des positions iShares Canada** (`/products/{id}/fund/1464253357814.ajax?fileType=csv`) | Positions avec secteur GICS, pays, poids, et duration par obligation. ID : XIU 239832, XIC 239837, XEF 251421, XEC 251423, XBB 239493 ; liste complète sur `product-list` | Conditions de BlackRock Canada |
| 5 | **Vanguard US** `vmf/api/{T}/...` | `portfolio-holding/stock` et `/bond` (positions complètes), `diversification` (pays et secteur), `characteristic` (duration), `profile` (frais) | Conditions de Vanguard. Positions en retard d'environ 30 à 45 jours |
| 6 | **SPDR / SSGA** | Positions quotidiennes en xlsx (11 FNB sectoriels, SPY, GLD), recherche de fonds en JSON (frais) | Conditions de SSGA, reproduction interdite |
| 7 | **OpenBB TMX** (AGPL-3.0) | Composition du TSX 60, 1 856 FNB canadiens (frais, classe), prix canadiens | Positions limitées au top 10 ; prix probablement non ajustés |
| 8 | **ccxt** (MIT), Bitstamp ou Bitfinex | BTC/USD quotidien depuis 2014 | Conditions des plateformes. Kraken : 720 jours seulement |
| 9 | **Binance data.binance.vision** | Bougies quotidiennes depuis 2017-08 | Conditions de Binance |
| 10 | **Bibliothèque de Ken French** | Facteurs développés, hors États-Unis, Europe, Japon, Asie-Pacifique et émergents depuis 1989-1990 | Gratuit, citation attendue |
| 11 | **Niveaux des indices MSCI** (`app2.msci.com ... getLevelDataForGraph`) | World et EM en rendement net mensuel depuis 2000 | **Calibration interne seulement**, redistribution interdite |
| 12 | **AQR Century of Factor Premia** | Facteurs multi-actifs depuis 1926 | Pas point-in-time : noter la date de la version |
| 13 | **JST Macrohistory** | 18 pays depuis 1870 | CC BY-NC-SA 4.0 |
| 14 | **Wikipédia** (S&P 500, S&P/TSX 60) | Composition + secteur GICS + date d'ajout | CC BY-SA |

## À ne pas utiliser

- **Stooq** : bloqué par une vérification JavaScript ; le lecteur pandas-datareader a été retiré.
- **CSV des positions iShares US** : renvoient du HTML, accès sans doute derrière une connexion.
- **CoinGecko** : pas d'historique au-delà de 365 jours.
- **Positions TMX** : top 10 seulement.
- **Nasdaq API** : prix non ajustés, à garder pour un contrôle croisé seulement.
- **Invesco** (406) et **pages BMO** (délai dépassé).

## Pipeline proposé (500 à 700 actifs)

1. **Liste maîtresse** : colonnes `id, name, exchange, MIC, currency, asset_class, sector, industry, country, source, as_of`.
   - Actions américaines : 150 à 200, les plus gros poids de SPY dans chaque secteur.
   - Actions canadiennes : 60 à 100, issues de XIU et XIC.
   - Actions développées et émergentes, en option : 50 à 100, issues de XEF et XEC.
   - FNB d'actions : environ 60 (marché large, 11 sectoriels, régions et pays, facteurs, FNB canadiens).
   - FNB obligataires : environ 30, en échelle de duration (crédit, inflation, émergents, Canada).
   - Matières premières : environ 10.
   - Cryptos : 5 à 10.
2. **Prix** :
   - `yf.download(..., auto_adjust=True)`, ramené à la fin de mois, avec l'horodatage du téléchargement ;
   - crypto : ccxt Bitstamp depuis 2014 ;
   - contrôle croisé : Nasdaq (US) et TMX (CA).
3. **Look-through** : positions iShares CA, Vanguard et SPDR, avec la date `as_of` de chaque fichier.
   Pour les FNB iShares US, passer par l'équivalent canadien (XEF ≈ IEFA) ou par le N-PORT de la SEC.
4. **Métadonnées** :
   - frais : iShares US, SSGA, Vanguard, TMX ;
   - duration : iShares US ou Vanguard, **jamais yfinance**.
