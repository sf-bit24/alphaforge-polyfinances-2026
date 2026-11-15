"use client";

import { createContext, useContext, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { cn } from "@/components/ui/cn";
import { flyIn, rememberYan, whenSettled, type Flight, type YanSource } from "./flight";
import { HAPPY_EYES, pathOf, YAN_COLORS, YAN_VIEW } from "./pixels";
import styles from "./yan.module.css";

/**
 * Yan, the personal assistant: the little red pixel robot of the team's demo video. It
 * hovers, blinks and its gold spark twinkles; with `arrive`, it stays away until its place
 * is shown, then its pixels fly in (from the brand's square or from where Yan was last
 * seen), it lands with a squash and, with `cheer`, squints with joy.
 */
export type YanMood = "idle" | "happy" | "think";

/** Whether the place Yan stands is on screen: a card hidden while the walker walks is not. */
export const YanShown = createContext(true);

const BODY = pathOf(["body", "eye"]);
const EYES = pathOf(["eye"]);
const SPARK = pathOf(["spark"]);
const VIEW_BOX = `${YAN_VIEW.x} ${YAN_VIEW.y} ${YAN_VIEW.size} ${YAN_VIEW.size}`;

type Phase = "away" | "landed" | "here";

/** `away` until the pixels have flown in once the place is shown; then where Yan was is noted when it hides. */
function useArrival(ref: RefObject<SVGSVGElement | null>, arrive: YanSource | undefined): Phase {
  const shown = useContext(YanShown);
  const [phase, setPhase] = useState<Phase>(arrive ? "away" : "here");
  useEffect(() => {
    const svg = ref.current;
    if (phase !== "away" || !shown || !svg || !arrive) return undefined;
    let flight: Flight | null = null;
    const stopWaiting = whenSettled(svg, () => {
      flight = flyIn(svg, arrive);
      void flight.done.then((landed) => {
        if (landed) setPhase("landed");
      });
    });
    return () => {
      stopWaiting();
      flight?.cancel();
    };
  }, [ref, arrive, phase, shown]);
  // A layout effect: on unmount it runs while the drawing is still on the page.
  useLayoutEffect(() => {
    const svg = ref.current;
    if (!shown || phase === "away") return undefined;
    return () => rememberYan(svg);
  }, [ref, shown, phase]);
  return phase;
}

interface SpriteProps {
  size: number;
  className?: string;
  mood?: YanMood;
  arrive?: YanSource;
  cheer?: boolean;
  shadow?: boolean;
}

function YanSprite({ size, className, mood = "idle", arrive, cheer = false, shadow = false }: SpriteProps) {
  const ref = useRef<SVGSVGElement>(null);
  const phase = useArrival(ref, arrive);
  return (
    <svg
      ref={ref}
      className={cn(styles.yan, className)}
      width={size}
      height={size}
      viewBox={VIEW_BOX}
      shapeRendering="crispEdges"
      data-phase={phase}
      data-mood={mood === "idle" ? undefined : mood}
      data-cheer={cheer || undefined}
      aria-hidden
      focusable="false"
    >
      {shadow ? <ellipse className={styles.shadow} cx={8} cy={13.9} rx={5.4} ry={0.5} shapeRendering="geometricPrecision" /> : null}
      <g className={styles.hover}>
        <g className={styles.body}>
          <path d={BODY} fill={YAN_COLORS.body} />
          <path className={styles.spark} d={SPARK} fill={YAN_COLORS.spark} />
          <path className={styles.eyes} d={EYES} fill={YAN_COLORS.eye} />
          <path className={styles.happy} d={HAPPY_EYES} fill={YAN_COLORS.eye} />
        </g>
      </g>
    </svg>
  );
}

interface MarkProps {
  size?: number;
  className?: string;
  mood?: YanMood;
  arrive?: YanSource;
}

/** Yan as the avatar of its lines and messages. Decorative: its name is always written beside it. */
export function YanMark({ size = 32, ...rest }: MarkProps) {
  return <YanSprite size={size} {...rest} />;
}

interface FigureProps extends Omit<MarkProps, "size"> {
  /** Kept from the first Yan: the figure is square, so it is also its width. */
  height?: number;
  cheer?: boolean;
}

/** Yan in full, hovering over its shadow: on the landing, and where the profile is complete. */
export function YanFigure({ height = 112, ...rest }: FigureProps) {
  return <YanSprite size={height} shadow {...rest} />;
}
