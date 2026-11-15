"use client";

import { Activity, LayoutDashboard, UserRound } from "lucide-react";
import Link from "next/link";
import { useRef, useState, type CSSProperties, type ReactNode } from "react";
import type { AnswerValue, ClientState, Dimension } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import { useViewport } from "@/lib/client/use-viewport";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { formatPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { itemForStage, plant, resumeLayout, sayFor, START, type PathLayout, type SayKey } from "@/lib/journey/path";
import { Assistant } from "@/components/dashboard/assistant";
import { Brand } from "@/components/layout/brand";
import { LanguageToggle } from "@/components/layout/language-toggle";
import { PortfolioReviewStep } from "@/components/profile/portfolio-review-step";
import { ProfilePanel } from "@/components/profile/profile-panel";
import { TracePanel } from "@/components/trace/trace-panel";
import { cn } from "@/components/ui/cn";
import { Drawer } from "@/components/ui/drawer";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Spinner } from "@/components/ui/spinner";
import { EndCard } from "./end-card";
import { PortfolioCard } from "./portfolio-card";
import { QuestionCard } from "./question-card";
import { Scene, sceneLayout, WORLD, type SceneHandle } from "./scene";
import s from "./journey.module.css";

type Phase = "landing" | "walking" | "ready";
type DrawerKind = "trace" | "profile" | "chat";

/** Narrower windows keep Yan's conversation in a drawer: beside the card, both would be too cramped. */
const SIDE_CHAT_MIN_WIDTH = 1100;

function sayText(t: Dictionary, key: SayKey): string {
  switch (key.kind) {
    case "first":
      return t.journey.say.first;
    case "resume":
      return t.journey.say.resume;
    case "dimension":
      return t.journey.say.dimension[key.dimension];
    case "same":
      return t.journey.say.same[key.n % t.journey.say.same.length] ?? t.journey.say.first;
  }
}

