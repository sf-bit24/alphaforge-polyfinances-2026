"use client";

import { Bot, CircleCheck, CirclePlus, ListPlus, Trash2 } from "lucide-react";
import { useState } from "react";
import type { PositionInput } from "@/lib/contract/requests";
import type { AccountType, PortfolioView, Position } from "@/lib/contract/schemas";
import { ACCOUNT_TYPES } from "@/lib/contract/schemas";
import { parseNumberInput } from "@/lib/client/answers";
import { useSession } from "@/lib/client/session";
import { formatDate, formatMoney, formatNumber } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Markdown } from "@/components/ui/markdown";
import { ExposuresView, FxNote } from "./exposures";

interface Row {
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

function rowOf(position: Position): Row {
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

function blankPosition(id: string, raw: string | null): Position {
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
function toInput(row: Row): PositionInput {
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

const CELL =
  "w-full rounded-md border-0 bg-white px-2 py-1.5 text-sm text-ink-950 ring-1 ring-ink-200 ring-inset focus:ring-2 focus:ring-brand-500 focus:outline-none aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-critical";

/** `portfolio_review`: the investor corrects A2's positions, then confirms. */
export function PortfolioReviewStep({ portfolio, message }: { portfolio: PortfolioView; message: string | null }) {
  const { t, locale } = useI18n();
  const session = useSession();
  const [rows, setRows] = useState<Row[]>(() => portfolio.positions.map(rowOf));
  const [problem, setProblem] = useState<string | null>(null);
  const [counter, setCounter] = useState(1);
  const confirming = session.pending === "portfolio.confirm";
  const edited = rows.some((row) => row.edited) || rows.length !== portfolio.positions.length;
  // An unresolved item with a `position_id` is shown on its row; the others (unreadable files...) in a list below.
  const rowIds = new Set(portfolio.positions.map((position) => position.id));
  const unresolvedById = new Map(
    portfolio.unresolved.flatMap((item) => (item.position_id && rowIds.has(item.position_id) ? [[item.position_id, item] as const] : [])),
  );
  const looseUnresolved = portfolio.unresolved.filter((item) => !item.position_id || !rowIds.has(item.position_id));

  const update = (key: string, patch: Partial<Row>) =>
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch, edited: true } : row)));

  const addRow = (raw: string | null = null) => {
    const id = `u${counter}`;
    setCounter(counter + 1);
    setRows((current) => [...current, { ...rowOf(blankPosition(id, raw)), edited: true }]);
  };

  // A row proposed by A2 may stay without a ticker (unresolved, left unvalued by code);
  // a row added by the investor needs a ticker or a declared value.
  const invalid = (row: Row) => ({
    ticker: row.ticker.trim() === "" && !rowIds.has(row.key) && row.marketValue.trim() === "",
    quantity: row.quantity.trim() !== "" && (parseNumberInput(row.quantity) === null || (parseNumberInput(row.quantity) ?? 0) < 0),
    marketValue:
      row.marketValue.trim() !== "" && (parseNumberInput(row.marketValue) === null || (parseNumberInput(row.marketValue) ?? 0) < 0),
    currency: row.currency.trim() !== "" && !/^[A-Za-z]{3}$/.test(row.currency.trim()),
  });

  const confirm = () => {
    if (rows.length === 0) {
      setProblem(t.review.needOne);
      return;
    }
    const issues = rows.map(invalid);
    if (issues.some((issue) => issue.ticker)) {
      setProblem(t.review.needTicker);
      return;
    }
    if (issues.some((issue) => issue.quantity || issue.marketValue || issue.currency)) {
      setProblem(t.question.enterNumber);
      return;
    }
    setProblem(null);
    void session.confirmPortfolio(rows.map(toInput));
  };

