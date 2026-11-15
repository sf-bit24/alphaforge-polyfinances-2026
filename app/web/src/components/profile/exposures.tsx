"use client";

import { ChartBar, Table2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import type { Exposures, FxRate, Locale, Position, Source } from "@/lib/contract/schemas";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { formatDate, formatMoney, formatNumber, formatPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { SourceLine } from "@/components/trace/trace-panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/components/ui/cn";

const MAX_ROWS = 6;

type Label = Record<Locale, string>;

/**
 * Keys the runtime uses for any group: a missing sector or market (`Unknown`, `other` in the mock) and cash. `other`
 * is not labelled "Other", which names the folded tail (`rowsOf`). The contract keys stay the raw values; only the
 * label shown changes.
 */
const UNCLASSIFIED: Label = { fr: "Non classé", en: "Unclassified" };
const COMMON_LABELS: Record<string, Label> = {
  Unknown: UNCLASSIFIED,
  other: UNCLASSIFIED,
  Cash: { fr: "Encaisse", en: "Cash" },
};

/** `by_sector` keys: the GICS sectors and the fund categories of the starter universe (`assets_universe.csv`). */
const SECTOR_LABELS: Record<string, Label> = {
  ...COMMON_LABELS,
  "Communication Services": { fr: "Services de communication", en: "Communication Services" },
  "Consumer Discretionary": { fr: "Consommation discrétionnaire", en: "Consumer Discretionary" },
  "Consumer Staples": { fr: "Consommation de base", en: "Consumer Staples" },
  Energy: { fr: "Énergie", en: "Energy" },
  Financials: { fr: "Services financiers", en: "Financials" },
  "Health Care": { fr: "Soins de santé", en: "Health Care" },
  Industrials: { fr: "Industrie", en: "Industrials" },
  "Information Technology": { fr: "Technologies de l’information", en: "Information Technology" },
  Materials: { fr: "Matériaux", en: "Materials" },
  "Real Estate": { fr: "Immobilier", en: "Real Estate" },
  Utilities: { fr: "Services publics", en: "Utilities" },
  "Bonds (Canada aggregate)": { fr: "Obligations (Canada, ensemble du marché)", en: "Bonds (Canada aggregate)" },
  "Bonds (Canada ultra short-term)": {
    fr: "Obligations (Canada, ultra court terme)",
    en: "Bonds (Canada ultra short-term)",
  },
  "Bonds (U.S. aggregate)": { fr: "Obligations (États-Unis, ensemble du marché)", en: "Bonds (U.S. aggregate)" },
  "Bonds (U.S. long Treasury)": { fr: "Obligations (Trésor américain, long terme)", en: "Bonds (U.S. long Treasury)" },
  "Broad market (Canada)": { fr: "Ensemble du marché (Canada)", en: "Broad market (Canada)" },
  "Broad market (U.S.)": { fr: "Ensemble du marché (États-Unis)", en: "Broad market (U.S.)" },
  "Broad market (U.S. growth/tech-heavy)": {
    fr: "Ensemble du marché (États-Unis, croissance et techno)",
    en: "Broad market (U.S. growth/tech-heavy)",
  },
  "Broad market (U.S., ESG-screened)": {
    fr: "Ensemble du marché (États-Unis, filtre ESG)",
    en: "Broad market (U.S., ESG-screened)",
  },
  "Crypto asset": { fr: "Cryptoactif", en: "Crypto asset" },
  Gold: { fr: "Or", en: "Gold" },
};

/** `by_market` keys: exchange names (TSX, NASDAQ, NYSE…) are shown as sent; only these are translated. */
const MARKET_LABELS: Record<string, Label> = {
  ...COMMON_LABELS,
  "Crypto (24/7)": { fr: "Crypto (24 h/24, 7 j/7)", en: "Crypto (24/7)" },
};

/** Label of a raw `by_sector` or `by_market` key in the session language; an unlisted key is shown as sent. */
export function exposureLabel(group: "sector" | "market", key: string, locale: Locale): string {
  const labels = group === "sector" ? SECTOR_LABELS : MARKET_LABELS;
  return labels[key]?.[locale] ?? key;
}

interface Row {
  name: string;
  share: number;
}

interface Group {
  title: string;
  rows: Row[];
}

/** Ranked rows, largest first; a long tail folds into "Other" so no row needs a new colour. */
function rowsOf(shares: Record<string, number>, label: (name: string) => string, other: string): Row[] {
  const sorted = Object.entries(shares)
    .map(([name, share]) => ({ name: label(name), share }))
    .sort((first, second) => second.share - first.share);
  if (sorted.length <= MAX_ROWS) return sorted;
  const head = sorted.slice(0, MAX_ROWS - 1);
  const tail = sorted.slice(MAX_ROWS - 1).reduce((sum, row) => sum + row.share, 0);
  return [...head, { name: other, share: tail }];
}

function BarList({ title, rows, total }: { title: string; rows: Row[]; total: number }) {
  const { locale } = useI18n();
  const max = Math.max(...rows.map((row) => row.share), 0.0001);
  return (
    <figure className="min-w-0">
      <figcaption className="mb-2 text-xs font-semibold tracking-wide text-ink-600 uppercase">{title}</figcaption>
      <ul className="space-y-2">
        {rows.map((row) => (
          <li
            key={row.name}
            className="group grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 text-sm"
            title={`${row.name} : ${formatPercent(row.share, locale, 1)} · ${formatMoney(row.share * total, locale)}`}
          >
            <span className="truncate text-ink-800">{row.name}</span>
            <span aria-hidden className="relative h-3 rounded-r-[4px]">
              <span
                className="absolute inset-y-0 left-0 rounded-r-[4px] bg-navy transition-[width] duration-500 group-hover:bg-ink-700"
                style={{ width: `${Math.max(1.5, (row.share / max) * 100)}%` }}
              />
            </span>
            <span className="w-12 text-right font-medium text-ink-900 tabular-nums">{formatPercent(row.share, locale)}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

function TableView({ groups, total }: { groups: Group[]; total: number }) {
  const { t, locale } = useI18n();
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-ink-200 text-left text-xs text-ink-600">
            <th scope="col" className="py-2 pr-4 font-semibold">
              {t.exposures.group}
            </th>
            <th scope="col" className="py-2 pr-4 font-semibold">
              {t.exposures.category}
            </th>
            <th scope="col" className="py-2 pr-4 text-right font-semibold">
              {t.exposures.share}
            </th>
            <th scope="col" className="py-2 text-right font-semibold">
              CAD
            </th>
          </tr>
        </thead>
        <tbody>
          {groups.flatMap((group) =>
            group.rows.map((row, index) => (
              <tr key={`${group.title}-${row.name}`} className="border-b border-ink-150">
                <td className="py-1.5 pr-4 text-ink-600">{index === 0 ? group.title : ""}</td>
                <td className="py-1.5 pr-4 text-ink-900">{row.name}</td>
                <td className="py-1.5 pr-4 text-right tabular-nums">{formatPercent(row.share, locale, 1)}</td>
                <td className="py-1.5 text-right tabular-nums">{formatMoney(row.share * total, locale)}</td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </div>
  );
}

export function FlagList({ flags }: { flags: string[] }) {
  const { t } = useI18n();
  if (flags.length === 0) return <p className="text-sm text-ink-500">{t.exposures.noFlags}</p>;
  return (
    <ul className="grid gap-2 sm:grid-cols-2">
      {flags.map((flag) => {
        const known = t.flags[flag];
        const title = known?.title ?? flag.replace(/_/g, " ");
        return (
          <li key={flag} className="flex items-start gap-2.5 rounded-lg bg-warning-wash px-3 py-2.5 ring-1 ring-warning/40">
            <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-warning-ink" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink-950">{title}</p>
              {known ? <p className="mt-0.5 text-[0.8rem] leading-snug text-ink-700">{known.text}</p> : null}
              <p className="mt-0.5 font-mono text-[0.65rem] text-ink-500">{flag}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function SourcesList({ sources }: { sources: Source[] }) {
  const { t } = useI18n();
  if (sources.length === 0) return null;
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold tracking-wide text-ink-600 uppercase">{t.common.sources}</p>
      <ul className="space-y-1.5">
        {sources.map((source) => (
          <SourceLine key={source.id} source={source} />
        ))}
      </ul>
    </div>
  );
}

/** The conversion rate behind the CAD values, with its date and source (`PortfolioView.fx`). */
export function FxNote({ fx, className }: { fx: FxRate | null | undefined; className?: string }) {
  const { t, locale } = useI18n();
  if (!fx) return null;
  const base = fx.pair.slice(0, 3) || "USD";
  const quote = fx.pair.slice(3) || "CAD";
  return (
    <p className={cn("text-xs text-ink-500", className)}>
      {t.exposures.fx(`1 ${base} = ${formatNumber(fx.rate, locale, 4)} ${quote}`, formatDate(fx.date, locale))}{" "}
      <span className="font-mono text-[0.7rem] text-ink-400">{fx.source}</span>
    </p>
  );
}

/** The four groups of bars, labelled in the session language (the keys are the contract's raw values). */
export function exposureGroups(exposures: Exposures, t: Dictionary, locale: Locale): Group[] {
  const assetLabel = (name: string) => (t.assetClasses as Record<string, string>)[name] ?? name;
  const marketLabel = (name: string) => exposureLabel("market", name, locale);
  const sectorLabel = (name: string) => exposureLabel("sector", name, locale);
  return [
    { title: t.exposures.byAssetClass, rows: rowsOf(exposures.by_asset_class, assetLabel, t.assetClasses.other) },
    { title: t.exposures.byCurrency, rows: rowsOf(exposures.by_currency, (name) => name, t.assetClasses.other) },
    { title: t.exposures.byMarket, rows: rowsOf(exposures.by_market, marketLabel, t.assetClasses.other) },
    { title: t.exposures.bySector, rows: rowsOf(exposures.by_sector, sectorLabel, t.assetClasses.other) },
  ];
}

interface ExposuresHeaderProps {
  total: number;
  fx: FxRate | null | undefined;
  table: boolean;
  onToggle: () => void;
}

function ExposuresHeader({ total, fx, table, onToggle }: ExposuresHeaderProps) {
  const { t, locale } = useI18n();
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="text-xs font-medium text-ink-500">{t.exposures.total}</p>
        <p className="text-[2rem] leading-tight font-semibold tracking-tight text-ink-950">{formatMoney(total, locale)}</p>
        <p className="text-xs text-ink-500">{t.exposures.computedByCode}</p>
        <FxNote fx={fx} className="mt-0.5" />
      </div>
      <Button
        size="sm"
        variant="secondary"
        onClick={onToggle}
        aria-pressed={table}
        icon={table ? <ChartBar aria-hidden className="size-4" /> : <Table2 aria-hidden className="size-4" />}
      >
        {table ? t.exposures.showBars : t.exposures.showTable}
      </Button>
    </div>
  );
}

/** The groups as a table or as bars; nothing to show without a total. */
function ExposuresBody({ groups, total, table }: { groups: Group[]; total: number; table: boolean }) {
  const { t } = useI18n();
  if (total <= 0) return <p className="text-sm text-ink-500">{t.exposures.empty}</p>;
  if (table) return <TableView groups={groups} total={total} />;
  return (
    <div className="grid gap-x-10 gap-y-6 md:grid-cols-2">
      {groups.map((group) => (
        <BarList key={group.title} title={group.title} rows={group.rows} total={total} />
      ))}
    </div>
  );
}

function TopPositions({ topPositions, positions }: { topPositions: Exposures["top_positions"]; positions: Position[] }) {
  const { t, locale } = useI18n();
  const byId = new Map(positions.map((position) => [position.id, position]));
  return (
    <div>
      <p className="mb-2 text-xs font-semibold tracking-wide text-ink-600 uppercase">{t.exposures.topPositions}</p>
      <ul className="flex flex-wrap gap-2">
        {topPositions.map((top) => {
          const position = byId.get(top.id);
          return (
            <li key={top.id} className="rounded-lg bg-ink-50 px-3 py-1.5 text-sm ring-1 ring-ink-150">
              <span className="font-mono font-medium text-ink-900">{position?.ticker ?? position?.name ?? top.id}</span>
              <span className="ml-2 text-ink-600 tabular-nums">{formatPercent(top.weight, locale, 1)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Exposures computed by code (shares of total_value_cad), with flags and sources. */
export function ExposuresView({
  exposures,
  positions,
  sources,
  fx,
  stale = false,
}: {
  exposures: Exposures;
  positions: Position[];
  sources: Source[];
  fx?: FxRate | null;
  stale?: boolean;
}) {
  const { t, locale } = useI18n();
  const [table, setTable] = useState(false);
  const total = exposures.total_value_cad;
  const groups = exposureGroups(exposures, t, locale);
  return (
    <div className={cn("space-y-6 transition-opacity", stale && "opacity-60")}>
      <ExposuresHeader total={total} fx={fx} table={table} onToggle={() => setTable((value) => !value)} />
      <ExposuresBody groups={groups} total={total} table={table} />
      {exposures.top_positions.length > 0 ? <TopPositions topPositions={exposures.top_positions} positions={positions} /> : null}
      <div>
        <p className="mb-2 text-xs font-semibold tracking-wide text-ink-600 uppercase">{t.exposures.flags}</p>
        <FlagList flags={exposures.flags} />
      </div>
      <SourcesList sources={sources} />
    </div>
  );
}
