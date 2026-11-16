"use client";

import type { CSSProperties, ReactNode } from "react";
import type { DecisionPosition, PortfolioBuildResponse, StrategySummary } from "@/lib/contract/portfolio";
import { useI18n } from "@/lib/i18n/provider";
import { bandPosition, styleBand, styleNotes, type FactIndex, type StyleBand } from "@/lib/portfolio/decision";
import { formatFact, formatWeight } from "@/lib/portfolio/format";
import { cn } from "@/components/ui/cn";
import d from "./base.module.css";
import { FactChip, FactChips, useDecisionLookup } from "./facts";
import p from "./portfolio.module.css";

/** A CSS custom property set from a backend share, for geometry only. */
const share = (name: string, value: number): CSSProperties => ({ [name]: String(value) }) as CSSProperties;

/* ------------------------------------------------------------------ */
/* Positions                                                            */
/* ------------------------------------------------------------------ */

function roleClass(role: DecisionPosition["role"], index: number): string | undefined {
  if (role === "satellite") return p.sat;
  if (role === "coeur") return index % 2 === 1 ? p.coreAlt : "";
  return p.other;
}

/** The screen names the two roles it knows; any other role of the contract is shown as is. */
function roleLabel(role: DecisionPosition["role"], names: { core: string; satellite: string }): string {
  if (role === "coeur") return names.core;
  if (role === "satellite") return names.satellite;
  return role ?? "—";
}

/** One bar split by weight, core and satellite apart, and its legend. */
function AllocationBar({ positions }: { positions: DecisionPosition[] }) {
  const { t } = useI18n();
  const v = t.portfolioView.positions;
  const describe = (pos: DecisionPosition) => `${pos.asset_id} ${formatWeight(pos.weight)} (${roleLabel(pos.role, v)})`;
  return (
    <>
      <div className={p.alloc} role="img" aria-label={v.barAria(positions.map(describe).join(", "))}>
        {positions.map((pos, index) => (
          <span key={pos.asset_id} className={roleClass(pos.role, index)} style={share("--w", pos.weight)} title={`${pos.asset_id} · ${formatWeight(pos.weight)} · ${roleLabel(pos.role, v)}`} />
        ))}
      </div>
      <div className={p.legend} aria-hidden>
        <span>
          <i className={p.swatch} />
          {v.core}
        </span>
        <span>
          <i className={cn(p.swatch, p.swatchSat)} />
          {v.satellite}
        </span>
      </div>
    </>
  );
}

