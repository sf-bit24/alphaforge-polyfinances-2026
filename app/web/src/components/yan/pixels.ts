/**
 * Yan in pixels, as the team's demo video draws it: a red block with two navy eyes, its
 * arms out at the sides, two feet, and a small gold spark for an antenna. One letter per
 * cell, read from a frame of the video: R the body, N an eye (on the body), Y the spark.
 */
const ART = [
  "........Y.......",
  ".......YY.......",
  "...RRRRRRRRRR...",
  "..RRRRRRRRRRRR..",
  "..RRRNRRRRNRRR..",
  "..RRRNRRRRNRRR..",
  "..RRRNRRRRNRRR..",
  "RRRRRRRRRRRRRRRR",
  "RRRRRRRRRRRRRRRR",
  "..RRRRRRRRRRRR..",
  "..RRRRRRRRRRRR..",
  "...RRRRRRRRRR...",
  "....RR....RR....",
];

export const YAN_COLS = 16;
export const YAN_ROWS = ART.length;

/** The drawing box of every Yan: the art centred in a square, with room to hover and for its shadow. */
export const YAN_VIEW = { x: 0, y: -1.5, size: 16 } as const;

export type PixelColor = "body" | "eye" | "spark";

export interface Pixel {
  x: number;
  y: number;
  color: PixelColor;
}

const COLOR_OF: Record<string, PixelColor | undefined> = { R: "body", N: "eye", Y: "spark" };

export const YAN_COLORS: Record<PixelColor, string> = { body: "#E41C23", eye: "#0B2341", spark: "#E2B03F" };

/** Every lit cell of the art, row by row. */
export const PIXELS: readonly Pixel[] = ART.flatMap((row, y) =>
  [...row].flatMap((cell, x) => {
    const color = COLOR_OF[cell];
    return color ? [{ x, y, color }] : [];
  }),
);

/** One SVG path of unit squares for the cells of `colors`, merged into runs along each row. */
export function pathOf(colors: readonly PixelColor[]): string {
  const lit = (x: number, y: number) => PIXELS.some((pixel) => pixel.x === x && pixel.y === y && colors.includes(pixel.color));
  const runs: string[] = [];
  for (let y = 0; y < YAN_ROWS; y += 1) {
    let start = -1;
    for (let x = 0; x <= YAN_COLS; x += 1) {
      const on = x < YAN_COLS && lit(x, y);
      if (on && start < 0) start = x;
      if (!on && start >= 0) {
        runs.push(`M${start} ${y}h${x - start}v1h${start - x}z`);
        start = -1;
      }
    }
  }
  return runs.join("");
}

/** The squint of joy, « ^ ^ », in half cells over each eye (as when the video ticks a line). */
export const HAPPY_EYES = [5.5, 10.5]
  .map((cx) => `M${cx - 0.25} 5h0.5v0.5h-0.5zM${cx - 0.75} 5.5h0.5v0.5h-0.5zM${cx + 0.25} 5.5h0.5v0.5h-0.5z`)
  .join("");
