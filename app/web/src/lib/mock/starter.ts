/**
 * Reference data the simulator uses for its fake A2 extraction: the 31 assets of the
 * organizers' starter dataset, their last close and the last USD/CAD rate. Values are
 * copied from alphaforge_starter (retrieved 2026-11-13, last observation 2026-11-12),
 * so the mock cites real sources instead of inventing prices.
 */
import type { AssetClass, Source } from "@/lib/contract/schemas";

export interface StarterAsset {
  ticker: string;
  name: string;
  asset_class: AssetClass;
  market: string;
  currency: "CAD" | "USD";
  sector: string;
  close: number;
  aliases: string[];
}

export const PRICE_DATE = "2026-11-12";
export const USDCAD = 1.4255;

export const STARTER_SOURCES = {
  universe: {
    id: "starter-universe",
    title: "Jeu de départ, assets_universe.csv",
    resource: "starter:assets_universe.csv",
    retrieved_at: "2026-11-13",
  },
  prices: {
    id: "starter-prices",
    title: "Jeu de départ, prices_daily.csv (Yahoo Finance via yfinance)",
    resource: "starter:prices_daily.csv",
    observed_at: PRICE_DATE,
    retrieved_at: "2026-11-13",
  },
  fx: {
    id: "starter-fx",
    title: "Jeu de départ, fx_usdcad_daily.csv (Banque du Canada, FXUSDCAD)",
    resource: "starter:fx_usdcad_daily.csv",
    observed_at: PRICE_DATE,
    retrieved_at: "2026-11-13",
  },
  macro: {
    id: "starter-macro",
    title: "Jeu de départ, macro_rates.csv (Banque du Canada, FRED)",
    resource: "starter:macro_rates.csv",
    observed_at: PRICE_DATE,
    retrieved_at: "2026-11-13",
  },
} satisfies Record<string, Source>;

