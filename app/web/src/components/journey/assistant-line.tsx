"use client";

import type { ReactNode } from "react";
import styles from "./journey.module.css";

/** The line of Yan, the personal assistant, at the top of a card, after its avatar. */
export function AssistantLine({ children }: { children: ReactNode }) {
  return (
    <div className={styles.say}>
      <span className={styles.avatar} aria-hidden>
        Y
      </span>
      <p>{children}</p>
    </div>
  );
}
