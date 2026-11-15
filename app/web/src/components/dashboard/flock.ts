/**
 * The flock of the dashboard draft, drawn on a canvas over the landscape. Birds keep to
 * their flock and avoid the edges, flee the pointer, scatter when the sky is clicked,
 * gather around the caret while the investor types, and all dive into the box on send.
 * It plays whatever the reduced-motion setting: it is part of the approved design.
 */

interface Bird {
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** Phase of the wing beat. */
  phase: number;
  size: number;
  /** How hard the bird darts away (0 to 1), after the pointer or a gust; it fades. */
  dart: number;
  /** How far the bird has vanished into the input box (0 to 1). */
  gone: number;
  isRed: boolean;
}

export interface FlockElements {
  scene: HTMLElement;
  canvas: HTMLCanvasElement;
  input: HTMLInputElement;
  form: HTMLElement;
  /** The man's group, mirrored to face the pointer. */
  flip: SVGGElement;
  /** The "…" bubble over the man's head while typing. */
  thought: HTMLElement;
}

export interface Flock {
  /** The input changed: birds gather around the caret, the man turns to the box. */
  typed(): void;
  /** Sending: every bird dives into the input box. */
  gulp(): void;
  stop(): void;
}

const MAN_X = 118;
const BIRD_COUNT = 16;
/** How long the birds stay around the caret after a keystroke. */
const TYPING_MS = 1800;
/** How long the dive into the input box lasts. */
const GULP_MS = 1500;
/** Life of the ring a click leaves in the sky (its gust pushes for the first half second). */
const GUST_MS = 900;
/** Birds closer than this push each other apart (px). */
const SEPARATION_PX = 26;
/** Birds within this distance fly together (px). */
const NEIGHBOUR_PX = 90;
const FLEE_PX = 110;
const GUST_PX = 180;

interface Sky {
  width: number;
  height: number;
  pixelRatio: number;
}

interface Pointer {
  x: number;
  y: number;
  isInside: boolean;
}

/** A point of the scene and the time it was set (ms). */
interface Mark {
  x: number;
  y: number;
  at: number;
}

/** What the birds react to, shared by the listeners, the frames and the commands. */
interface World {
  sky: Sky;
  birds: Bird[];
  pointer: Pointer;
  /** The caret at the last keystroke. */
  caret: Mark;
  /** Centre of the input box when the message was sent. */
  gulpAt: Mark;
  /** Clicks in the sky. */
  gusts: Mark[];
}

/** The world at one animation frame. */
interface Frame extends World {
  now: number;
  /** Time since the previous frame, in 60 fps frames (at most 3): every per-frame rate is scaled by it. */
  steps: number;
  seconds: number;
  typing: boolean;
  gulping: boolean;
}

/** Acceleration of one bird, summed rule by rule in a fixed order. */
interface Steering {
  ax: number;
  ay: number;
}

/** The canvas matches the scene, at the screen's pixel density (2 at most). */
function fitCanvas(sky: Sky, scene: HTMLElement, canvas: HTMLCanvasElement): void {
  sky.pixelRatio = Math.min(2, window.devicePixelRatio || 1);
  sky.width = scene.clientWidth;
  sky.height = scene.clientHeight;
  canvas.width = sky.width * sky.pixelRatio;
  canvas.height = sky.height * sky.pixelRatio;
}

/** The flock at the start, spread over the sky, flying left or right; the first bird is the red one. */
function hatchBirds(width: number): Bird[] {
  return Array.from({ length: BIRD_COUNT }, (_, index) => ({
    x: Math.min(width - 40, 260 + Math.random() * 520),
    y: 40 + Math.random() * 150,
    vx: (Math.random() < 0.5 ? -1 : 1) * (0.8 + Math.random() * 0.5),
    vy: (Math.random() - 0.5) * 0.4,
    phase: Math.random() * 6.28,
    size: 0.8 + Math.random() * 0.45,
    dart: 0,
    gone: 0,
    isRed: index === 0,
  }));
}

/**
 * The man faces the pointer (unless the investor is in the input), the birds flee it, and a
 * click in the sky, not on the form, sets off a gust. Returns the removal of the listeners.
 */
