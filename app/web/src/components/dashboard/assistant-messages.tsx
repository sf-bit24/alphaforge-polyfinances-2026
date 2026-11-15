"use client";

import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { cn } from "@/components/ui/cn";
import { YanMark, type YanMood } from "@/components/yan/yan";
import styles from "./dashboard.module.css";

export interface HowStep {
  tone: "neutral" | "stop" | "ok";
  title: string;
  detail?: string | null;
  meta?: string;
}

/** The trace of a request, in the draft's timeline style, folded under the message. */
export function HowIAnswered({ steps, t }: { steps: HowStep[]; t: Dictionary }) {
  if (steps.length === 0) return null;
  return (
    <details
      className={styles.how}
      onToggle={(event) => {
        // Opening the steps of the last answer brings them into view in the thread.
        if (event.currentTarget.open) event.currentTarget.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }}
    >
      <summary>
        <ChevronRight aria-hidden />
        {t.assistant.how(steps.length)}
      </summary>
      <ul className={styles.trace}>
        {steps.map((step, index) => (
          <li key={`${step.title}-${index}`} className={step.tone === "neutral" ? undefined : styles[step.tone]}>
            <b>{step.title}</b>
            {step.detail}
            {step.meta ? <small>{step.meta}</small> : null}
          </li>
        ))}
      </ul>
    </details>
  );
}

export function Sources({ items, tag }: { items: string[]; tag?: string }) {
  if (items.length === 0 && !tag) return null;
  return (
    <div className={styles.meta}>
      {tag ? <span className={styles.tag}>{tag}</span> : null}
      {items.map((item) => (
        <span key={item} className={styles.src}>
          {item}
        </span>
      ))}
    </div>
  );
}

/** A message from Yan; `asks` marks the one whose questions are open, read from its start; `mood` is Yan's face. */
export function AgentMessage({ children, asks = false, mood }: { children: ReactNode; asks?: boolean; mood?: YanMood }) {
  return (
    <div className={styles.msg} data-asks={asks || undefined}>
      <YanMark className={styles.avatar} mood={mood} />
      <div className={styles.body}>{children}</div>
    </div>
  );
}

export function UserBubble({ children }: { children: ReactNode }) {
  return (
    <div className={cn(styles.msg, styles.user)}>
      <div className={styles.bubble}>{children}</div>
    </div>
  );
}
