"use client";

import { CircleCheck, Trash2 } from "lucide-react";
import type { PositionInput } from "@/lib/contract/requests";
import type { AccountType, PortfolioView, Position, UnresolvedItem } from "@/lib/contract/schemas";
import { ACCOUNT_TYPES } from "@/lib/contract/schemas";
import { parseNumberInput } from "@/lib/client/answers";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { formatDate, formatMoney, formatNumber } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/components/ui/cn";

export interface Row {
  key: string;
  base: Position;
  ticker: string;
  quantity: string;
  marketValue: string;
  currency: string;
  account: AccountType | "";
  edited: boolean;
}

const numberText = (value: number | null | undefined) => (typeof value === "number" ? String(value) : "");

export function rowOf(position: Position): Row {
  return {
    key: position.id,
    base: position,
    ticker: position.ticker ?? "",
    quantity: numberText(position.quantity),
    marketValue: numberText(position.market_value),
    currency: position.currency ?? "",
    account: position.account_type ?? "",
    edited: false,
  };
}

export function blankPosition(id: string, raw: string | null): Position {
  return {
    id,
    raw,
    ticker: null,
    name: null,
    asset_class: null,
    sector: null,
    market: null,
    currency: "CAD",
    quantity: null,
    market_value: null,
    account_type: "unknown",
    price: null,
    price_date: null,
    price_source: null,
    value_cad: null,
    resolved: false,
    notes: null,
  };
}

/** The corrected position sent back with `portfolio.confirm`; derived fields are dropped when stale. */
export function toInput(row: Row): PositionInput {
  const base = row.base;
  const tickerChanged = row.ticker.trim().toUpperCase() !== (base.ticker ?? "").toUpperCase();
  const keep = <T,>(value: T | null | undefined): T | null => (tickerChanged ? null : (value ?? null));
  return {
    id: base.id,
    raw: base.raw ?? null,
    ticker: row.ticker.trim() || null,
    name: keep(base.name),
    asset_class: keep(base.asset_class),
    sector: keep(base.sector),
    market: keep(base.market),
    currency: row.currency.trim().toUpperCase() || null,
    quantity: parseNumberInput(row.quantity),
    market_value: parseNumberInput(row.marketValue),
    account_type: row.account || null,
    price: keep(base.price),
    price_date: keep(base.price_date),
    price_source: keep(base.price_source),
    value_cad: row.edited ? null : (base.value_cad ?? null),
    resolved: tickerChanged ? false : base.resolved,
    notes: base.notes ?? null,
  };
}

/** A filled amount that is not a number, or is negative. */
const isBadAmount = (text: string) => text.trim() !== "" && (parseNumberInput(text) === null || (parseNumberInput(text) ?? 0) < 0);

/**
 * A row proposed by A2 may stay without a ticker (unresolved, left unvalued by code);
 * a row added by the investor needs a ticker or a declared value.
 */
function rowIssues(row: Row, rowIds: Set<string>) {
  return {
    ticker: row.ticker.trim() === "" && !rowIds.has(row.key) && row.marketValue.trim() === "",
    quantity: isBadAmount(row.quantity),
    marketValue: isBadAmount(row.marketValue),
    currency: row.currency.trim() !== "" && !/^[A-Za-z]{3}$/.test(row.currency.trim()),
  };
}

type RowIssues = ReturnType<typeof rowIssues>;

/** Why the rows cannot be confirmed yet, or null. */
export function confirmProblem(rows: Row[], rowIds: Set<string>, t: Dictionary): string | null {
  if (rows.length === 0) return t.review.needOne;
  const issues = rows.map((row) => rowIssues(row, rowIds));
  if (issues.some((issue) => issue.ticker)) return t.review.needTicker;
  if (issues.some((issue) => issue.quantity || issue.marketValue || issue.currency)) return t.question.enterNumber;
  return null;
}

/** An unresolved item with a `position_id` is shown on its row; the others (unreadable files...) in a list below. */
export function reviewIndex(portfolio: PortfolioView) {
  const rowIds = new Set(portfolio.positions.map((position) => position.id));
  const unresolvedById = new Map(
    portfolio.unresolved.flatMap((item) => (item.position_id && rowIds.has(item.position_id) ? [[item.position_id, item] as const] : [])),
  );
  const looseUnresolved = portfolio.unresolved.filter((item) => !item.position_id || !rowIds.has(item.position_id));
  return { rowIds, unresolvedById, looseUnresolved };
}