function PositionsTable({ positions }: { positions: DecisionPosition[] }) {
  const { t } = useI18n();
  const v = t.portfolioView.positions;
  return (
    <div className={d.tableWrap}>
      <table className={d.table} style={{ minWidth: 480 }}>
        <caption className="sr-only">{v.title}</caption>
        <thead>
          <tr>
            <th scope="col">{v.asset}</th>
            <th scope="col">{v.role}</th>
            <th scope="col" className={d.n}>
              {v.weight}
            </th>
            <th scope="col">{v.facts}</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((pos) => (
            <tr key={pos.asset_id} className={pos.role === "satellite" ? p.rowSat : undefined}>
              <td>
                <span className={d.ticker}>{pos.asset_id}</span>
              </td>
              <td>
                <span className={cn(d.chip, pos.role === "satellite" ? d.stop : d.navy)}>{roleLabel(pos.role, v)}</span>
              </td>
              <td className={cn(d.n, p.num)}>{formatWeight(pos.weight)}</td>
              <td>
                <FactChips ids={pos.rationale_fact_ids} limit={2} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Positions({ positions }: { positions: DecisionPosition[] }) {
  const { t } = useI18n();
  const v = t.portfolioView.positions;
  return (
    <section className={cn(d.tile, p.half)} aria-labelledby="pf-positions">
      <header>
        <h2 id="pf-positions">{v.title}</h2>
        <span className={d.cap} style={{ margin: 0 }}>
          {v.count(positions.length)}
        </span>
      </header>
      {positions.length === 0 ? (
        <p className={p.empty}>{v.none}</p>
      ) : (
        <>
          <AllocationBar positions={positions} />
          <PositionsTable positions={positions} />
        </>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Style and equity band                                                */
/* ------------------------------------------------------------------ */

/** What the marks of the band bar stand for, each with the fact behind it. */
function BandKeys({ band }: { band: StyleBand }) {
  const { t } = useI18n();
  const v = t.portfolioView.style;
  return (
    <ul className={p.bandKeys}>
      <li>
        <i className={p.keyZone} aria-hidden />
        <span>
          {v.min} – {v.cap}
        </span>
        <FactChip id="strat.e_min" compact />
        <FactChip id="strat.e_cap" compact />
      </li>
      {band.target ? (
        <li>
          <i className={p.keyMark} aria-hidden />
          <span>{v.target}</span>
          <FactChip id={band.target.fact_id} compact />
        </li>
      ) : (
        <li className={p.sub}>{v.noTarget}</li>
      )}
      {band.finalTarget ? (
        <li>
          <i className={cn(p.keyMark, p.keyMarkFinal)} aria-hidden />
          <span>{v.finalTarget}</span>
          <FactChip id={band.finalTarget.fact_id} compact />
        </li>
      ) : null}
      {band.pi ? (
        <li>
          <FactChip id={band.pi.fact_id} />
        </li>
      ) : null}
    </ul>
  );
}

function BandBar({ facts }: { facts: FactIndex }) {
  const { t } = useI18n();
  const v = t.portfolioView.style;
  const band = styleBand(facts);
  const min = bandPosition(band.eMin);
  const cap = bandPosition(band.eCap);
  const target = bandPosition(band.target);
  const final = bandPosition(band.finalTarget);
  if (!band.eMin || !band.eCap || min === null || cap === null) return null;
  const shown = band.finalTarget ?? band.target;
  return (
    <div className={p.block}>
      <h3>{v.band}</h3>
      <div
        className={p.band}
        role="img"
        aria-label={v.bandAria(formatFact(band.eMin), formatFact(band.eCap), shown ? formatFact(shown) : "—")}
        style={{ ...share("--min", min), ...share("--cap", cap) }}
      >
        <span className={p.track} />
        <span className={p.zone} />
        {target !== null ? <span className={cn(p.mark, final !== null && p.markBefore)} style={share("--at", target)} /> : null}
        {final !== null ? <span className={cn(p.mark, p.markFinal)} style={share("--at", final)} /> : null}
      </div>
      <div className={p.scale} aria-hidden>
        <span>0 %</span>
        <span>100 %</span>
      </div>
      <BandKeys band={band} />
    </div>
  );
}

/** The final floor of a satellite when the debate lowered it, else the floor of step 0; then its amount in dollars. */
function floorFactIds(facts: FactIndex, ticker: string): string[] {
  const floor = facts.has(`strat.final.floor.${ticker}`) ? `strat.final.floor.${ticker}` : `strat.floor.${ticker}`;
  return [floor, `strat.floor_cad.${ticker}`].filter((id) => facts.has(id));
}

function Shortlist({ shortlist }: { shortlist: string[] }) {
  const { t } = useI18n();
  const v = t.portfolioView.style;
  const { facts } = useDecisionLookup();
  return (
    <div className={p.block}>
      <h3>{v.shortlist}</h3>
      {shortlist.length === 0 ? (
        <p className={p.sub}>{v.noShortlist}</p>
      ) : (
        <div className={p.chips}>{shortlist.flatMap((ticker) => floorFactIds(facts, ticker).map((id) => <FactChip key={id} id={id} />))}</div>
      )}
    </div>
  );
}

/** A titled block of fact chips. */
function ChipBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className={p.block}>
      <h3>{title}</h3>
      <div className={p.chips}>{children}</div>
    </div>
  );
}

/** Step 0 as it ran: style, preference, band, satellites kept, sector caps, risk cost and notes. */
function StyleDetails({ strategy }: { strategy: StrategySummary }) {
  const { t } = useI18n();
  const v = t.portfolioView.style;
  const { facts } = useDecisionLookup();
  const notes = styleNotes(facts);
  return (
    <>
      <div className={p.styleHead}>
        <span className={cn(d.chip, d.navy, p.styleBadge)}>{v.badge(v.styles[strategy.style])}</span>
        <span className={p.sub}>{v.fromLevel(v.styles[strategy.from_level])}</span>
      </div>
      <div className={cn(p.chips, p.block)} style={{ marginTop: 10 }}>
        {notes.style ? <FactChip id={notes.style.fact_id} /> : null}
        {notes.preference ? <FactChip id={notes.preference.fact_id} /> : null}
        {notes.applied ? <FactChip id={notes.applied.fact_id} /> : null}
        {notes.k ? <FactChip id={notes.k.fact_id} /> : null}
      </div>
      <BandBar facts={facts} />
      <Shortlist shortlist={strategy.shortlist} />
      {notes.sectorCaps.length > 0 ? (
        <ChipBlock title={v.sectorCaps}>
          {notes.sectorCaps.map(({ fact }) => (
            <FactChip key={fact.fact_id} id={fact.fact_id} />
          ))}
        </ChipBlock>
      ) : null}
      {notes.riskCost || notes.baseRisk ? (
        <ChipBlock title={v.riskCost}>
          {notes.riskCost ? <FactChip id={notes.riskCost.fact_id} /> : null}
          {notes.baseRisk ? <FactChip id={notes.baseRisk.fact_id} /> : null}
        </ChipBlock>
      ) : null}
      {notes.notes.length > 0 ? (
        <ChipBlock title={v.notes}>
          {notes.notes.map((fact) => (
            <FactChip key={fact.fact_id} id={fact.fact_id} />
          ))}
        </ChipBlock>
      ) : null}
    </>
  );
}

export function StylePanel({ response }: { response: PortfolioBuildResponse }) {
  const { t } = useI18n();
  const v = t.portfolioView.style;
  const strategy = response.strategy;
  return (
    <section className={cn(d.tile, p.half)} aria-labelledby="pf-style">
      <header>
        <h2 id="pf-style">{v.title}</h2>
        {strategy ? (
          <span className={d.cap} style={{ margin: 0 }}>
            strategy.yaml@{strategy.version}
          </span>
        ) : null}
      </header>
      {strategy ? <StyleDetails strategy={strategy} /> : <p className={p.empty}>{v.off}</p>}
    </section>
  );
}
