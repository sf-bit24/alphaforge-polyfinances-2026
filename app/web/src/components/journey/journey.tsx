"use client";

import { Activity, LayoutDashboard, UserRound } from "lucide-react";
import Link from "next/link";
import { useRef, type CSSProperties, type ReactNode } from "react";
import type { ClientState, Stage } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import { useViewport } from "@/lib/client/use-viewport";
import type { SceneLayout } from "@/lib/journey/geometry";
import { useI18n } from "@/lib/i18n/provider";
import { itemForStage, type PathLayout, type StopKind } from "@/lib/journey/path";
import { Brand } from "@/components/layout/brand";
import { LanguageToggle } from "@/components/layout/language-toggle";
import { ProfilePanel } from "@/components/profile/profile-panel";
import { TracePanel } from "@/components/trace/trace-panel";
import { cn } from "@/components/ui/cn";
import { Drawer } from "@/components/ui/drawer";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Spinner } from "@/components/ui/spinner";
import { Scene, sceneLayout, WORLD, type SceneHandle } from "./scene";
import { StageCard } from "./stage-card";
import { useJourneyFlow, type DrawerName } from "./use-journey-flow";
import styles from "./journey.module.css";

function TopBar({ state, onOpen }: { state: ClientState | null; onOpen: (drawer: DrawerName) => void }) {
  const { t } = useI18n();
  const atHouse = state ? itemForStage(state.stage) === "house" : false;
  return (
    <header className={styles.topbar}>
      <Brand />
      <div className={styles.topRight}>
        <span className={styles.topNote}>{t.appNav.simulation}</span>
        {state ? (
          <>
            <button type="button" className={styles.topLink} onClick={() => onOpen("trace")}>
              <Activity aria-hidden />
              <span className={styles.topLabel}>{t.journey.trace}</span>
            </button>
            <button type="button" className={styles.topLink} onClick={() => onOpen("profile")}>
              <UserRound aria-hidden />
              <span className={styles.topLabel}>{t.journey.profile}</span>
            </button>
          </>
        ) : null}
        {atHouse ? (
          <Link href="/dashboard" className={cn(styles.topLink, styles.topWide)}>
            <LayoutDashboard aria-hidden />
            <span className={styles.topLabel}>{t.appNav.dashboard}</span>
          </Link>
        ) : null}
        <LanguageToggle />
      </div>
    </header>
  );
}

/**
 * The profile journey of the approved draft, driven by the real contract: one stop per
 * base question (the runtime decides the next one, branches included), a briefcase stop
 * for an existing portfolio (A2), then the house with the profile's first version.
 */
export function Journey() {
  const session = useSession();
  // The flow starts from the stored session, so it mounts only once that session is back.
  if (!session.hydrated || (session.resuming && !session.state)) {
    return (
      <div className={styles.root}>
        <TopBar state={null} onOpen={() => undefined} />
        <div className={styles.boot}>
          <BootSpinner />
        </div>
      </div>
    );
  }
  return <JourneyFlow initial={session.state} />;
}

function BootSpinner() {
  const { t } = useI18n();
  return <Spinner label={t.session.loading} />;
}

/**
 * Geometry of the draft: the card sits right of the walker, above the ground. On a
 * phone the walk is a strip along the bottom and the cards stand above it.
 */
function cardFrame(width: number, height: number) {
  const geo = sceneLayout(width, height);
  const { scale, narrow } = geo;
  const left = narrow ? 16 : Math.max((WORLD.manX + 150) * scale, width * 0.36);
  // Short windows (laptops) move the card up, so the answers and their button fit.
  const top = narrow ? 80 : Math.max(88, (WORLD.ground - 470) * scale - (900 - height) * 0.5);
  /** Lowest point a card may reach: above the walker's head on a phone, above the footer elsewhere. */
  const floor = narrow ? geo.manTop - 14 : height - 52;
  return { geo, width, left, top, floor };
}

type CardFrame = ReturnType<typeof cardFrame>;

