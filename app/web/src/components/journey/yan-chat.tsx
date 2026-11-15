"use client";

import type { CSSProperties } from "react";
import type { ClientState } from "@/lib/contract/schemas";
import { useViewport } from "@/lib/client/use-viewport";
import { NARROW } from "@/lib/journey/geometry";
import { formatPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { itemForStage } from "@/lib/journey/path";
import { Assistant } from "@/components/dashboard/assistant";
import { cn } from "@/components/ui/cn";
import styles from "./journey.module.css";

/** Narrower windows keep Yan's conversation in a drawer: beside the card, both would be too cramped. */
const SIDE_MIN_WIDTH = 1100;
const SIDE_MARGIN = 24;
const SIDE_TOP = 84;

/** Yan's conversation stands on the right of the screen: wide enough, and at the house. */
export function sideChatFits(width: number, state: ClientState | null): boolean {
  return state !== null && itemForStage(state.stage) === "house" && width >= Math.max(NARROW, SIDE_MIN_WIDTH);
}

export function useSideChat(state: ClientState | null): boolean {
  return sideChatFits(useViewport().width, state);
}

/** At the house, when the conversation does not fit beside the card, it opens in a drawer. */
export function useDrawerChat(state: ClientState | null): boolean {
  const side = useSideChat(state);
  return state !== null && itemForStage(state.stage) === "house" && !side;
}

/** Width of the conversation, and the room it takes on the right (with its margins). */
export function sideChatWidth(width: number): number {
  return Math.min(500, Math.max(400, width * 0.32));
}

/** Room the end card leaves on the right for the conversation (none when it is not beside). */
export function sideChatReserve(width: number, state: ClientState | null): number {
  return sideChatFits(width, state) ? sideChatWidth(width) + 2 * SIDE_MARGIN : 0;
}

/** Who is talking, and how far the profile is. */
function YanHeader({ state }: { state: ClientState }) {
  const { t, locale } = useI18n();
  const { completeness } = state;
  return (
    <div className={styles.chatHead}>
      <span className={styles.avatar} aria-hidden>
        Y
      </span>
      <div>
        <h2 id="yan-title">{t.journey.yan.title}</h2>
        <p>{t.journey.yan.role}</p>
      </div>
      <span className={cn(styles.pill, completeness.ready && styles.pillReady)}>
        {t.assistant.profilePill(formatPercent(completeness.displayed, locale))}
      </span>
    </div>
  );
}

/** Yan's follow-ups (A1), straight into the thread: Yan asks its first questions on its own. */
export function YanConversation({ state }: { state: ClientState }) {
  return (
    <>
      <YanHeader state={state} />
      <Assistant key={state.client_id} state={state} sample={false} intro={false} autoStart />
    </>
  );
}

/** The conversation docked on the right of the screen, beside the end card, when it fits. */
export function SideChat({ state, visible, width, floor }: { state: ClientState | null; visible: boolean; width: number; floor: number }) {
  if (!state || !sideChatFits(width, state)) return null;
  const style: CSSProperties = { right: SIDE_MARGIN, top: SIDE_TOP, width: sideChatWidth(width), height: floor - SIDE_TOP };
  return (
    <section className={cn(styles.panel, styles.chat, !visible && styles.hidden)} style={style} inert={!visible} aria-labelledby="yan-title">
      <YanConversation state={state} />
    </section>
  );
}

/** In the drawer (narrow windows), the same conversation fills the panel. */
export function DrawerChat({ state }: { state: ClientState }) {
  return (
    <div className={styles.chatDrawer}>
      <YanConversation state={state} />
    </div>
  );
}
