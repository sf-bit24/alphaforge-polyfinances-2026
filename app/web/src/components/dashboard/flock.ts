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
  ph: number;
  size: number;
  dart: number;
  gone: number;
  red: boolean;
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

export function startFlock({ scene, canvas, input, form, flip, thought }: FlockElements): Flock {
  const ctx = canvas.getContext("2d");
  let width = 0;
  let height = 0;
  let dpr = 1;
  const size = () => {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    width = scene.clientWidth;
    height = scene.clientHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
  };
  size();
  const resizer = new ResizeObserver(size);
  resizer.observe(scene);

  const birds: Bird[] = Array.from({ length: 16 }, (_, index) => ({
    x: Math.min(width - 40, 260 + Math.random() * 520),
    y: 40 + Math.random() * 150,
    vx: (Math.random() < 0.5 ? -1 : 1) * (0.8 + Math.random() * 0.5),
    vy: (Math.random() - 0.5) * 0.4,
    ph: Math.random() * 6.28,
    size: 0.8 + Math.random() * 0.45,
    dart: 0,
    gone: 0,
    red: index === 0,
  }));
  const pointer = { x: -999, y: -999, on: false };
  const caret = { x: 0, y: 0, t: -1e9 };
  const gulpAt = { x: 0, y: 0, t: -1e9 };
  const gusts: Array<{ x: number; y: number; t0: number }> = [];

  const local = (event: PointerEvent) => {
    const box = scene.getBoundingClientRect();
    return { x: event.clientX - box.left, y: event.clientY - box.top };
  };
  const onMove = (event: PointerEvent) => {
    Object.assign(pointer, local(event), { on: true });
    flip.setAttribute("transform", pointer.x < MAN_X && document.activeElement !== input ? "scale(-1 1)" : "");
  };
  const onLeave = () => {
    pointer.on = false;
  };
  const onDown = (event: PointerEvent) => {
    if (event.target instanceof Element && event.target.closest("form, button, a, input")) return;
    gusts.push({ ...local(event), t0: performance.now() });
  };
  const onFocus = () => flip.setAttribute("transform", "");
  scene.addEventListener("pointermove", onMove);
  scene.addEventListener("pointerleave", onLeave);
  scene.addEventListener("pointerdown", onDown);
  input.addEventListener("focus", onFocus);

  const measure = document.createElement("canvas").getContext("2d");
  const caretPosition = () => {
    const style = getComputedStyle(input);
    const box = input.getBoundingClientRect();
    const sceneBox = scene.getBoundingClientRect();
    let textWidth = 0;
    if (measure) {
      measure.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
      textWidth = measure.measureText(input.value.slice(0, input.selectionStart ?? input.value.length)).width;
    }
    return { x: box.left - sceneBox.left + Math.min(textWidth - input.scrollLeft, box.width - 10), y: box.top - sceneBox.top };
  };

  let frame = 0;
  let last = performance.now();
  const tick = (now: number) => {
    const dt = Math.min(0.05, (now - last) / 1000);
    const k = dt * 60;
    last = now;
    const typing = now - caret.t < 1800;
    const gulping = now - gulpAt.t < 1500;
    const ts = now / 1000;
    for (let i = 0; i < birds.length; i += 1) {
      const bird = birds[i]!;
      let ax = 0;
      let ay = 0;
      let cx = 0;
      let cy = 0;
      let avx = 0;
      let avy = 0;
      let n = 0;
      for (let j = 0; j < birds.length; j += 1) {
        if (i === j) continue;
        const other = birds[j]!;
        const dx = other.x - bird.x;
        const dy = other.y - bird.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < 26 * 26 && d2 > 0.01) {
          const d = Math.sqrt(d2);
          ax -= (dx / d) * (26 - d) * 0.014;
          ay -= (dy / d) * (26 - d) * 0.014;
        }
        if (d2 < 90 * 90) {
          cx += other.x;
          cy += other.y;
          avx += other.vx;
          avy += other.vy;
          n += 1;
        }
      }
      if (n) {
        ax += (cx / n - bird.x) * 0.0006 + (avx / n - bird.vx) * 0.03;
        ay += (cy / n - bird.y) * 0.0006 + (avy / n - bird.vy) * 0.03;
      }
      // The flock drifts on a slow loop round the sky.
      ax += (width * (0.58 + 0.3 * Math.sin(ts * 0.11)) - bird.x) * 0.0003;
      ay += (height * (0.24 + 0.1 * Math.cos(ts * 0.13)) - bird.y) * 0.0004;
      ax += Math.sin(now * 0.0008 + i * 1.7) * 0.01;
      ay += Math.cos(now * 0.001 + i * 2.3) * 0.008;
      // Edges, and stay above the rooftops.
      const margin = 30;
      if (bird.x < margin) ax += (margin - bird.x) * 0.006;
      if (bird.x > width - margin) ax -= (bird.x - (width - margin)) * 0.006;
      if (bird.y < margin) ay += (margin - bird.y) * 0.006;
      if (bird.y > height * 0.5) ay -= (bird.y - height * 0.5) * 0.01;
      if (pointer.on && !gulping) {
        const dx = bird.x - pointer.x;
        const dy = bird.y - pointer.y;
        const d = Math.hypot(dx, dy);
        if (d < 110 && d > 0.1) {
          const push = (110 - d) / 110;
          ax += (dx / d) * push * 0.6;
          ay += (dy / d) * push * 0.6;
          bird.dart = Math.max(bird.dart, push);
        }
      }
      for (const gust of gusts) {
        if ((now - gust.t0) / 1000 > 0.5) continue;
        const dx = bird.x - gust.x;
        const dy = bird.y - gust.y;
        const d = Math.hypot(dx, dy) || 1;
        if (d < 180) {
          ax += (dx / d) * 0.5 * (1 - d / 180);
          ay += (dy / d) * 0.5 * (1 - d / 180);
          bird.dart = 1;
        }
      }
      if (typing && !gulping) {
        const dx = caret.x - bird.x;
        const dy = caret.y - 34 - bird.y;
        const d = Math.hypot(dx, dy) || 1;
        const want = 40 + (i % 5) * 12;
        const pull = (d - want) * 0.0018 * (1 - (now - caret.t) / 1800);
        ax += (dx / d) * pull;
        ay += (dy / d) * pull;
      }
      if (gulping) {
        const dx = gulpAt.x - bird.x;
        const dy = gulpAt.y - bird.y;
        const d = Math.hypot(dx, dy) || 1;
        ax += (dx / d) * 0.35;
        ay += (dy / d) * 0.35;
        if (d < 30) bird.gone = Math.min(1, bird.gone + 0.12 * k);
      }
      bird.dart = Math.max(0, bird.dart - 0.02 * k);
      const maxV = 1.5 * (1 + bird.dart * 2 + (gulping ? 1.8 : 0));
      const minV = 0.5;
      bird.vx += ax * k;
      bird.vy += ay * k;
      const v = Math.hypot(bird.vx, bird.vy);
      if (v > maxV) {
        bird.vx *= maxV / v;
        bird.vy *= maxV / v;
      } else if (v < minV) {
        bird.vx *= minV / Math.max(v, 0.01);
        bird.vy *= minV / Math.max(v, 0.01);
      }
      bird.x += bird.vx * k;
      bird.y += bird.vy * k;
      bird.ph += (0.22 + v * 0.08 + bird.dart * 0.3) * k;
    }
    for (let i = gusts.length - 1; i >= 0; i -= 1) if (now - (gusts[i]?.t0 ?? 0) > 900) gusts.splice(i, 1);

    if (ctx) {
      // Each bird is two curved wing strokes that beat.
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      for (const gust of gusts) {
        const age = (now - gust.t0) / 900;
        ctx.strokeStyle = `rgba(11,35,65,${0.25 * (1 - age)})`;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(gust.x, gust.y, 10 + age * 70, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      for (const bird of birds) {
        const alpha = 1 - bird.gone;
        if (alpha < 0.02) continue;
        const span = 9 * bird.size;
        const flap = Math.sin(bird.ph) * span * 0.55;
        const angle = Math.atan2(bird.vy, bird.vx) * 0.25;
        ctx.save();
        ctx.translate(bird.x, bird.y);
        ctx.rotate(angle);
        ctx.strokeStyle = bird.red ? `rgba(228,28,35,${alpha})` : `rgba(11,35,65,${alpha * 0.85})`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(-span, -flap);
        ctx.quadraticCurveTo(-span * 0.45, -flap * 0.2 - 2, 0, 1);
        ctx.quadraticCurveTo(span * 0.45, -flap * 0.2 - 2, span, -flap);
        ctx.stroke();
        ctx.restore();
      }
    }
    frame = requestAnimationFrame(tick);
  };
  frame = requestAnimationFrame(tick);

  return {
    typed() {
      Object.assign(caret, caretPosition(), { t: performance.now() });
      flip.setAttribute("transform", "");
      const head = flip.getBoundingClientRect();
      const sceneBox = scene.getBoundingClientRect();
      thought.style.left = `${head.right - sceneBox.left - 6}px`;
      thought.style.top = `${head.top - sceneBox.top - 36}px`;
    },
    gulp() {
      const sceneBox = scene.getBoundingClientRect();
      const box = form.getBoundingClientRect();
      Object.assign(gulpAt, { x: (box.left + box.right) / 2 - sceneBox.left, y: (box.top + box.bottom) / 2 - sceneBox.top, t: performance.now() });
    },
    stop() {
      cancelAnimationFrame(frame);
      resizer.disconnect();
      scene.removeEventListener("pointermove", onMove);
      scene.removeEventListener("pointerleave", onLeave);
      scene.removeEventListener("pointerdown", onDown);
      input.removeEventListener("focus", onFocus);
    },
  };
}
