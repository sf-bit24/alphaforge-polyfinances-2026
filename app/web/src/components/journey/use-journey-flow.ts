"use client";

import { useRef, useState, type RefObject } from "react";
import type { AnswerValue, ClientState, Dimension } from "@/lib/contract/schemas";
import type { SessionValue } from "@/lib/client/session";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { itemForStage, plant, resumeLayout, START, type PathLayout } from "@/lib/journey/path";
import { sampleAnswer } from "@/lib/journey/sample-profile";
import type { SceneHandle } from "./scene";

type Phase = "landing" | "walking" | "ready";
export type DrawerName = "trace" | "profile";

/** Where the walker stands and what the screen shows. */
function useJourneyState(initial: ClientState | null) {
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
  const [drawer, setDrawer] = useState<DrawerName | null>(null);
  /** Answers saved so far by « Passer les questions », or null when it is not running. */
  const [skipping, setSkipping] = useState<number | null>(null);
  // The latest layout, for the async flows below (they outlive the render that started them).
  const latestLayout = useRef(layout);
  const apply = (next: PathLayout) => {
    latestLayout.current = next;
    setLayout(next);
  };
  return {
    layout,
    latestLayout,
    apply,
    initialStand,
    phase,
    setPhase,
    resumed,
    setResumed,
    greetBack,
    setGreetBack,
    previous,
    setPrevious,
    moving,
    setMoving,
    waiting,
    setWaiting,
    interacted,
    setInteracted,
    drawer,
    setDrawer,
    skipping,
    setSkipping,
  };
}

type JourneyState = ReturnType<typeof useJourneyState>;

/** What the walking flows read and change. */
type Walk = Pick<JourneyState, "latestLayout" | "apply" | "setPhase" | "setPrevious" | "setWaiting" | "setInteracted"> & {
  session: SessionValue;
  scene: RefObject<SceneHandle | null>;
};

/** Fresh session: walk to the first stop while the runtime prepares the first question. */
async function startFresh(walk: Walk, call: () => Promise<boolean>): Promise<void> {
  const { session, scene, apply, setPhase, setPrevious, setInteracted } = walk;
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
}

/** An answer moves the walker to the next stop; what stands there comes with the runtime's reply. */
async function advance(walk: Walk, call: () => Promise<boolean>): Promise<boolean> {
  const { session, scene, latestLayout, apply, setPhase, setWaiting, setInteracted } = walk;
  setInteracted(true);
  const from = latestLayout.current.stand;
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
  apply(plant(latestLayout.current, to, next.stage));
  await arrived;
  setWaiting(false);
  setPhase("ready");
  return true;
}

/**
 * « Passer les questions » (tests, demos): the sample profile answers every base question
 * through the runtime, then the walker stands at the house with the profile's first version.
 * If an answer fails, the journey stops at that question and its card shows the error.
 */
async function skipQuestions(walk: Walk, setSkipping: (count: number | null) => void): Promise<void> {
  const { session, scene, apply, setPhase, setPrevious, setInteracted } = walk;
  setInteracted(true);
  setSkipping(0);
  setPhase("ready");
  if (!session.getState() && !(await session.start())) {
    setSkipping(null);
    setPhase("landing");
    return;
  }
  await session.answerAllBase(sampleAnswer, setSkipping);
  const next = session.getState();
  setSkipping(null);
  setPrevious(null);
  if (!next) {
    setPhase("landing");
    return;
  }
  const at = resumeLayout(next);
  apply(at);
  scene.current?.jumpTo(at.stand);
}

/** The journey's state and the investor's moves; each move interleaves the walk with the runtime's reply. */
export function useJourneyFlow(initial: ClientState | null, scene: RefObject<SceneHandle | null>, session: SessionValue, t: Dictionary) {
  const { latestLayout, apply, setPhase, setResumed, setGreetBack, setPrevious, setWaiting, setInteracted, setSkipping, ...view } =
    useJourneyState(initial);
  const { setDrawer } = view;
  const walk: Walk = { session, scene, latestLayout, apply, setPhase, setPrevious, setWaiting, setInteracted };

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
    void startFresh(walk, session.restart);
  };

  const answer = (dimension: Dimension, questionId: string, value: AnswerValue) => {
    setPrevious(dimension);
    setGreetBack(false);
    void advance(walk, () => session.answerBase(questionId, value));
  };

  const skip = () => {
    setGreetBack(false);
    setResumed(false);
    setDrawer(null);
    void skipQuestions(walk, setSkipping);
  };

  return {
    ...view,
    skipQuestions: skip,
    startFresh: (call: () => Promise<boolean>) => startFresh(walk, call),
    advance: (call: () => Promise<boolean>) => advance(walk, call),
    resume,
    restart,
    answer,
  };
}

export type Flow = ReturnType<typeof useJourneyFlow>;
