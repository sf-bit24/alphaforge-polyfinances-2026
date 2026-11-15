/**
 * The profile journey as a path: one stop per base question, a briefcase stop when
 * the investor shares an existing portfolio, then the house. Pure functions, so the
 * walker's position can be rebuilt from a stored session (resume) and tested.
 */
import type { ClientState, Dimension, Stage } from "@/lib/contract/schemas";

export type StopKind = "question" | "portfolio";
export type PathItem = StopKind | "house";

export interface PathLayout {
  /** Stop where the walker stands. -1 is the start of the path, before the first stop. */
  stand: number;
  /** What is planted at each stop. */
  signs: Record<number, StopKind>;
  /** Stop of the house, once the base questions and the portfolio are behind. */
  house: number | null;
  /** Stop planted by the last answer, which rises from the ground; null after a resume. */
  planted: number | null;
}

export const START: PathLayout = { stand: -1, signs: {}, house: null, planted: null };

/** What waits at the current stop for a stage. */
export function itemForStage(stage: Stage): PathItem {
  switch (stage) {
    case "base_questions":
      return "question";
    case "existing_portfolio":
    case "portfolio_review":
      return "portfolio";
    case "followups":
    case "complete":
      return "house";
  }
}

/** Base questions answered so far: one `base:<question_id>` provenance per answer (CONTRACTS.md, facts). */
export function answeredBaseCount(state: Pick<ClientState, "profile">): number {
  return new Set(state.profile.facts.map((fact) => fact.provenance).filter((provenance) => provenance.startsWith("base:"))).size;
}

/** Plant the item of `stage` at `index`, where the walker now goes. */
export function plant(layout: PathLayout, index: number, stage: Stage): PathLayout {
  const item = itemForStage(stage);
  if (item === "house") return { ...layout, stand: index, house: index, planted: index };
  return { ...layout, stand: index, signs: { ...layout.signs, [index]: item }, house: null, planted: index };
}

/** Where the walker stands, and what is planted behind him, when a stored session resumes. */
export function resumeLayout(state: Pick<ClientState, "profile" | "stage" | "portfolio">): PathLayout {
  const answered = answeredBaseCount(state);
  const signs: Record<number, StopKind> = {};
  for (let index = 0; index < answered; index += 1) signs[index] = "question";
  const item = itemForStage(state.stage);
  if (item !== "house") {
    signs[answered] = item;
    return { stand: answered, signs, house: null, planted: null };
  }
  const hadPortfolio = state.portfolio !== null;
  if (hadPortfolio) signs[answered] = "portfolio";
  const house = answered + (hadPortfolio ? 1 : 0);
  return { stand: house, signs, house, planted: null };
}

/** Which line the assistant says above a base question. */
export type SayKey =
  | { kind: "first" }
  | { kind: "resume" }
  | { kind: "dimension"; dimension: Dimension }
  | { kind: "same"; n: number };

export function sayFor(current: Dimension, previous: Dimension | null, index: number, resumed: boolean): SayKey {
  if (resumed) return { kind: "resume" };
  if (previous === null) return index <= 0 ? { kind: "first" } : { kind: "dimension", dimension: current };
  return previous === current ? { kind: "same", n: index } : { kind: "dimension", dimension: current };
}

/** Keys 1 to 9 pick an option; more options than that are reachable with Tab only. */
export function shortcutIndex(key: string, optionCount: number): number | null {
  if (!/^[1-9]$/.test(key)) return null;
  const index = Number(key) - 1;
  return index < optionCount ? index : null;
}