export const STARTER_ASSETS: StarterAsset[] = [
  { ticker: "RY.TO", name: "Royal Bank of Canada", asset_class: "equity", market: "TSX", currency: "CAD", sector: "Financials", close: 289.39, aliases: ["royal bank", "banque royale", "rbc", "ry"] },
  { ticker: "TD.TO", name: "Toronto-Dominion Bank", asset_class: "equity", market: "TSX", currency: "CAD", sector: "Financials", close: 176.69, aliases: ["toronto-dominion", "banque td", "td bank", "td"] },
  { ticker: "MFC.TO", name: "Manulife Financial", asset_class: "equity", market: "TSX", currency: "CAD", sector: "Financials", close: 62.65, aliases: ["manulife", "manuvie", "mfc"] },
  { ticker: "ENB.TO", name: "Enbridge", asset_class: "equity", market: "TSX", currency: "CAD", sector: "Energy", close: 68.57, aliases: ["enbridge", "enb"] },
  { ticker: "CNQ.TO", name: "Canadian Natural Resources", asset_class: "equity", market: "TSX", currency: "CAD", sector: "Energy", close: 70.04, aliases: ["canadian natural", "cnq"] },
  { ticker: "CNR.TO", name: "Canadian National Railway", asset_class: "equity", market: "TSX", currency: "CAD", sector: "Industrials", close: 181.9, aliases: ["canadian national", "cn rail", "cnr"] },
  { ticker: "FTS.TO", name: "Fortis", asset_class: "equity", market: "TSX", currency: "CAD", sector: "Utilities", close: 84.43, aliases: ["fortis", "fts"] },
  { ticker: "ATD.TO", name: "Alimentation Couche-Tard", asset_class: "equity", market: "TSX", currency: "CAD", sector: "Consumer Staples", close: 82.48, aliases: ["couche-tard", "couche tard", "atd"] },
  { ticker: "SHOP.TO", name: "Shopify", asset_class: "equity", market: "TSX", currency: "CAD", sector: "Information Technology", close: 209.41, aliases: ["shopify", "shop"] },
  { ticker: "CSU.TO", name: "Constellation Software", asset_class: "equity", market: "TSX", currency: "CAD", sector: "Information Technology", close: 3496.88, aliases: ["constellation software", "csu"] },
  { ticker: "AAPL", name: "Apple", asset_class: "equity", market: "NASDAQ", currency: "USD", sector: "Information Technology", close: 354.88, aliases: ["apple"] },
  { ticker: "MSFT", name: "Microsoft", asset_class: "equity", market: "NASDAQ", currency: "USD", sector: "Information Technology", close: 523.0, aliases: ["microsoft"] },
  { ticker: "NVDA", name: "NVIDIA", asset_class: "equity", market: "NASDAQ", currency: "USD", sector: "Information Technology", close: 166.19, aliases: ["nvidia"] },
  { ticker: "GOOGL", name: "Alphabet (Class A)", asset_class: "equity", market: "NASDAQ", currency: "USD", sector: "Communication Services", close: 298.7, aliases: ["alphabet", "google", "goog"] },
  { ticker: "AMZN", name: "Amazon", asset_class: "equity", market: "NASDAQ", currency: "USD", sector: "Consumer Discretionary", close: 267.44, aliases: ["amazon"] },
  { ticker: "TSLA", name: "Tesla", asset_class: "equity", market: "NASDAQ", currency: "USD", sector: "Consumer Discretionary", close: 397.45, aliases: ["tesla"] },
  { ticker: "JPM", name: "JPMorgan Chase", asset_class: "equity", market: "NYSE", currency: "USD", sector: "Financials", close: 342.82, aliases: ["jpmorgan", "jp morgan"] },
  { ticker: "JNJ", name: "Johnson & Johnson", asset_class: "equity", market: "NYSE", currency: "USD", sector: "Health Care", close: 283.52, aliases: ["johnson & johnson", "johnson and johnson"] },
  { ticker: "PG", name: "Procter & Gamble", asset_class: "equity", market: "NYSE", currency: "USD", sector: "Consumer Staples", close: 168.03, aliases: ["procter", "procter & gamble"] },
  { ticker: "XOM", name: "Exxon Mobil", asset_class: "equity", market: "NYSE", currency: "USD", sector: "Energy", close: 169.78, aliases: ["exxon"] },
  { ticker: "XIU.TO", name: "iShares S&P/TSX 60 Index ETF", asset_class: "etf_equity", market: "TSX", currency: "CAD", sector: "Broad market (Canada)", close: 54.55, aliases: ["xiu", "tsx 60"] },
  { ticker: "SPY", name: "SPDR S&P 500 ETF Trust", asset_class: "etf_equity", market: "NYSE Arca", currency: "USD", sector: "Broad market (U.S.)", close: 757.12, aliases: ["s&p 500", "sp500"] },
  { ticker: "QQQ", name: "Invesco QQQ Trust (Nasdaq-100)", asset_class: "etf_equity", market: "NASDAQ", currency: "USD", sector: "Broad market (U.S. growth/tech-heavy)", close: 688.17, aliases: ["nasdaq-100", "nasdaq 100"] },
  { ticker: "ESGV", name: "Vanguard ESG U.S. Stock ETF", asset_class: "etf_equity", market: "Cboe BZX", currency: "USD", sector: "Broad market (U.S., ESG-screened)", close: 133.29, aliases: ["vanguard esg"] },
  { ticker: "XBB.TO", name: "iShares Core Canadian Universe Bond Index ETF", asset_class: "etf_bond", market: "TSX", currency: "CAD", sector: "Bonds (Canada aggregate)", close: 27.53, aliases: ["xbb"] },
  { ticker: "ZST.TO", name: "BMO Ultra Short-Term Bond ETF", asset_class: "etf_bond", market: "TSX", currency: "CAD", sector: "Bonds (Canada ultra short-term)", close: 49.07, aliases: ["zst"] },
  { ticker: "AGG", name: "iShares Core U.S. Aggregate Bond ETF", asset_class: "etf_bond", market: "NYSE Arca", currency: "USD", sector: "Bonds (U.S. aggregate)", close: 95.22, aliases: [] },
  { ticker: "TLT", name: "iShares 20+ Year Treasury Bond ETF", asset_class: "etf_bond", market: "NASDAQ", currency: "USD", sector: "Bonds (U.S. long Treasury)", close: 79.72, aliases: [] },
  { ticker: "GLD", name: "SPDR Gold Shares", asset_class: "etf_commodity", market: "NYSE Arca", currency: "USD", sector: "Gold", close: 354.89, aliases: ["gold", "spdr gold"] },
  { ticker: "BTC-USD", name: "Bitcoin", asset_class: "crypto", market: "Crypto (24/7)", currency: "USD", sector: "Crypto asset", close: 71342.97, aliases: ["bitcoin", "btc"] },
  { ticker: "ETH-USD", name: "Ether", asset_class: "crypto", market: "Crypto (24/7)", currency: "USD", sector: "Crypto asset", close: 2016.83, aliases: ["ethereum", "ether", "eth"] },
];

const BY_TICKER = new Map(STARTER_ASSETS.map((asset) => [asset.ticker, asset]));

/** Resolve a ticker as typed by an investor: `RY.TO`, `ry`, `RY-T`, `BTC`... */
export function findAssetByTicker(input: string | null | undefined): StarterAsset | null {
  if (!input) return null;
  const token = input.trim().toUpperCase().replace(/[-.]T$|\.TSX$|:TSX$|^TSX:/, "");
  if (token === "") return null;
  return (
    BY_TICKER.get(token) ??
    BY_TICKER.get(`${token}.TO`) ??
    BY_TICKER.get(`${token}-USD`) ??
    BY_TICKER.get(input.trim().toUpperCase()) ??
    null
  );
}

/** Find an asset whose name or alias appears in a free-text line. */
export function findAssetInText(line: string): StarterAsset | null {
  const lower = ` ${line.toLowerCase()} `;
  for (const asset of STARTER_ASSETS) {
    const names = [asset.name.toLowerCase(), ...asset.aliases];
    for (const name of names) {
      if (name.length < 3) continue;
      const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      if (new RegExp(`[^a-z0-9]${escaped}[^a-z0-9]`).test(lower)) return asset;
    }
  }
  return null;
}