type ReviewIndex = ReturnType<typeof reviewIndex>;

const CELL =
  "w-full rounded-md border-0 bg-white px-2 py-1.5 text-sm text-ink-950 ring-1 ring-ink-200 ring-inset focus:ring-2 focus:ring-navy focus:outline-none aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-critical";

/** What the editable cells of a row share. */
interface RowCellsProps {
  row: Row;
  issue: RowIssues;
  /** The row's number, for the cells' accessible names. */
  rowLabel: string;
  confirming: boolean;
  onChange: (patch: Partial<Row>) => void;
}

function IdentityCells({ row, issue, rowLabel, confirming, onChange }: RowCellsProps) {
  const { t } = useI18n();
  const base = row.base;
  return (
    <>
      <td className="w-28 px-2 py-2">
        <input
          value={row.ticker}
          onChange={(event) => onChange({ ticker: event.target.value })}
          aria-label={`${t.review.columns.ticker}, ${rowLabel}`}
          aria-invalid={issue.ticker || undefined}
          placeholder={t.review.tickerPlaceholder}
          className={cn(CELL, "min-w-24 font-mono uppercase")}
          disabled={confirming}
        />
        {base.raw ? <p className="mt-1 truncate font-mono text-[0.65rem] text-ink-400" title={base.raw}>{base.raw}</p> : null}
      </td>
      <td className="max-w-40 px-2 py-2">
        <p className="truncate font-medium text-ink-900" title={base.name ?? undefined}>
          {base.name ?? "—"}
        </p>
        {base.asset_class ? <p className="text-xs text-ink-500">{t.assetClasses[base.asset_class]}</p> : null}
      </td>
    </>
  );
}

function HoldingCells({ row, issue, rowLabel, confirming, onChange }: RowCellsProps) {
  const { t } = useI18n();
  return (
    <>
      <td className="w-24 px-2 py-2">
        <input
          value={row.quantity}
          inputMode="decimal"
          onChange={(event) => onChange({ quantity: event.target.value })}
          aria-label={`${t.review.columns.quantity}, ${rowLabel}`}
          aria-invalid={issue.quantity || undefined}
          className={cn(CELL, "min-w-20 text-right tabular-nums")}
          disabled={confirming}
        />
      </td>
      <td className="w-28 px-2 py-2">
        <input
          value={row.marketValue}
          inputMode="decimal"
          onChange={(event) => onChange({ marketValue: event.target.value })}
          aria-label={`${t.review.columns.value}, ${rowLabel}`}
          aria-invalid={issue.marketValue || undefined}
          className={cn(CELL, "min-w-24 text-right tabular-nums")}
          disabled={confirming}
        />
      </td>
      <td className="w-16 px-2 py-2">
        <input
          value={row.currency}
          list="currency-options"
          maxLength={3}
          onChange={(event) => onChange({ currency: event.target.value.toUpperCase() })}
          aria-label={`${t.review.columns.currency}, ${rowLabel}`}
          aria-invalid={issue.currency || undefined}
          className={cn(CELL, "min-w-16 font-mono uppercase")}
          disabled={confirming}
        />
      </td>
    </>
  );
}

function AccountCell({ row, rowLabel, confirming, onChange }: RowCellsProps) {
  const { t } = useI18n();
  return (
    <td className="w-32 px-2 py-2">
      <select
        value={row.account}
        onChange={(event) => onChange({ account: event.target.value as AccountType | "" })}
        aria-label={`${t.review.columns.account}, ${rowLabel}`}
        className={cn(CELL, "min-w-32")}
        disabled={confirming}
      >
        <option value="">—</option>
        {ACCOUNT_TYPES.map((type) => (
          <option key={type} value={type}>
            {t.accountTypes[type]}
          </option>
        ))}
      </select>
    </td>
  );
}

function PriceCell({ position }: { position: Position }) {
  const { t, locale } = useI18n();
  return (
    <td className="px-2 py-2 whitespace-nowrap tabular-nums">
      {typeof position.price === "number" ? (
        <span
          title={
            position.price_date && position.price_source ? t.review.priceSource(formatDate(position.price_date, locale), position.price_source) : undefined
          }
        >
          {formatNumber(position.price, locale)} <span className="text-xs text-ink-500">{position.currency}</span>
          {position.price_date ? <span className="block text-[0.65rem] text-ink-500">{formatDate(position.price_date, locale)}</span> : null}
        </span>
      ) : (
        "—"
      )}
    </td>
  );
}