  return (
    <div className="animate-fade-in space-y-5">
      {message ? (
        <Card>
          <div className="flex gap-3 px-5 py-4">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-kind-agent text-white">
              <Bot aria-hidden className="size-4" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-ink-600">A2 · {t.stages.portfolio_review}</p>
              <Markdown className="mt-1">{message}</Markdown>
            </div>
          </div>
        </Card>
      ) : null}

      <Card>
        <CardHeader title={t.review.title} subtitle={t.review.intro} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1080px] text-sm">
            <thead>
              <tr className="border-b border-ink-200 bg-ink-50 text-left text-xs text-ink-600">
                {[
                  t.review.columns.ticker,
                  t.review.columns.name,
                  t.review.columns.quantity,
                  t.review.columns.value,
                  t.review.columns.currency,
                  t.review.columns.account,
                  t.review.columns.price,
                  t.review.columns.valueCad,
                  t.review.columns.status,
                ].map((label) => (
                  <th key={label} scope="col" className="px-3 py-2 font-semibold whitespace-nowrap">
                    {label}
                  </th>
                ))}
                <th scope="col" className="px-3 py-2">
                  <span className="sr-only">{t.review.columns.actions}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={10} className="px-3 py-6 text-center text-ink-500">
                    {t.review.empty}
                  </td>
                </tr>
              ) : null}
              {rows.map((row, index) => {
                const label = row.ticker || t.review.rowLabel(index + 1);
                const issue = invalid(row);
                const base = row.base;
                return (
                  <tr key={row.key} className={cn("border-b border-ink-150 align-top", row.edited && "bg-brand-50/30")}>
                    <td className="w-32 px-3 py-2">
                      <input
                        value={row.ticker}
                        onChange={(event) => update(row.key, { ticker: event.target.value })}
                        aria-label={`${t.review.columns.ticker}, ${t.review.rowLabel(index + 1)}`}
                        aria-invalid={issue.ticker || undefined}
                        placeholder={t.review.tickerPlaceholder}
                        className={cn(CELL, "min-w-28 font-mono uppercase")}
                        disabled={confirming}
                      />
                      {base.raw ? <p className="mt-1 truncate font-mono text-[0.65rem] text-ink-400" title={base.raw}>{base.raw}</p> : null}
                    </td>
                    <td className="max-w-48 px-3 py-2">
                      <p className="truncate font-medium text-ink-900" title={base.name ?? undefined}>
                        {base.name ?? "—"}
                      </p>
                      {base.asset_class ? <p className="text-xs text-ink-500">{t.assetClasses[base.asset_class]}</p> : null}
                    </td>
                    <td className="w-28 px-3 py-2">
                      <input
                        value={row.quantity}
                        inputMode="decimal"
                        onChange={(event) => update(row.key, { quantity: event.target.value })}
                        aria-label={`${t.review.columns.quantity}, ${t.review.rowLabel(index + 1)}`}
                        aria-invalid={issue.quantity || undefined}
                        className={cn(CELL, "min-w-24 text-right tabular-nums")}
                        disabled={confirming}
                      />
                    </td>
                    <td className="w-32 px-3 py-2">
                      <input
                        value={row.marketValue}
                        inputMode="decimal"
                        onChange={(event) => update(row.key, { marketValue: event.target.value })}
                        aria-label={`${t.review.columns.value}, ${t.review.rowLabel(index + 1)}`}
                        aria-invalid={issue.marketValue || undefined}
                        className={cn(CELL, "min-w-28 text-right tabular-nums")}
                        disabled={confirming}
                      />
                    </td>
                    <td className="w-20 px-3 py-2">
                      <input
                        value={row.currency}
                        list="currency-options"
                        maxLength={3}
                        onChange={(event) => update(row.key, { currency: event.target.value.toUpperCase() })}
                        aria-label={`${t.review.columns.currency}, ${t.review.rowLabel(index + 1)}`}
                        aria-invalid={issue.currency || undefined}
                        className={cn(CELL, "min-w-18 font-mono uppercase")}
                        disabled={confirming}
                      />
                    </td>
                    <td className="w-36 px-3 py-2">
                      <select
                        value={row.account}
                        onChange={(event) => update(row.key, { account: event.target.value as AccountType | "" })}
                        aria-label={`${t.review.columns.account}, ${t.review.rowLabel(index + 1)}`}
                        className={cn(CELL, "min-w-40")}
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
                    <td className="px-3 py-2 whitespace-nowrap tabular-nums">
                      {typeof base.price === "number" ? (
                        <span
                          title={base.price_date && base.price_source ? t.review.priceSource(formatDate(base.price_date, locale), base.price_source) : undefined}
                        >
                          {formatNumber(base.price, locale)} <span className="text-xs text-ink-500">{base.currency}</span>
                          {base.price_date ? <span className="block text-[0.65rem] text-ink-500">{formatDate(base.price_date, locale)}</span> : null}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap tabular-nums">
                      {typeof base.value_cad === "number" && !row.edited ? formatMoney(base.value_cad, locale, "CAD") : "—"}
                    </td>
                    <td className="px-3 py-2">
                      {row.edited ? (
                        <Badge tone="brand">{t.review.edited}</Badge>
                      ) : base.resolved ? (
                        <Badge tone="good" icon={<CircleCheck aria-hidden className="size-3" />}>
                          {t.review.resolved}
                        </Badge>
                      ) : (
                        <Badge tone="warning">{t.review.unresolved}</Badge>
                      )}
                      {unresolvedById.has(base.id) && unresolvedById.get(base.id)?.reason !== base.notes ? (
                        <p className="mt-1 max-w-48 text-[0.7rem] leading-snug text-warning-ink">{unresolvedById.get(base.id)?.reason}</p>
                      ) : null}
                      {base.notes ? <p className="mt-1 max-w-48 text-[0.7rem] leading-snug text-ink-500">{base.notes}</p> : null}
                    </td>
                    <td className="px-2 py-2">
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() => setRows((current) => current.filter((candidate) => candidate.key !== row.key))}
                        aria-label={t.review.deleteRow(label)}
                        disabled={confirming}
                      >
                        <Trash2 aria-hidden className="size-4" />
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <datalist id="currency-options">
            <option value="CAD" />
            <option value="USD" />
            <option value="EUR" />
          </datalist>
        </div>
        <div className="flex flex-wrap items-center gap-3 px-5 py-3">
          <Button variant="secondary" size="sm" onClick={() => addRow()} icon={<CirclePlus aria-hidden className="size-4" />} disabled={confirming}>
            {t.review.addRow}
          </Button>
          <FxNote fx={portfolio.fx} className="ml-auto" />
        </div>
        {looseUnresolved.length > 0 ? (
          <div className="border-t border-ink-150 px-5 py-4">
            <h3 className="text-sm font-semibold text-ink-900">{t.review.unresolvedTitle}</h3>
            <ul className="mt-2 space-y-2">
              {looseUnresolved.map((item, index) => (
                <li key={`${item.raw}-${index}`} className="flex flex-wrap items-center gap-3 rounded-lg bg-warning-wash px-3 py-2 text-sm ring-1 ring-warning/40">
                  <span className="font-mono text-ink-900">{item.raw}</span>
                  <span className="flex-1 text-xs text-ink-600">{item.reason}</span>
                  <Button size="sm" variant="ghost" onClick={() => addRow(item.raw)} icon={<ListPlus aria-hidden className="size-4" />} disabled={confirming}>
                    {t.review.addAsRow}
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <footer className="space-y-3 border-t border-ink-150 px-5 py-4">
          {problem ? (
            <p role="alert" className="text-sm font-medium text-critical-ink">
              {problem}
            </p>
          ) : null}
          {session.error && session.errorAction === "portfolio.confirm" ? (
            <ErrorNotice error={session.error} onRetry={session.retry} onDismiss={session.dismissError} />
          ) : null}
          <div className="flex justify-end">
            <Button size="lg" onClick={confirm} loading={confirming} icon={<CircleCheck aria-hidden className="size-4" />}>
              {confirming ? t.review.confirming : t.review.confirm}
            </Button>
          </div>
        </footer>
      </Card>

      <Card>
        <CardHeader title={t.exposures.title} subtitle={edited ? t.review.staleNote : t.exposures.computedByCode} />
        <div className="px-5 py-5">
          <ExposuresView exposures={portfolio.exposures} positions={portfolio.positions} sources={portfolio.sources} fx={portfolio.fx} stale={edited} />
        </div>
      </Card>
    </div>
  );
}
