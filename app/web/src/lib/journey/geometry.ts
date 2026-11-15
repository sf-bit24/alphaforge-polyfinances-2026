/**
 * Geometry of the journey scene, shared by the SVG (scene.tsx) and the cards placed
 * over it (journey.tsx). Pure, so it is tested without a browser.
 */
/** Design units of the draft: the world is drawn 900 high, then scaled to the window height. */
export const WORLD = { height: 900, ground: 650, gap: 520, manX: 330 } as const;
/** Scroll position at which the walker stands at stop `index` (-1 is the start). */
export const stopX = (index: number) => WORLD.gap * (index + 1);

/** Phones show the walk as a strip along the bottom of the screen, under the cards. */
export const NARROW = 760;
export const STRIP_SCALE = 0.42;
/** Screen px kept under the road on a phone, for the disclaimer. */
export const STRIP_FOOT = 64;

/**
 * Where the world is drawn on screen: `x + design * scale`. On wide screens the world
 * fills the window height (the draft); on a phone it is a small strip at the bottom.
 */
export interface SceneLayout {
  narrow: boolean;
  scale: number;
  x: number;
  y: number;
  /** Screen y of the ground line. */
  ground: number;
  /** Screen y of the top of the walker's head. */
  manTop: number;
}

export function sceneLayout(width: number, height: number): SceneLayout {
  if (width < NARROW) {
    const scale = STRIP_SCALE;
    const ground = height - STRIP_FOOT;
    return { narrow: true, scale, x: 64 - WORLD.manX * scale, y: ground - WORLD.ground * scale, ground, manTop: ground - 275 * scale };
  }
  const scale = height / WORLD.height;
  return { narrow: false, scale, x: 0, y: 0, ground: WORLD.ground * scale, manTop: (WORLD.ground - 275) * scale };
}

