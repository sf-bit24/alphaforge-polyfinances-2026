"use client";

import Link from "next/link";
import { useEffect, useRef, type RefObject } from "react";
import type { ClientState, Completeness, DimensionView, RiskLevel } from "@/lib/contract/schemas";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { curly, formatPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { withoutLabel } from "@/lib/journey/summary";
import { sharePercent } from "@/components/profile/meters";
import { AssistantLine } from "./assistant-line";
import styles from "./journey.module.css";

const summaryOf = (view: DimensionView | undefined) => view?.summary ?? null;

/** Label and value of each row; the value is null while the profile does not say. */
function summaryRows(profile: ClientState["profile"], t: Dictionary): Array<[string, string | null]> {
  const level = (value: RiskLevel | null | undefined) => (value ? t.riskLevels[value] : null);
  return [
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
}

function SummaryMeter({ completeness }: { completeness: Completeness }) {
  const { t, locale } = useI18n();
  return (
    <div className={styles.meter}>
      <p>
        {t.journey.summary.completeness(formatPercent(completeness.displayed, locale))} ·{" "}
        {completeness.ready ? t.journey.summary.ready : t.journey.summary.threshold(formatPercent(completeness.threshold, locale))}
      </p>
      <div
        className={styles.meterTrack}
        role="meter"
        aria-label={t.panel.completeness}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(completeness.displayed * 100)}
      >
        <i style={{ width: sharePercent(completeness.displayed) }} />
        <b style={{ left: `calc(${sharePercent(completeness.threshold)} - 1px)` }} />
      </div>
    </div>
  );
}

interface SummaryActionsProps {
  ctaRef: RefObject<HTMLAnchorElement | null>;
  busy: boolean;
  onOpenProfile: () => void;
  onRestart: () => void;
}

function SummaryActions({ ctaRef, busy, onOpenProfile, onRestart }: SummaryActionsProps) {
  const { t } = useI18n();
  return (
    <div className={styles.next}>
      <Link ref={ctaRef} href="/dashboard" className={`${styles.cta} ${styles.ctaSmall}`}>
        {t.journey.summary.toDashboard}
      </Link>
      <button type="button" className={styles.ghost} onClick={onOpenProfile}>
        {t.journey.summary.details}
      </button>
      <button type="button" className={styles.ghost} onClick={onRestart} disabled={busy}>
        {t.journey.summary.restart}
      </button>
    </div>
  );
}

interface SummaryCardProps {
  state: ClientState;
  autoFocus: boolean;
  busy: boolean;
  onOpenProfile: () => void;
  onRestart: () => void;
}

/** At the house: what the runtime understood, per dimension, and the way on to the dashboard. */
export function SummaryCard({ state, autoFocus, busy, onOpenProfile, onRestart }: SummaryCardProps) {
  const { t } = useI18n();
  const ctaRef = useRef<HTMLAnchorElement>(null);
  const complete = state.stage === "complete";
  const rows = summaryRows(state.profile, t);

  useEffect(() => {
    if (autoFocus) ctaRef.current?.focus({ preventScroll: true });
  }, [autoFocus]);

  return (
    <>
      <AssistantLine>{complete ? t.journey.say.summaryComplete : t.journey.say.summaryFollowups}</AssistantLine>
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
      <SummaryMeter completeness={state.completeness} />
      <SummaryActions ctaRef={ctaRef} busy={busy} onOpenProfile={onOpenProfile} onRestart={onRestart} />
    </>
  );
}
