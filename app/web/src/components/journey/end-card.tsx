"use client";

import { MessageCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef } from "react";
import type { ClientState } from "@/lib/contract/schemas";
import { useI18n } from "@/lib/i18n/provider";
import s from "./journey.module.css";

/**
 * At the house: the base questionnaire is over. No profile here: the card hands over to
 * Yan's follow-ups (A1), shown beside it on wide screens, or in a drawer (`onOpenChat`).
 */
export function EndCard({
  state,
  side,
  autoFocus,
  busy,
  onOpenChat,
  onRestart,
}: {
  state: ClientState;
  /** The conversation stands on the right of the screen. */
  side: boolean;
  autoFocus: boolean;
  busy: boolean;
  onOpenChat: () => void;
  onRestart: () => void;
}) {
  const { t } = useI18n();
  const ctaRef = useRef<HTMLElement | null>(null);
  const complete = state.stage === "complete";

  useEffect(() => {
    // Beside the conversation, the focus belongs to Yan's questions (the chat's own fields).
    if (autoFocus && (complete || !side)) ctaRef.current?.focus({ preventScroll: true });
  }, [autoFocus, complete, side]);

  return (
    <>
      <div className={s.say}>
        <span className={s.avatar} aria-hidden>
          Y
        </span>
        <p>{complete ? t.journey.say.endComplete : t.journey.say.endFollowups}</p>
      </div>
      <h2>{complete ? t.journey.end.titleComplete : t.journey.end.titleFollowups}</h2>
      <p className={s.lead}>{complete ? t.journey.end.leadComplete : side ? t.journey.end.leadSide : t.journey.end.leadInline}</p>
      <div className={s.next}>
        {complete ? (
          <Link ref={(node) => void (ctaRef.current = node)} href="/dashboard" className={`${s.cta} ${s.ctaSmall}`}>
            {t.journey.end.toDashboard}
          </Link>
        ) : side ? (
          <Link href="/dashboard" className={s.ghost}>
            {t.journey.end.later}
          </Link>
        ) : (
          <>
            <button ref={(node) => void (ctaRef.current = node)} type="button" className={`${s.cta} ${s.ctaSmall}`} onClick={onOpenChat}>
              <MessageCircle aria-hidden className="size-5" />
              {t.journey.end.openChat}
            </button>
            <Link href="/dashboard" className={s.ghost}>
              {t.journey.end.later}
            </Link>
          </>
        )}
        <button type="button" className={s.ghost} onClick={onRestart} disabled={busy}>
          {t.journey.end.restart}
        </button>
      </div>
    </>
  );
}
