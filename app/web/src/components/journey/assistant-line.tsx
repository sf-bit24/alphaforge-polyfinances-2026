"use client";

import type { ReactNode } from "react";
import { YanMark, type YanMood } from "@/components/yan/yan";
import styles from "./journey.module.css";

/**
 * The line of Yan, the personal assistant, at the top of a card, after its avatar. A
 * short text is one paragraph; Yan's own message (A1's markdown) comes as blocks. Yan
 * flies in from where it was last seen (the landing, the card before) when the card shows.
 */
export function AssistantLine({ children, mood }: { children: ReactNode; mood?: YanMood }) {
  return (
    <div className={styles.say}>
      <YanMark className={styles.avatar} arrive="last" mood={mood} />
      {typeof children === "string" ? <p>{children}</p> : <div className={styles.sayRich}>{children}</div>}
    </div>
  );
}