function listen({ scene, input, flip }: FlockElements, { pointer, gusts }: World): () => void {
  const scenePoint = (event: PointerEvent) => {
    const box = scene.getBoundingClientRect();
    return { x: event.clientX - box.left, y: event.clientY - box.top };
  };
  const handleMove = (event: PointerEvent) => {
    Object.assign(pointer, scenePoint(event), { isInside: true });
    flip.setAttribute("transform", pointer.x < MAN_X && document.activeElement !== input ? "scale(-1 1)" : "");
  };
  const handleLeave = () => {
    pointer.isInside = false;
  };
  const handleDown = (event: PointerEvent) => {
    if (event.target instanceof Element && event.target.closest("form, button, a, input")) return;
    gusts.push({ ...scenePoint(event), at: performance.now() });
  };
  const handleFocus = () => flip.setAttribute("transform", "");
  scene.addEventListener("pointermove", handleMove);
  scene.addEventListener("pointerleave", handleLeave);
  scene.addEventListener("pointerdown", handleDown);
  input.addEventListener("focus", handleFocus);
  return () => {
    scene.removeEventListener("pointermove", handleMove);
    scene.removeEventListener("pointerleave", handleLeave);
    scene.removeEventListener("pointerdown", handleDown);
    input.removeEventListener("focus", handleFocus);
  };
}

/** The caret in scene coordinates, measuring the text before it in the input's font. */
function caretPosition(input: HTMLInputElement, scene: HTMLElement, measure: CanvasRenderingContext2D | null) {
  const style = getComputedStyle(input);
  const box = input.getBoundingClientRect();
  const sceneBox = scene.getBoundingClientRect();
  let textWidth = 0;
  if (measure) {
    measure.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    textWidth = measure.measureText(input.value.slice(0, input.selectionStart ?? input.value.length)).width;
  }
  return { x: box.left - sceneBox.left + Math.min(textWidth - input.scrollLeft, box.width - 10), y: box.top - sceneBox.top };
}

function frameAt(world: World, now: number, last: number): Frame {
  const elapsed = Math.min(0.05, (now - last) / 1000);
  return { ...world, now, steps: elapsed * 60, seconds: now / 1000, typing: now - world.caret.at < TYPING_MS, gulping: now - world.gulpAt.at < GULP_MS };
}

/** Birds keep clear of their closest neighbours, and move toward and along with the flock around them. */
function flockWith(bird: Bird, index: number, birds: Bird[], steer: Steering): void {
  let sumX = 0;
  let sumY = 0;
  let sumVx = 0;
  let sumVy = 0;
  let n = 0;
  for (let j = 0; j < birds.length; j += 1) {
    if (index === j) continue;
    const other = birds[j]!;
    const dx = other.x - bird.x;
    const dy = other.y - bird.y;
    const distanceSquared = dx * dx + dy * dy;
    if (distanceSquared < SEPARATION_PX * SEPARATION_PX && distanceSquared > 0.01) {
      const distance = Math.sqrt(distanceSquared);
      steer.ax -= (dx / distance) * (SEPARATION_PX - distance) * 0.014;
      steer.ay -= (dy / distance) * (SEPARATION_PX - distance) * 0.014;
    }
    if (distanceSquared < NEIGHBOUR_PX * NEIGHBOUR_PX) {
      sumX += other.x;
      sumY += other.y;
      sumVx += other.vx;
      sumVy += other.vy;
      n += 1;
    }
  }
  if (n) {
    steer.ax += (sumX / n - bird.x) * 0.0006 + (sumVx / n - bird.vx) * 0.03;
    steer.ay += (sumY / n - bird.y) * 0.0006 + (sumVy / n - bird.vy) * 0.03;
  }
}

/** The flock drifts on a slow loop round the sky, and each bird wobbles on its own. */
function drift(bird: Bird, index: number, frame: Frame, steer: Steering): void {
  const { sky, seconds, now } = frame;
  steer.ax += (sky.width * (0.58 + 0.3 * Math.sin(seconds * 0.11)) - bird.x) * 0.0003;
  steer.ay += (sky.height * (0.24 + 0.1 * Math.cos(seconds * 0.13)) - bird.y) * 0.0004;
  steer.ax += Math.sin(now * 0.0008 + index * 1.7) * 0.01;
  steer.ay += Math.cos(now * 0.001 + index * 2.3) * 0.008;
}

