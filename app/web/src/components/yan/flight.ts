/**
 * Yan's pixels in flight, as in the team's demo video: the brand's red square bursts into
 * pixels that stream across the page and assemble into Yan. Each pixel is a square on a
 * fixed layer over the page, so no card that scrolls or clips can cut the flight short;
 * the layer goes as soon as the pixels have landed and the real drawing shows.
 */
import { PIXELS, YAN_COLORS, type Pixel } from "./pixels";

/** Where the pixels come from: the brand's red square, or the spot where Yan was last seen. */
export type YanSource = "home" | "last";

export interface Flight {
  /** True once every pixel has landed; false when the flight was cancelled. */
  done: Promise<boolean>;
  cancel: () => void;
}

interface Grid {
  left: number;
  top: number;
  unit: number;
}

interface Course {
  from: [number, number];
  via: [number, number];
  delay: number;
  duration: number;
}

let lastSeen: DOMRect | null = null;

/** Notes where a Yan stood as its place hides or goes away: the next Yan flies in from there. */
export function rememberYan(node: Element | null): void {
  if (!node?.isConnected) return;
  const box = node.getBoundingClientRect();
  if (box.width > 0 && box.height > 0) lastSeen = box;
}

function sourceOf(from: YanSource): { box: DOMRect; home: Element | null } | null {
  const home = from === "home" ? document.querySelector("[data-yan-home]") : null;
  const box = home?.getBoundingClientRect();
  if (home && box && box.width > 0) return { box, home };
  return lastSeen ? { box: lastSeen, home: null } : null;
}

/** Screen position of the drawing's cells, from the SVG's box and view box (centred, as SVG draws it). */
function gridOf(svg: SVGSVGElement): Grid {
  const box = svg.getBoundingClientRect();
  const view = svg.viewBox.baseVal;
  const unit = Math.min(box.width / view.width, box.height / view.height);
  return {
    unit,
    left: box.left + (box.width - view.width * unit) / 2 - view.x * unit,
    top: box.top + (box.height - view.height * unit) / 2 - view.y * unit,
  };
}

function far(source: DOMRect, svg: SVGSVGElement): boolean {
  const box = svg.getBoundingClientRect();
  const dx = source.left + source.width / 2 - (box.left + box.width / 2);
  const dy = source.top + source.height / 2 - (box.top + box.height / 2);
  return Math.hypot(dx, dy) > Math.max(3 * box.width, 120);
}

/** From a far source, a stream along a gentle arc; each pixel leaves from a point of the source. */
function streamCourse(x: number, y: number, source: DOMRect, bend: number): Course {
  const dx = source.left + Math.random() * source.width - x;
  const dy = source.top + Math.random() * source.height - y;
  const curve = bend * (0.8 + Math.random() * 0.4);
  return {
    from: [dx, dy],
    via: [dx * 0.42 - dy * curve, dy * 0.42 + dx * curve],
    delay: Math.random() * 320,
    duration: 760 + Math.random() * 260,
  };
}

/** Without a far source, the pixels gather from a small cloud around the spot. */
function burstCourse(unit: number): Course {
  const angle = Math.random() * Math.PI * 2;
  const radius = unit * (3 + Math.random() * 4);
  const from: [number, number] = [Math.cos(angle) * radius, Math.sin(angle) * radius - unit * 2];
  return {
    from,
    via: [from[0] * 0.3, from[1] * 0.3 - unit],
    delay: Math.random() * 180,
    duration: 440 + Math.random() * 160,
  };
}

function launch(layer: HTMLElement, pixel: Pixel, grid: Grid, course: (x: number, y: number) => Course): Animation {
  const x = grid.left + pixel.x * grid.unit;
  const y = grid.top + pixel.y * grid.unit;
  const dot = document.createElement("i");
  Object.assign(dot.style, {
    position: "absolute",
    left: `${x}px`,
    top: `${y}px`,
    width: `${grid.unit + 0.5}px`,
    height: `${grid.unit + 0.5}px`,
    background: YAN_COLORS[pixel.color],
  });
  layer.append(dot);
  const { from, via, delay, duration } = course(x, y);
  return dot.animate(
    [
      { transform: `translate(${from[0]}px, ${from[1]}px) scale(0.5)`, opacity: 0 },
      { transform: `translate(${from[0] * 0.94}px, ${from[1] * 0.94}px) scale(0.7)`, opacity: 1, offset: 0.12 },
      { transform: `translate(${via[0]}px, ${via[1]}px) scale(0.9)`, opacity: 1, offset: 0.62 },
      { transform: "none", opacity: 1 },
    ],
    { duration, delay, easing: "cubic-bezier(0.3, 0.75, 0.3, 1)", fill: "both" },
  );
}

/** The brand's square gives its pixels: it shrinks, then springs back. */
function squeeze(home: Element): void {
  home.animate(
    [{ transform: "scale(1)" }, { transform: "scale(0.55)", offset: 0.3 }, { transform: "scale(1.12)", offset: 0.8 }, { transform: "scale(1)" }],
    { duration: 900, easing: "ease-in-out" },
  );
}

function makeLayer(): HTMLElement {
  const layer = document.createElement("div");
  layer.setAttribute("aria-hidden", "true");
  Object.assign(layer.style, { position: "fixed", inset: "0", zIndex: "60", pointerEvents: "none", overflow: "hidden" });
  document.body.append(layer);
  return layer;
}

/** Flies Yan's pixels to `svg`, from `from` when it is far enough, else from a cloud around it. */
export function flyIn(svg: SVGSVGElement, from: YanSource): Flight {
  const grid = gridOf(svg);
  if (grid.unit <= 0 || typeof svg.animate !== "function") return { done: Promise.resolve(true), cancel: () => undefined };
  const source = sourceOf(from);
  const stream = source && far(source.box, svg) ? source : null;
  const bend = (Math.random() < 0.5 ? -1 : 1) * 0.16;
  const course = (x: number, y: number) => (stream ? streamCourse(x, y, stream.box, bend) : burstCourse(grid.unit));
  const layer = makeLayer();
  const flights = PIXELS.map((pixel) => launch(layer, pixel, grid, course));
  if (stream?.home) squeeze(stream.home);
  const done = Promise.all(flights.map((flight) => flight.finished)).then(
    () => true,
    () => false,
  );
  void done.finally(() => layer.remove());
  return {
    done,
    cancel: () => {
      flights.forEach((flight) => flight.cancel());
      layer.remove();
    },
  };
}

/** Calls `ready` once `node` has stopped moving (its card slides in), or after `maxMs`; returns the cancel. */
export function whenSettled(node: Element, ready: () => void, maxMs = 900): () => void {
  const start = performance.now();
  let frame = 0;
  let last = "";
  let still = 0;
  const tick = () => {
    const box = node.getBoundingClientRect();
    const key = `${Math.round(box.left)}:${Math.round(box.top)}:${Math.round(box.width)}`;
    still = key === last ? still + 1 : 0;
    last = key;
    if (still >= 3 || performance.now() - start > maxMs) ready();
    else frame = requestAnimationFrame(tick);
  };
  frame = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(frame);
}
