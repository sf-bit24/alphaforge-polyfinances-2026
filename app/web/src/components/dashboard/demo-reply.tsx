"use client";

import Link from "next/link";
import type { Locale } from "@/lib/contract/schemas";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { useI18n } from "@/lib/i18n/provider";
import { DEMO, type DemoAction, type DemoKey } from "@/lib/sample/assistant-demo";
import { tr } from "@/lib/sample/portfolio";
import { cn } from "@/components/ui/cn";
import { AgentMessage, HowIAnswered, Sources } from "./assistant-messages";
import styles from "./dashboard.module.css";

type DemoScript = (typeof DEMO)[DemoKey];

function DemoVerdict({ verdict, locale }: { verdict: NonNullable<DemoScript["verdict"]>; locale: Locale }) {
  return (
    <div className={cn(styles.verdict, verdict.ok && styles.verdictOk)}>
      <div className={styles.verdictH}>
        {tr(verdict.title, locale)}
        <span>{tr(verdict.by, locale)}</span>
      </div>
      <div className={styles.checks}>
        {verdict.checks.map((check) => (
          <div key={check.label.fr} className={styles.check}>
            <span>{tr(check.label, locale)}</span>
            <b className={check.ok ? styles.good : styles.bad}>{tr(check.value, locale)}</b>
            <span>{tr(check.cap, locale)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DemoReasons({ reasons, locale }: { reasons: NonNullable<DemoScript["reasons"]>; locale: Locale }) {
  return (
    <div className={cn(styles.verdict, styles.verdictPlain)}>
      <ol className={styles.reasons}>
        {reasons.map((reason) => (
          <li key={reason.title.fr}>
            <span>
              <b>{tr(reason.title, locale)}</b> {tr(reason.text, locale)}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function DemoActions({ actions, onAction, t, locale }: { actions: DemoAction[]; onAction: (action: DemoAction) => void; t: Dictionary; locale: Locale }) {
  return (
    <div className={styles.actions}>
      {actions.map((action) =>
        action.href ? (
          <Link key={action.key} href={action.href} className={cn(styles.btn, action.primary && styles.btnPrimary)}>
            {tr(action.label, locale)}
          </Link>
        ) : (
          <button
            key={action.key}
            type="button"
            className={cn(styles.btn, action.primary && styles.btnPrimary)}
            onClick={() => onAction(action)}
            disabled={action.key === "noop"}
            title={action.key === "noop" ? t.assistant.exampleOnly : undefined}
          >
            {tr(action.label, locale)}
          </button>
        ),
      )}
    </div>
  );
}

/** A scripted answer of the draft (`mock` mode), tagged as a simulated example. */
export function DemoReply({ demoKey, onAction }: { demoKey: DemoKey; onAction: (action: DemoAction) => void }) {
  const { t, locale } = useI18n();
  const reply = DEMO[demoKey];
  return (
    <AgentMessage>
      {reply.paragraphs.map((paragraph) => (
        <p key={paragraph.fr}>{tr(paragraph, locale)}</p>
      ))}
      {reply.verdict ? <DemoVerdict verdict={reply.verdict} locale={locale} /> : null}
      {reply.reasons ? <DemoReasons reasons={reply.reasons} locale={locale} /> : null}
      {reply.closing ? <p style={{ marginTop: 14 }}>{tr(reply.closing, locale)}</p> : null}
      <Sources items={reply.sources.map((source) => tr(source, locale))} tag={t.assistant.sampleTag} />
      {reply.actions.length > 0 ? <DemoActions actions={reply.actions} onAction={onAction} t={t} locale={locale} /> : null}
      <HowIAnswered steps={reply.trace.map((step) => ({ tone: step.tone, title: tr(step.title, locale), detail: tr(step.detail, locale) }))} t={t} />
    </AgentMessage>
  );
}