/** Birds avoid the edges, and stay above the rooftops. */
function keepInSky(bird: Bird, sky: Sky, steer: Steering): void {
  const margin = 30;
  if (bird.x < margin) steer.ax += (margin - bird.x) * 0.006;
  if (bird.x > sky.width - margin) steer.ax -= (bird.x - (sky.width - margin)) * 0.006;
  if (bird.y < margin) steer.ay += (margin - bird.y) * 0.006;
  if (bird.y > sky.height * 0.5) steer.ay -= (bird.y - sky.height * 0.5) * 0.01;
}

function fleePointer(bird: Bird, pointer: Pointer, steer: Steering): void {
  const dx = bird.x - pointer.x;
  const dy = bird.y - pointer.y;
  const distance = Math.hypot(dx, dy);
  if (distance < FLEE_PX && distance > 0.1) {
    const push = (FLEE_PX - distance) / FLEE_PX;
    steer.ax += (dx / distance) * push * 0.6;
    steer.ay += (dy / distance) * push * 0.6;
    bird.dart = Math.max(bird.dart, push);
  }
}

/** A gust pushes the birds around it away, for half a second. */
function scatter(bird: Bird, frame: Frame, steer: Steering): void {
  for (const gust of frame.gusts) {
    if ((frame.now - gust.at) / 1000 > 0.5) continue;
    const dx = bird.x - gust.x;
    const dy = bird.y - gust.y;
    const distance = Math.hypot(dx, dy) || 1;
    if (distance < GUST_PX) {
      steer.ax += (dx / distance) * 0.5 * (1 - distance / GUST_PX);
      steer.ay += (dy / distance) * 0.5 * (1 - distance / GUST_PX);
      bird.dart = 1;
    }
  }
}

/** Birds gather around the caret, each at its own distance; the pull fades after the keystroke. */
function gatherAtCaret(bird: Bird, index: number, frame: Frame, steer: Steering): void {
  const { caret } = frame;
  const dx = caret.x - bird.x;
  const dy = caret.y - 34 - bird.y;
  const distance = Math.hypot(dx, dy) || 1;
  const want = 40 + (index % 5) * 12;
  const pull = (distance - want) * 0.0018 * (1 - (frame.now - caret.at) / TYPING_MS);
  steer.ax += (dx / distance) * pull;
  steer.ay += (dy / distance) * pull;
}

/** Birds dive into the input box, and vanish once there. */
function diveIntoBox(bird: Bird, frame: Frame, steer: Steering): void {
  const dx = frame.gulpAt.x - bird.x;
  const dy = frame.gulpAt.y - bird.y;
  const distance = Math.hypot(dx, dy) || 1;
  steer.ax += (dx / distance) * 0.35;
  steer.ay += (dy / distance) * 0.35;
  if (distance < 30) bird.gone = Math.min(1, bird.gone + 0.12 * frame.steps);
}

/** The bird accelerates within its speed bounds (wider while darting or diving), moves, and beats its wings. */
function fly(bird: Bird, steer: Steering, frame: Frame): void {
  const { steps } = frame;
  bird.dart = Math.max(0, bird.dart - 0.02 * steps);
  const maxSpeed = 1.5 * (1 + bird.dart * 2 + (frame.gulping ? 1.8 : 0));
  const minSpeed = 0.5;
  bird.vx += steer.ax * steps;
  bird.vy += steer.ay * steps;
  const speed = Math.hypot(bird.vx, bird.vy);
  if (speed > maxSpeed) {
    bird.vx *= maxSpeed / speed;
    bird.vy *= maxSpeed / speed;
  } else if (speed < minSpeed) {
    bird.vx *= minSpeed / Math.max(speed, 0.01);
    bird.vy *= minSpeed / Math.max(speed, 0.01);
  }
  bird.x += bird.vx * steps;
  bird.y += bird.vy * steps;
  bird.phase += (0.22 + speed * 0.08 + bird.dart * 0.3) * steps;
}

/** The steering rules, in their order, then the flight. */
function updateBird(bird: Bird, index: number, frame: Frame): void {
  const steer: Steering = { ax: 0, ay: 0 };
  flockWith(bird, index, frame.birds, steer);
  drift(bird, index, frame, steer);
  keepInSky(bird, frame.sky, steer);
  if (frame.pointer.isInside && !frame.gulping) fleePointer(bird, frame.pointer, steer);
  scatter(bird, frame, steer);
  if (frame.typing && !frame.gulping) gatherAtCaret(bird, index, frame, steer);
  if (frame.gulping) diveIntoBox(bird, frame, steer);
  fly(bird, steer, frame);
}