/** How a stage's card sits beside the walker: `wide` spans the screen, `tall` starts higher. */
interface CardShape {
  wide: boolean;
  tall: boolean;
  width: number;
}

const PLAIN_CARD: CardShape = { wide: false, tall: false, width: 560 };

const CARD_SHAPES: Record<Stage, CardShape> = {
  base_questions: PLAIN_CARD,
  existing_portfolio: { wide: false, tall: true, width: 640 },
  portfolio_review: { wide: true, tall: false, width: 560 },
  followups: { wide: false, tall: true, width: 560 },
  complete: { wide: false, tall: true, width: 560 },
};

function panelStyle({ geo, width, left, top, floor }: CardFrame, shape: CardShape): CSSProperties {
  const { narrow } = geo;
  if (shape.wide) {
    const panelWidth = Math.min(1240, width - 32);
    return { left: (width - panelWidth) / 2, top: narrow ? 80 : 84, width: panelWidth, maxHeight: floor - (narrow ? 80 : 84) };
  }
  // Tall cards (portfolio, summary) start just under the progress bar so they fit without scrolling.
  const cardTop = shape.tall && !narrow ? 88 : top;
  return { left, top: cardTop, width: narrow ? width - 32 : Math.min(shape.width, width - left - 40), maxHeight: floor - cardTop };
}

function landingStyle({ geo, width, left, top, floor }: CardFrame): CSSProperties {
  return geo.narrow
    ? { left, top, width: width - 32, maxHeight: floor - top, overflowY: "auto" }
    : { left, top: Math.max(96, (WORLD.ground - 470) * geo.scale), width: Math.min(560, width - left - 40) };
}

/** The first sign stands ahead of the walker on the landing, as in the draft. */
function signsAhead(layout: PathLayout): Record<number, StopKind> {
  return layout.stand === -1 && layout.signs[0] === undefined ? { ...layout.signs, 0: "question" as const } : layout.signs;
}

function ProgressBar({ state, started }: { state: ClientState | null; started: boolean }) {
  const { t } = useI18n();
  return (
    <div
      className={cn(styles.progress, started && styles.progressOn)}
      role="progressbar"
      aria-label={t.journey.progress}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={state ? Math.round(state.completeness.displayed * 100) : 0}
    >
      <i style={{ width: `${(state?.completeness.displayed ?? 0) * 100}%` }} />
    </div>
  );
}

/** The walker's thought bubble while he waits at a stop for the runtime's reply. */
function ThoughtBubble({ geo, waiting }: { geo: SceneLayout; waiting: boolean }) {
  const { t } = useI18n();
  return (
    <>
      <div
        aria-hidden
        className={cn(styles.thought, waiting && styles.thoughtOn)}
        style={{ left: geo.x + (WORLD.manX + 34) * geo.scale, top: geo.manTop - (geo.narrow ? 44 : 30 * geo.scale) }}
      >
        …
      </div>
      {waiting ? <p className="sr-only" role="status">{t.journey.waiting}</p> : null}
    </>
  );
}

interface LandingProps {
  shown: boolean;
  resumed: boolean;
  style: CSSProperties;
  onStart: () => void;
  onResume: () => void;
  onRestart: () => void;
}

