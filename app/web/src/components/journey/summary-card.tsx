"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import type { ClientState, DimensionView, RiskLevel } from "@/lib/contract/schemas";
import { curly, formatPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { withoutLabel } from "@/lib/journey/summary";
import s from "./journey.module.css";

const summaryOf = (view: DimensionView | undefined) => view?.summary ?? null;

/** At the house: what the runtime understood, per dimension, and the way on to the dashboard. */
export function SummaryCard({
  state,
  autoFocus,
  busy,
  onOpenProfile,
  onRestart,
}: {
  state: ClientState;
  autoFocus: boolean;
  busy: boolean;
  onOpenProfile: () => void;
  onRestart: () => void;
}) {
  const { t, locale } = useI18n();
  const ctaRef = useRef<HTMLAnchorElement>(null);
  const { profile, completeness } = state;
  const complete = state.stage === "complete";
  const level = (value: RiskLevel | null | undefined) => (value ? t.riskLevels[value] : null);
  const rows: Array<[string, string | null]> = [
    [t.journey.summary.rows.knowledge, profile.knowledge_level ? t.knowledgeLevels[profile.knowledge_level] : null],
    [t.journey.summary.rows.objective, summaryOf(profile.dimensions.objective)],
    [t.journey.summary.rows.horizon, summaryOf(profile.dimensions.horizon)],
    [t.journey.summary.rows.tolerance, summaryOf(profile.dimensions.risk_tolerance) ?? level(profile.risk?.tolerance)],
    [t.journey.summary.rows.capacity, summaryOf(profile.dimensions.risk_capacity) ?? level(profile.risk?.capacity)],
    [t.journey.summary.rows.effective, profile.effective_risk ? t.journey.summary.effective(t.riskLevels[profile.effective_risk]) : null],
    [t.journey.summary.rows.constraints, summaryOf(profile.dimensions.constraints)],
    [t.journey.summary.rows.preferences, summaryOf(profile.dimensions.preferences)],
    [t.journey.summary.rows.context, summaryOf(profile.dimensions.context)],
  ];
  const pct = (value: number) => `${Math.max(0, Math.min(1, value)) * 100}%`;

  useEffect(() => {
    if (autoFocus) ctaRef.current?.focus({ preventScroll: true });
  }, [autoFocus]);

  return (
    <>
      <div className={s.say}>
        <span className={s.avatar} aria-hidden>
          A
        </span>
        <p>{complete ? t.journey.say.summaryComplete : t.journey.say.summaryFollowups}</p>
      </div>
      <h2>{complete ? t.journey.summary.titleComplete : t.journey.summary.titleFollowups}</h2>
      <dl>
        {rows
          .filter(([, value]) => value !== null)
          .map(([label, value]) => (
            <div key={label} className="contents">
              <dt>{label}</dt>
              <dd>{value ? curly(withoutLabel(label, value)) : value}</dd>
            </div>
          ))}
      </dl>
      <div className={s.meter}>
        <p>
          {t.journey.summary.completeness(formatPercent(completeness.displayed, locale))} ·{" "}
          {completeness.ready ? t.journey.summary.ready : t.journey.summary.threshold(formatPercent(completeness.threshold, locale))}
        </p>
        <div
          className={s.meterTrack}
          role="meter"
          aria-label={t.panel.completeness}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(completeness.displayed * 100)}
        >
          <i style={{ width: pct(completeness.displayed) }} />
          <b style={{ left: `calc(${pct(completeness.threshold)} - 1px)` }} />
        </div>
      </div>
      <div className={s.next}>
        <Link ref={ctaRef} href="/dashboard" className={`${s.cta} ${s.ctaSmall}`}>
          {t.journey.summary.toDashboard}
        </Link>
        <button type="button" className={s.ghost} onClick={onOpenProfile}>
          {t.journey.summary.details}
        </button>
        <button type="button" className={s.ghost} onClick={onRestart} disabled={busy}>
          {t.journey.summary.restart}
        </button>
      </div>
    </>
  );
}