function TopBar({ state, onOpen }: { state: ClientState | null; onOpen: (drawer: "trace" | "profile") => void }) {
  const { t } = useI18n();
  const atHouse = state ? itemForStage(state.stage) === "house" : false;
  return (
    <header className={s.topbar}>
      <Brand />
      <div className={s.topRight}>
        <span className={s.topNote}>{t.appNav.simulation}</span>
        {state ? (
          <>
            <button type="button" className={s.topLink} onClick={() => onOpen("trace")}>
              <Activity aria-hidden />
              <span className={s.topLabel}>{t.journey.trace}</span>
            </button>
            <button type="button" className={s.topLink} onClick={() => onOpen("profile")}>
              <UserRound aria-hidden />
              <span className={s.topLabel}>{t.journey.profile}</span>
            </button>
          </>
        ) : null}
        {atHouse ? (
          <Link href="/dashboard" className={cn(s.topLink, s.topWide)}>
            <LayoutDashboard aria-hidden />
            <span className={s.topLabel}>{t.appNav.dashboard}</span>
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
 * for an existing portfolio (A2), then the house: the questionnaire ends there and Yan
 * (A1) asks its personalized follow-ups, in a conversation on the right of the screen.
 */
export function Journey() {
  const session = useSession();
  // The flow starts from the stored session, so it mounts only once that session is back.
  if (!session.hydrated || (session.resuming && !session.state)) {
    return (
      <div className={s.root}>
        <TopBar state={null} onOpen={() => undefined} />
        <div className={s.boot}>
          <BootSpinner />
        </div>
      </div>
    );
  }
  return <JourneyFlow initial={session.state} />;
}

/** Who is talking in the conversation beside the house, and how far the profile is. */
function YanHeader({ state }: { state: ClientState }) {
  const { t, locale } = useI18n();
  const { completeness } = state;
  return (
    <div className={s.chatHead}>
      <span className={s.avatar} aria-hidden>
        Y
      </span>
      <div>
        <h2 id="yan-title">{t.journey.yan.title}</h2>
        <p>{t.journey.yan.role}</p>
      </div>
      <span className={cn(s.pill, completeness.ready && s.pillReady)}>{t.assistant.profilePill(formatPercent(completeness.displayed, locale))}</span>
    </div>
  );
}

function BootSpinner() {
  const { t } = useI18n();
  return <Spinner label={t.session.loading} />;
}

function JourneyFlow({ initial }: { initial: ClientState | null }) {
  const { t } = useI18n();
  const session = useSession();
  const { width, height } = useViewport();
  const scene = useRef<SceneHandle>(null);
  const resumable = initial !== null && itemForStage(initial.stage) !== "house";
  const [layout, setLayout] = useState<PathLayout>(() => (initial ? resumeLayout(initial) : START));
  const [initialStand] = useState(() => (initial ? resumeLayout(initial).stand : -1));
  const [phase, setPhase] = useState<Phase>(() => (initial && !resumable ? "ready" : "landing"));
  const [resumed, setResumed] = useState(resumable);
  const [greetBack, setGreetBack] = useState(false);
  const [previous, setPrevious] = useState<Dimension | null>(null);
  const [moving, setMoving] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [interacted, setInteracted] = useState(false);
  const [drawer, setDrawer] = useState<DrawerKind | null>(null);
  // The latest layout, for the async flows below (they outlive the render that started them).
  const current = useRef(layout);
  const apply = (next: PathLayout) => {
    current.current = next;
    setLayout(next);
  };

  const state = session.state;

  /** Fresh session: walk to the first stop while the runtime prepares the first question. */
  const startFresh = async (call: () => Promise<boolean>) => {
    setInteracted(true);
    setPhase("walking");
    const arrived = scene.current?.walkTo(0) ?? Promise.resolve();
    const ok = await call();
    const next = session.getState();
    if (!ok || !next) {
      scene.current?.jumpTo(-1);
      apply(START);
      setPhase("landing");
      return;
    }
    setPrevious(null);
    // The first sign already stands on the landing: it stays, without rising again.
    apply({ ...plant(START, 0, next.stage), planted: null });
    await arrived;
    setPhase("ready");
  };

  /** An answer moves the walker to the next stop; what stands there comes with the runtime's reply. */
  const advance = async (call: () => Promise<boolean>): Promise<boolean> => {
    setInteracted(true);
    const from = current.current.stand;
    const to = from + 1;
    setPhase("walking");
    let replied = false;
    const arrived = (scene.current?.walkTo(to) ?? Promise.resolve()).then(() => {
      if (!replied) setWaiting(true);
    });
    const ok = await call();
    replied = true;
    setWaiting(false);
    const next = session.getState();
    if (!ok || !next) {
      // The answer did not go through: back to the stop, the card shows the error.
      scene.current?.jumpTo(from);
      setPhase("ready");
      return false;
    }
    apply(plant(current.current, to, next.stage));
    await arrived;
    setWaiting(false);
    setPhase("ready");
    return true;
  };

  const resume = () => {
    setInteracted(true);
    setGreetBack(true);
    setPhase("ready");
  };

  const restart = () => {
    if (!window.confirm(t.journey.end.restartConfirm)) return;
    setDrawer(null);
    setResumed(false);
    setGreetBack(false);
    scene.current?.jumpTo(-1);
    apply(START);
    void startFresh(session.restart);
  };

  const answer = (dimension: Dimension, questionId: string, value: AnswerValue) => {
    setPrevious(dimension);
    setGreetBack(false);
    void advance(() => session.answerBase(questionId, value));
  };

  // Geometry of the draft: the card sits right of the walker, above the ground. On a
  // phone the walk is a strip along the bottom and the cards stand above it.
  const geo = sceneLayout(width, height);
  const { scale, narrow } = geo;
  const left = narrow ? 16 : Math.max((WORLD.manX + 150) * scale, width * 0.36);
  // Short windows (laptops) move the card up, so the answers and their button fit.
  const top = narrow ? 80 : Math.max(88, (WORLD.ground - 470) * scale - (900 - height) * 0.5);
  /** Lowest point a card may reach: above the walker's head on a phone, above the footer elsewhere. */
  const floor = narrow ? geo.manTop - 14 : height - 52;
  const visible = phase === "ready";
  const atHouse = state !== null && itemForStage(state.stage) === "house";
  const sideChat = atHouse && !narrow && width >= SIDE_CHAT_MIN_WIDTH;
  // Yan's conversation, docked right; the end card shares what is left of the walker's side.
  const chatWidth = Math.min(500, Math.max(400, width * 0.32));
  const chatTop = 84;
  const chatStyle: CSSProperties = { right: 24, top: chatTop, width: chatWidth, height: floor - chatTop };

  let content: ReactNode = null;
  let wide = false;
  let tall = false;
  let cardWidth = 560;
  if (state) {
    switch (state.stage) {
      case "base_questions": {
        const question = state.questions[0];
        if (question) {
          content = (
            <QuestionCard
              key={question.id}
              question={question}
              say={sayText(t, sayFor(question.dimension, previous, layout.stand, greetBack))}
              busy={!visible || session.pending === "base.answer"}
              autoFocus={visible && interacted}
              onAnswer={(value) => answer(question.dimension, question.id, value)}
            >
              {session.error && session.errorAction === "base.answer" ? (
                <ErrorNotice error={session.error} onRetry={() => void advance(session.retry)} onDismiss={session.dismissError} />
              ) : null}
            </QuestionCard>
          );
        }
        break;
      }
      case "existing_portfolio":
        cardWidth = 640;
        tall = true;
        content = (
          <PortfolioCard
            say={greetBack ? t.journey.say.resume : t.journey.say.portfolio}
            autoFocus={visible && interacted}
            onSkip={() => void advance(session.skipPortfolio)}
          />
        );
        break;
      case "portfolio_review":
        wide = true;
        content = state.portfolio ? (
          <>
            <div className={s.say}>
              <span className={s.avatar} aria-hidden>
                Y
              </span>
              <p>{t.journey.say.review}</p>
            </div>
            <PortfolioReviewStep
              key={state.portfolio.positions.map((position) => position.id).join("|")}
              portfolio={state.portfolio}
              message={state.message}
              onConfirm={(positions) => advance(() => session.confirmPortfolio(positions))}
            />
          </>
        ) : null;
        break;
      case "followups":
      case "complete":
        cardWidth = 480;
        content = (
          <EndCard
            state={state}
            side={sideChat}
            autoFocus={visible && interacted}
            busy={Boolean(session.pending)}
            onOpenChat={() => setDrawer("chat")}
            onRestart={restart}
          />
        );
        break;
    }
  }

  // Tall cards (portfolio, summary) start just under the progress bar so they fit without scrolling.
  const cardTop = tall && !narrow ? 88 : top;
  const panelStyle: CSSProperties = wide
    ? (() => {
        const panelWidth = Math.min(1240, width - 32);
        return { left: (width - panelWidth) / 2, top: narrow ? 80 : 84, width: panelWidth, maxHeight: floor - (narrow ? 80 : 84) };
      })()
    : {
        left,
        top: cardTop,
        width: narrow ? width - 32 : Math.min(cardWidth, (sideChat ? width - 24 - chatWidth - 24 : width - 40) - left),
        maxHeight: floor - cardTop,
      };
  // A new panel per stop, so each starts scrolled to its top.
  const panelKey = state ? `${state.stage}:${state.questions[0]?.id ?? ""}` : "none";
  const landingStyle: CSSProperties = narrow
    ? { left, top, width: width - 32, maxHeight: floor - top, overflowY: "auto" }
    : { left, top: Math.max(96, (WORLD.ground - 470) * scale), width: Math.min(560, width - left - 40) };
  // The first sign stands ahead of the walker on the landing, as in the draft.
  const signs = layout.stand === -1 && layout.signs[0] === undefined ? { ...layout.signs, 0: "question" as const } : layout.signs;
  const started = phase !== "landing" && state !== null;
  const startError =
    session.error && (session.errorAction === "session.start" || session.errorAction === "session.resume") ? session.error : null;

  return (
    <div className={s.root}>
      <TopBar state={state} onOpen={setDrawer} />
      <div
        className={cn(s.progress, started && s.progressOn)}
        role="progressbar"
        aria-label={t.journey.progress}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={state ? Math.round(state.completeness.displayed * 100) : 0}
      >
        <i style={{ width: `${(state?.completeness.displayed ?? 0) * 100}%` }} />
      </div>

      <Scene
        ref={scene}
        initialStand={initialStand}
        signs={signs}
        house={layout.house}
        planted={layout.planted}
        onMovingChange={setMoving}
      />

      <div
        aria-hidden
        className={cn(s.thought, waiting && s.thoughtOn)}
        style={{ left: geo.x + (WORLD.manX + 34) * scale, top: geo.manTop - (narrow ? 44 : 30 * scale) }}
      >
        …
      </div>
      {waiting ? <p className="sr-only" role="status">{t.journey.waiting}</p> : null}

      <section className={cn(s.panel, s.landing, phase !== "landing" && s.hidden)} style={landingStyle} inert={phase !== "landing"}>
        <h1>{resumed ? t.journey.landing.resumeTitle : t.journey.landing.title}</h1>
        <p>{resumed ? t.journey.landing.resumeLead : t.journey.landing.lead}</p>
        <div className={s.landingActions}>
          <button
            type="button"
            className={s.cta}
            onClick={resumed ? resume : () => void startFresh(session.start)}
            disabled={Boolean(session.pending)}
          >
            {resumed ? t.journey.landing.resume : t.journey.landing.start}
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
              <path d="M3 9h11M10 4.5L14.5 9 10 13.5" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          {resumed ? (
            <button type="button" className={s.ghost} onClick={restart} disabled={Boolean(session.pending)}>
              {t.journey.landing.restart}
            </button>
          ) : null}
        </div>
        <p className={s.meta}>{t.journey.landing.meta}</p>
        {session.notice === "not_found" ? <p className={s.meta}>{t.session.notFound}</p> : null}
        {startError ? (
          <div className={s.notice}>
            <ErrorNotice error={startError} onDismiss={session.dismissError} />
          </div>
        ) : null}
      </section>

      <section
        key={panelKey}
        className={cn(s.panel, wide ? s.wide : s.card, !visible && s.hidden)}
        style={panelStyle}
        inert={!visible}
        aria-live="polite"
      >
        {content}
      </section>

      {sideChat && state ? (
        <section
          className={cn(s.panel, s.chat, !visible && s.hidden)}
          style={chatStyle}
          inert={!visible}
          aria-labelledby="yan-title"
        >
          <YanHeader state={state} />
          <Assistant key={state.client_id} state={state} sample={false} intro={false} autoStart />
        </section>
      ) : null}

      <p className={s.disclaimer}>{t.journey.disclaimer}</p>
      <button
        type="button"
        className={cn(s.skip, moving && s.skipOn)}
        style={narrow ? { top: geo.manTop - 4 } : undefined}
        onClick={() => scene.current?.skip()}
      >
        {t.journey.skipWalk}
      </button>

      <Drawer open={drawer === "trace"} onClose={() => setDrawer(null)} label={t.trace.title}>
        <TracePanel />
      </Drawer>
      <Drawer open={drawer === "profile"} onClose={() => setDrawer(null)} label={t.panel.title}>
        {state ? <ProfilePanel state={state} /> : null}
      </Drawer>
      <Drawer open={drawer === "chat" && atHouse && !sideChat} onClose={() => setDrawer(null)} label={t.assistant.conversation}>
        {state ? (
          <div className={s.chatDrawer}>
            <YanHeader state={state} />
            <Assistant key={state.client_id} state={state} sample={false} intro={false} autoStart />
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
