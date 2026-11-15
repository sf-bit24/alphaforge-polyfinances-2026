import { createElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PositionsTable, reviewIndex, rowOf } from "@/components/profile/review-rows";
import { PortfolioView, type Locale } from "@/lib/contract/schemas";
import { I18nProvider } from "@/lib/i18n/provider";

// Issue #80, suite: in A2's review step, the Status column (with the notes) was cut off on the right at 1440 px
// and 1920 px. The table uses the automatic layout: a `truncate` line with no width bound counts at its full
// length, so the raw CSV line under the ticker widened the first column (373 px) and pushed Status out of the card.

const Provider = I18nProvider as (props: { initialLocale: Locale; children?: ReactNode }) => ReactElement;

const position = {
  sector: null,
  market: null,
  account_type: "tfsa",
  price: null,
  price_date: null,
  price_source: null,
  value_cad: null,
  resolved: false,
  notes: null,
} as const;

// Two rows of the end-to-end check on Bedrock (session va-fr): a long raw line, a long note, an unresolved line.
const PORTFOLIO = PortfolioView.parse({
  positions: [
    {
      ...position,
      id: "p1",
      raw: "XIU.TO,iShares S&P/TSX 60,150,38.20,5730.00,CAD",
      ticker: "XIU.TO",
      name: "iShares S&P/TSX 60 Index ETF",
      asset_class: "etf_equity",
      currency: "CAD",
      quantity: 150,
      market_value: 5730,
      price: 54.55,
      price_date: "2026-11-12",
      price_source: "starter:prices_daily.csv",
      value_cad: 8182.5,
      resolved: true,
      notes: "Compte CELI indiqué dans le texte collé.",
    },
    {
      ...position,
      id: "p7",
      raw: "fonds maison XYZ",
      ticker: null,
      name: "fonds maison XYZ",
      asset_class: "fund",
      currency: null,
      quantity: null,
      market_value: null,
      notes: "Présent seulement dans le texte collé, sans symbole, quantité ni valeur : à préciser.",
    },
  ],
  unresolved: [{ raw: "fonds maison XYZ", reason: "titre introuvable et aucune valeur fournie", position_id: "p7" }],
  exposures: {
    total_value_cad: 8182.5,
    by_asset_class: { etf_equity: 1 },
    by_currency: { CAD: 1 },
    by_market: { TSX: 1 },
    by_sector: { "Broad market (Canada)": 1 },
    top_positions: [{ id: "p1", weight: 1 }],
    flags: ["unvalued_positions"],
  },
  status: "draft",
  sources: [],
});

function table(locale: Locale): string {
  const element = createElement(PositionsTable, {
    rows: PORTFOLIO.positions.map(rowOf),
    review: reviewIndex(PORTFOLIO),
    confirming: false,
    onChange: () => undefined,
    onDelete: () => undefined,
  });
  return renderToStaticMarkup(createElement(Provider, { initialLocale: locale }, element));
}

const classesOf = (html: string, pattern: RegExp) => [...html.matchAll(pattern)].map((match) => match[1] ?? "");

describe("A2 review table keeps the notes inside the card (#80)", () => {
  for (const locale of ["fr", "en"] as const) {
    it(`bounds every truncated line, so it cannot widen its column (${locale})`, () => {
      const html = table(locale);
      const truncated = classesOf(html, /class="([^"]*\btruncate\b[^"]*)"/g);
      expect(truncated.length).toBeGreaterThan(0);
      for (const classes of truncated) expect(classes, classes).toMatch(/\bmax-w-/);
      expect(html).toContain('title="XIU.TO,iShares S&amp;P/TSX 60,150,38.20,5730.00,CAD"');
    });

    it(`reserves a width for the status and its notes, which wrap inside it (${locale})`, () => {
      const html = table(locale);
      const status = classesOf(html, /<td class="([^"]*)"><span[^>]*class="[^"]*rounded-full/g);
      expect(status).toHaveLength(2);
      for (const classes of status) expect(classes).toMatch(/\bw-52\b/);
      for (const note of ["Compte CELI indiqué dans le texte collé.", "titre introuvable et aucune valeur fournie"]) {
        const [, classes = ""] = html.match(new RegExp(`<p class="([^"]*)">${note}</p>`)) ?? [];
        expect(classes, note).toMatch(/\bwrap-anywhere\b/);
        expect(classes, note).not.toMatch(/\bmax-w-/);
      }
    });
  }
});
