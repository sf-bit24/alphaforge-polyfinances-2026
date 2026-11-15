"use client";

import type { ReactNode } from "react";
import { YanMark } from "@/components/yan/yan";
import styles from "./journey.module.css";

/**
 * The line of Yan, the personal assistant, at the top of a card, after its avatar. A
 * short text is one paragraph; Yan's own message (A1's markdown) comes as blocks.
 */
export function AssistantLine({ children }: { children: ReactNode }) {
  return (
    <div className={styles.say}>
      <YanMark className={styles.avatar} />
      {typeof children === "string" ? <p>{children}</p> : <div className={styles.sayRich}>{children}</div>}
    </div>
  );
}