/** One frame of the simulation: the birds one after the other (each sees those before it already moved), then old gusts go. */
function advance(frame: Frame): void {
  const { birds, gusts, now } = frame;
  for (let i = 0; i < birds.length; i += 1) updateBird(birds[i]!, i, frame);
  for (let i = gusts.length - 1; i >= 0; i -= 1) if (now - (gusts[i]?.at ?? 0) > GUST_MS) gusts.splice(i, 1);
}

/** The ring a click leaves in the sky, widening as it fades. */
function drawGust(context: CanvasRenderingContext2D, gust: Mark, now: number): void {
  const age = (now - gust.at) / GUST_MS;
  context.strokeStyle = `rgba(11,35,65,${0.25 * (1 - age)})`;
  context.lineWidth = 1.5;
  context.beginPath();
  context.arc(gust.x, gust.y, 10 + age * 70, 0, Math.PI * 2);
  context.stroke();
}

/** Each bird is two curved wing strokes that beat. */
function drawBird(context: CanvasRenderingContext2D, bird: Bird): void {
  const alpha = 1 - bird.gone;
  if (alpha < 0.02) return;
  const span = 9 * bird.size;
  const flap = Math.sin(bird.phase) * span * 0.55;
  const angle = Math.atan2(bird.vy, bird.vx) * 0.25;
  context.save();
  context.translate(bird.x, bird.y);
  context.rotate(angle);
  context.strokeStyle = bird.isRed ? `rgba(228,28,35,${alpha})` : `rgba(11,35,65,${alpha * 0.85})`;
  context.lineWidth = 2;
  context.beginPath();
  context.moveTo(-span, -flap);
  context.quadraticCurveTo(-span * 0.45, -flap * 0.2 - 2, 0, 1);
  context.quadraticCurveTo(span * 0.45, -flap * 0.2 - 2, span, -flap);
  context.stroke();
  context.restore();
}

function drawFrame(context: CanvasRenderingContext2D, frame: Frame): void {
  const { sky } = frame;
  context.setTransform(sky.pixelRatio, 0, 0, sky.pixelRatio, 0, 0);
  context.clearRect(0, 0, sky.width, sky.height);
  for (const gust of frame.gusts) drawGust(context, gust, frame.now);
  context.lineCap = "round";
  context.lineJoin = "round";
  for (const bird of frame.birds) drawBird(context, bird);
}

export function startFlock(elements: FlockElements): Flock {
  const { scene, canvas, input, form, flip, thought } = elements;
  const context = canvas.getContext("2d");
  const sky: Sky = { width: 0, height: 0, pixelRatio: 1 };
  fitCanvas(sky, scene, canvas);
  const resizer = new ResizeObserver(() => fitCanvas(sky, scene, canvas));
  resizer.observe(scene);

  const world: World = {
    sky,
    birds: hatchBirds(sky.width),
    pointer: { x: -999, y: -999, isInside: false },
    caret: { x: 0, y: 0, at: -1e9 },
    gulpAt: { x: 0, y: 0, at: -1e9 },
    gusts: [],
  };
  const unlisten = listen(elements, world);
  const measure = document.createElement("canvas").getContext("2d");

  let request = 0;
  let last = performance.now();
  const tick = (now: number) => {
    const frame = frameAt(world, now, last);
    last = now;
    advance(frame);
    if (context) drawFrame(context, frame);
    request = requestAnimationFrame(tick);
  };
  request = requestAnimationFrame(tick);

  return {
    typed() {
      Object.assign(world.caret, caretPosition(input, scene, measure), { at: performance.now() });
      flip.setAttribute("transform", "");
      const head = flip.getBoundingClientRect();
      const sceneBox = scene.getBoundingClientRect();
      thought.style.left = `${head.right - sceneBox.left - 6}px`;
      thought.style.top = `${head.top - sceneBox.top - 36}px`;
    },
    gulp() {
      const sceneBox = scene.getBoundingClientRect();
      const box = form.getBoundingClientRect();
      Object.assign(world.gulpAt, { x: (box.left + box.right) / 2 - sceneBox.left, y: (box.top + box.bottom) / 2 - sceneBox.top, at: performance.now() });
    },
    stop() {
      cancelAnimationFrame(request);
      resizer.disconnect();
      unlisten();
    },
  };
}