function LandingPanel({ shown, resumed, style, onStart, onResume, onRestart }: LandingProps) {
  const { t } = useI18n();
  const session = useSession();
  const startError =
    session.error && (session.errorAction === "session.start" || session.errorAction === "session.resume") ? session.error : null;
  return (
    <section className={cn(styles.panel, styles.landing, !shown && styles.hidden)} style={style} inert={!shown}>
      <h1>{resumed ? t.journey.landing.resumeTitle : t.journey.landing.title}</h1>
      <p>{resumed ? t.journey.landing.resumeLead : t.journey.landing.lead}</p>
      <div className={styles.landingActions}>
        <button type="button" className={styles.cta} onClick={resumed ? onResume : onStart} disabled={Boolean(session.pending)}>
          {resumed ? t.journey.landing.resume : t.journey.landing.start}
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
            <path d="M3 9h11M10 4.5L14.5 9 10 13.5" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {resumed ? (
          <button type="button" className={styles.ghost} onClick={onRestart} disabled={Boolean(session.pending)}>
            {t.journey.landing.restart}
          </button>
        ) : null}
      </div>
      <p className={styles.meta}>{t.journey.landing.meta}</p>
      {session.notice === "not_found" ? <p className={styles.meta}>{t.session.notFound}</p> : null}
      {startError ? (
        <div className={styles.notice}>
          <ErrorNotice error={startError} onDismiss={session.dismissError} />
        </div>
      ) : null}
    </section>
  );
}

function CardPanel({ shape, visible, style, children }: { shape: CardShape; visible: boolean; style: CSSProperties; children: ReactNode }) {
  return (
    <section
      className={cn(styles.panel, shape.wide ? styles.wide : styles.card, !visible && styles.hidden)}
      style={style}
      inert={!visible}
      aria-live="polite"
    >
      {children}
    </section>
  );
}

function SkipWalkButton({ geo, moving, onSkip }: { geo: SceneLayout; moving: boolean; onSkip: () => void }) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      className={cn(styles.skip, moving && styles.skipOn)}
      style={geo.narrow ? { top: geo.manTop - 4 } : undefined}
      onClick={onSkip}
    >
      {t.journey.skipWalk}
    </button>
  );
}

function JourneyDrawers({ drawer, state, onClose }: { drawer: DrawerName | null; state: ClientState | null; onClose: () => void }) {
  const { t } = useI18n();
  return (
    <>
      <Drawer open={drawer === "trace"} onClose={onClose} label={t.trace.title}>
        <TracePanel />
      </Drawer>
      <Drawer open={drawer === "profile"} onClose={onClose} label={t.panel.title}>
        {state ? <ProfilePanel state={state} /> : null}
      </Drawer>
    </>
  );
}

function JourneyFlow({ initial }: { initial: ClientState | null }) {
  const { t } = useI18n();
  const session = useSession();
  const { width, height } = useViewport();
  const scene = useRef<SceneHandle>(null);
  const flow = useJourneyFlow(initial, scene, session, t);
  const state = session.state;
  const frame = cardFrame(width, height);
  const shape = state ? CARD_SHAPES[state.stage] : PLAIN_CARD;
  const visible = flow.phase === "ready";
  // A new panel per stop, so each starts scrolled to its top.
  const panelKey = state ? `${state.stage}:${state.questions[0]?.id ?? ""}` : "none";

  return (
    <div className={styles.root}>
      <TopBar state={state} onOpen={flow.setDrawer} />
      <ProgressBar state={state} started={flow.phase !== "landing" && state !== null} />
      <Scene
        ref={scene}
        initialStand={flow.initialStand}
        signs={signsAhead(flow.layout)}
        house={flow.layout.house}
        planted={flow.layout.planted}
        onMovingChange={flow.setMoving}
      />
      <ThoughtBubble geo={frame.geo} waiting={flow.waiting} />
      <LandingPanel
        shown={flow.phase === "landing"}
        resumed={flow.resumed}
        style={landingStyle(frame)}
        onStart={() => void flow.startFresh(session.start)}
        onResume={flow.resume}
        onRestart={flow.restart}
      />
      <CardPanel key={panelKey} shape={shape} visible={visible} style={panelStyle(frame, shape)}>
        {state ? <StageCard state={state} flow={flow} visible={visible} /> : null}
      </CardPanel>
      <p className={styles.disclaimer}>{t.journey.disclaimer}</p>
      <SkipWalkButton geo={frame.geo} moving={flow.moving} onSkip={() => scene.current?.skip()} />
      <JourneyDrawers drawer={flow.drawer} state={state} onClose={() => flow.setDrawer(null)} />
    </div>
  );
}
