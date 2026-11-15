"use client";

import { MessageCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef } from "react";
import type { ClientState } from "@/lib/contract/schemas";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { useI18n } from "@/lib/i18n/provider";
import { AssistantLine } from "./assistant-line";
import styles from "./journey.module.css";

interface EndCardProps {
  state: ClientState;
  /** Yan's conversation stands on the right of the screen; otherwise it opens in a drawer. */
  side: boolean;
  autoFocus: boolean;
  busy: boolean;
  onOpenChat: () => void;
  onRestart: () => void;
}

function endTexts(t: Dictionary, complete: boolean, side: boolean) {
  if (complete) return { say: t.journey.say.endComplete, title: t.journey.end.titleComplete, lead: t.journey.end.leadComplete };
  return { say: t.journey.say.endFollowups, title: t.journey.end.titleFollowups, lead: side ? t.journey.end.leadSide : t.journey.end.leadInline };
}

/** The main action: the dashboard once complete, Yan's drawer when the conversation is not beside. */
function MainAction({ complete, side, ctaRef, onOpenChat }: Pick<EndCardProps, "side" | "onOpenChat"> & { complete: boolean; ctaRef: (node: HTMLElement | null) => void }) {
  const { t } = useI18n();
  if (complete) {
    return (
      <Link ref={ctaRef} href="/dashboard" className={`${styles.cta} ${styles.ctaSmall}`}>
        {t.journey.end.toDashboard}
      </Link>
    );
  }
  if (side) return null;
  return (
    <button ref={ctaRef} type="button" className={`${styles.cta} ${styles.ctaSmall}`} onClick={onOpenChat}>
      <MessageCircle aria-hidden className="size-5" />
      {t.journey.end.openChat}
    </button>
  );
}

/**
 * At the house: the base questionnaire is over. No profile here: the card hands over to
 * Yan's follow-ups (A1), shown beside it on wide screens, or in a drawer (`onOpenChat`).
 */
export function EndCard({ state, side, autoFocus, busy, onOpenChat, onRestart }: EndCardProps) {
  const { t } = useI18n();
  const ctaRef = useRef<HTMLElement | null>(null);
  const complete = state.stage === "complete";
  const texts = endTexts(t, complete, side);

  useEffect(() => {
    // Beside the conversation, the focus belongs to Yan's questions.
    if (autoFocus) ctaRef.current?.focus({ preventScroll: true });
  }, [autoFocus, complete, side]);

  return (
    <>
      <AssistantLine>{texts.say}</AssistantLine>
      <h2>{texts.title}</h2>
      <p className={styles.lead}>{texts.lead}</p>
      <div className={styles.next}>
        <MainAction complete={complete} side={side} ctaRef={(node) => void (ctaRef.current = node)} onOpenChat={onOpenChat} />
        {complete ? null : (
          <Link href="/dashboard" className={styles.ghost}>
            {t.journey.end.later}
          </Link>
        )}
        <button type="button" className={styles.ghost} onClick={onRestart} disabled={busy}>
          {t.journey.end.restart}
        </button>
      </div>
    </>
  );
}
