"use client";

import type { CSSProperties, ReactNode } from "react";
import type { Allocation, AllocationSectorBucket } from "@/lib/contract/portfolio";
import { useI18n } from "@/lib/i18n/provider";
import { allocationAmount, allocationShare, bucketLabel } from "@/lib/portfolio/allocation";
import d from "./base.module.css";
import { cn } from "@/components/ui/cn";
import { FactChip, useDecisionLookup } from "./facts";
import p from "./portfolio.module.css";

/** The engine's weight of a row as the bar's width: geometry only. */
const width = (weight: number): CSSProperties => ({ "--w": String(weight) }) as CSSProperties;

type Row = Pick<AllocationSectorBucket, "key" | "label_fr" | "weight" | "amount_cad" | "fact_id" | "basis">;

const FILL_CLASS: Record<string, string | undefined> = { lookthrough: p.fillLook, non_ventile: p.fillNone };

/** One row: label, share and amount as the engine gave them, its fact, and a bar of the same share. */
function BreakdownRow({ row, names }: { row: Row; names: Readonly<Record<string, string>> }) {
  const { t, locale } = useI18n();
  const v = t.portfolioView.allocation;
  const { facts } = useDecisionLookup();
  const label = bucketLabel(row, names);
  const share = allocationShare(row.weight, locale);
  const amount = allocationAmount(row.amount_cad, locale);
  const basis = row.basis === "lookthrough" ? v.basis.lookthrough : null;
  return (
    <li className={p.allocRow}>
      <div className={p.allocHead}>
        <span className={p.allocLabel}>
          {label}
          {basis ? <span className={p.allocBasis}> · {basis}</span> : null}
        </span>
        <span className={p.allocFigures}>
          <b className={p.num}>{share}</b>
          {amount ? <span className={p.num}>{amount}</span> : null}
        </span>
        {row.fact_id && facts.has(row.fact_id) ? <FactChip id={row.fact_id} compact /> : null}
      </div>
      <div className={p.allocTrack} aria-hidden title={v.row(label, share, amount)}>
        <span className={FILL_CLASS[row.basis ?? ""]} style={width(row.weight)} />
      </div>
    </li>
  );
}

function Breakdown({ id, title, rows, names, children }: { id: string; title: string; rows: Row[]; names: Readonly<Record<string, string>>; children?: ReactNode }) {
  if (rows.length === 0) return null;
  return (
    <div className={p.allocBlock}>
      <h3 id={id}>{title}</h3>
      <ul className={p.allocRows} aria-labelledby={id}>
        {rows.map((row) => (
          <BreakdownRow key={row.key} row={row} names={names} />
        ))}
      </ul>
      {children}
    </div>
  );
}

/** « Répartition de votre argent »: the engine's breakdown by asset type, sector and currency, in % and $. */
export function AllocationBreakdown({ allocation }: { allocation: Allocation | null | undefined }) {
  const { t, locale } = useI18n();
  const v = t.portfolioView.allocation;
  if (!allocation || (allocation.by_class.length === 0 && allocation.by_sector.length === 0 && allocation.by_currency.length === 0)) return null;
  const total = allocationAmount(allocation.amount_cad, locale);
  const coverage = allocation.sector_coverage;
  return (
    <section className={cn(d.tile, d.tWide)} aria-labelledby="pf-alloc">
      <header>
        <h2 id="pf-alloc">{v.title}</h2>
        {total ? (
          <span className={p.allocTotal}>
            <span className={d.cap} style={{ margin: 0 }}>
              {v.total}
            </span>
            <b className={p.num}>{total}</b>
          </span>
        ) : null}
      </header>
      <p className={p.sub} style={{ marginTop: -8, marginBottom: 14 }}>
        {v.lead}
      </p>
      <div className={p.allocGrid}>
        <Breakdown id="pf-alloc-class" title={v.byClass} rows={allocation.by_class} names={v.classes} />
        <Breakdown id="pf-alloc-sector" title={v.bySector} rows={allocation.by_sector} names={{}}>
          {coverage !== null && coverage !== undefined && coverage < 1 ? (
            <p className={cn(p.sub, p.allocNote)} role="note">
              {v.coverage(allocationShare(coverage, locale))}
            </p>
          ) : null}
        </Breakdown>
        <Breakdown id="pf-alloc-currency" title={v.byCurrency} rows={allocation.by_currency} names={v.currencies} />
      </div>
    </section>
  );
}