function StatusBadge({ row }: { row: Row }) {
  const { t } = useI18n();
  if (row.edited) return <Badge tone="brand">{t.review.edited}</Badge>;
  if (row.base.resolved) {
    return (
      <Badge tone="good" icon={<CircleCheck aria-hidden className="size-3" />}>
        {t.review.resolved}
      </Badge>
    );
  }
  return <Badge tone="warning">{t.review.unresolved}</Badge>;
}

/** The row's status, then why A2 could not value it (unless its notes already say so), then its notes. */
function StatusCell({ row, unresolved }: { row: Row; unresolved: UnresolvedItem | undefined }) {
  const base = row.base;
  return (
    <td className="px-2 py-2">
      <StatusBadge row={row} />
      {unresolved && unresolved.reason !== base.notes ? (
        <p className="mt-1 max-w-48 text-[0.7rem] leading-snug text-warning-ink">{unresolved.reason}</p>
      ) : null}
      {base.notes ? <p className="mt-1 max-w-48 text-[0.7rem] leading-snug text-ink-500">{base.notes}</p> : null}
    </td>
  );
}

interface ReviewRowProps {
  row: Row;
  index: number;
  review: ReviewIndex;
  confirming: boolean;
  onChange: (patch: Partial<Row>) => void;
  onDelete: () => void;
}

function ReviewRow({ row, index, review, confirming, onChange, onDelete }: ReviewRowProps) {
  const { t, locale } = useI18n();
  const label = row.ticker || t.review.rowLabel(index + 1);
  const cells: RowCellsProps = { row, issue: rowIssues(row, review.rowIds), rowLabel: t.review.rowLabel(index + 1), confirming, onChange };
  const base = row.base;
  return (
    <tr className={cn("border-b border-ink-150 align-top", row.edited && "bg-soft")}>
      <IdentityCells {...cells} />
      <HoldingCells {...cells} />
      <AccountCell {...cells} />
      <PriceCell position={base} />
      <td className="px-2 py-2 text-right whitespace-nowrap tabular-nums">
        {typeof base.value_cad === "number" && !row.edited ? formatMoney(base.value_cad, locale, "CAD") : "—"}
      </td>
      <StatusCell row={row} unresolved={review.unresolvedById.get(base.id)} />
      <td className="px-2 py-2">
        <Button size="sm" variant="danger" onClick={onDelete} aria-label={t.review.deleteRow(label)} disabled={confirming}>
          <Trash2 aria-hidden className="size-4" />
        </Button>
      </td>
    </tr>
  );
}

function ReviewTableHead() {
  const { t } = useI18n();
  const columns = [
    t.review.columns.ticker,
    t.review.columns.name,
    t.review.columns.quantity,
    t.review.columns.value,
    t.review.columns.currency,
    t.review.columns.account,
    t.review.columns.price,
    t.review.columns.valueCad,
    t.review.columns.status,
  ];
  return (
    <thead>
      <tr className="border-b border-ink-200 bg-ink-50 text-left text-xs text-ink-600">
        {columns.map((label) => (
          <th key={label} scope="col" className="px-2 py-2 font-semibold whitespace-nowrap">
            {label}
          </th>
        ))}
        <th scope="col" className="px-2 py-2">
          <span className="sr-only">{t.review.columns.actions}</span>
        </th>
      </tr>
    </thead>
  );
}

interface PositionsTableProps {
  rows: Row[];
  review: ReviewIndex;
  confirming: boolean;
  onChange: (key: string, patch: Partial<Row>) => void;
  onDelete: (key: string) => void;
}

export function PositionsTable({ rows, review, confirming, onChange, onDelete }: PositionsTableProps) {
  const { t } = useI18n();
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[1080px] text-sm">
        <ReviewTableHead />
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={10} className="px-3 py-6 text-center text-ink-500">
                {t.review.empty}
              </td>
            </tr>
          ) : null}
          {rows.map((row, index) => (
            <ReviewRow
              key={row.key}
              row={row}
              index={index}
              review={review}
              confirming={confirming}
              onChange={(patch) => onChange(row.key, patch)}
              onDelete={() => onDelete(row.key)}
            />
          ))}
        </tbody>
      </table>
      <datalist id="currency-options">
        <option value="CAD" />
        <option value="USD" />
        <option value="EUR" />
      </datalist>
    </div>
  );
}
