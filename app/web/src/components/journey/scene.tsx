"use client";

import { forwardRef, useImperativeHandle, useLayoutEffect, useMemo, useRef, type Ref, type RefObject } from "react";
import type { StopKind } from "@/lib/journey/path";
import s from "./journey.module.css";

import { sceneLayout, stopX, WORLD } from "@/lib/journey/geometry";

export { sceneLayout, stopX, WORLD };

const MAX_STOPS = 48;
const SPEED = 400; // design px / s
const G = WORLD.ground;

/** The walk plays even with reduced motion (it is the core of this screen); « Passer la marche » skips it. */
export interface SceneHandle {
  walkTo(index: number): Promise<void>;
  jumpTo(index: number): void;
  skip(): void;
}

interface Scenery {
  world: number;
  hills: string;
  blocks: Array<{ x: number; w: number; h: number; windows: string }>;
  trees: Array<{ x: number; h: number; r: number; fill: string; extra: { cx: number; cy: number; r: number } | null }>;
  tufts: string;
  dashes: string;
}

/** The draft's city, park and countryside, from the same seeded random sequence. */
function buildScenery(): Scenery {
  let seed = 7;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const world = stopX(MAX_STOPS) + 2400;

  let hills = `M -200 ${G}`;
  const hillsEnd = world * 0.35 + 3000;
  for (let x = -200; x <= hillsEnd; x += 40) hills += ` L ${x} ${(G - 120 - 50 * Math.sin(x / 260) - 26 * Math.sin(x / 97)).toFixed(1)}`;
  hills += ` L ${hillsEnd} ${G} Z`;

  const blocks: Scenery["blocks"] = [];
  const trees: Scenery["trees"] = [];
  let x = -100;
  while (x < world * 0.65 + 3000) {
    const at = x / 0.65;
    if (at < 2600) {
      const w = 90 + rnd() * 90;
      const h = 140 + rnd() * 200;
      let windows = "";
      for (let wy = G - h + 18; wy < G - 30; wy += 30)
        for (let wx = x + 14; wx < x + w - 18; wx += 24) windows += `M${wx.toFixed(1)} ${wy.toFixed(1)}h10v14h-10z`;
      blocks.push({ x, w, h, windows });
      x += w + 10 + rnd() * 30;
    } else {
      const r = 34 + rnd() * 30;
      const h = 50 + rnd() * 40;
      const extra = rnd() > 0.5 ? { cx: x + r * 0.6, cy: G - h - r * 0.3, r: r * 0.65 } : null;
      trees.push({ x, h, r, fill: at < 5200 ? "#D5DFEA" : "#CFDAE6", extra });
      x += r * 2 + 40 + rnd() * 140;
    }
  }

  let dashes = "";
  for (let dx = -400; dx < world + 3000; dx += 70) dashes += `M${dx} ${G + 10}h30v3h-30z`;

  let tufts = "";
  for (let tx = 0; tx < world + 2000; tx += 180 + rnd() * 260) {
    const ty = G + 48 + rnd() * 50;
    tufts += `M${tx.toFixed(1)} ${ty.toFixed(1)}q6 -22 12 0q6 -30 12 0q6 -18 12 0z`;
  }
  return { world, hills, blocks, trees, tufts, dashes };
}

const C = {
  skin: "#C98E6B",
  skinB: "#B57B59",
  hair: "#2B2321",
  jacket: "#0B2341",
  jacketB: "#071A31",
  pants: "#3A4B60",
  pantsB: "#2E3D50",
  shoe: "#1A1A1A",
  shirt: "#FFFFFF",
  pack: "#E41C23",
  packB: "#B8141A",
};

interface LimbRefs {
  top: RefObject<SVGGElement | null>;
  joint: RefObject<SVGGElement | null>;
}

function Limb({
  topRef,
  jointRef,
  upLen,
  loLen,
  wUp,
  wLo,
  cUp,
  cLo,
  foot,
  hand,
}: {
  topRef: RefObject<SVGGElement | null>;
  jointRef: RefObject<SVGGElement | null>;
  upLen: number;
  loLen: number;
  wUp: number;
  wLo: number;
  cUp: string;
  cLo: string;
  foot?: boolean;
  hand?: string;
}) {
  return (
    <g ref={topRef}>
      <rect x={-wUp / 2} y={-4} width={wUp} height={upLen + 8} rx={wUp / 2} fill={cUp} />
      <g ref={jointRef}>
        <rect x={-wLo / 2} y={-4} width={wLo} height={loLen + 6} rx={wLo / 2} fill={cLo} />
        {foot ? <path d={`M ${-wLo / 2 - 1} ${loLen - 4} h ${wLo + 16} a 7 7 0 0 1 0 14 h ${-(wLo + 16)} z`} fill={C.shoe} /> : null}
        {hand ? <circle cx={0} cy={loLen + 4} r={7.5} fill={hand} /> : null}
      </g>
    </g>
  );
}

function SignPost({ index, kind, animate }: { index: number; kind: StopKind; animate: boolean }) {
  return (
    <g transform={`translate(${stopX(index) + WORLD.manX + 110} ${G})`}>
      <g className={animate ? s.plant : undefined}>
        <rect x={-3} y={-150} width={6} height={150} rx={3} fill="#0B2341" />
        {kind === "portfolio" ? (
          <>
            <path d="M3 -146 h58 l12 14 l-12 14 h-58 z" fill="#0B2341" />
            <rect x={14} y={-138} width={22} height={14} rx={2.5} fill="none" stroke="#fff" strokeWidth={2} />
            <path d="M21 -138 v-3 a2 2 0 0 1 2 -2 h4 a2 2 0 0 1 2 2 v3" fill="none" stroke="#fff" strokeWidth={2} />
            <rect x={44} y={-136} width={9} height={9} rx={2} fill="#E41C23" />
          </>
        ) : (
          <path d="M3 -146 h46 l12 14 l-12 14 h-46 z" fill="#E41C23" />
        )}
        <ellipse cx={0} cy={2} rx={16} ry={4} fill="#E1E7EE" />
      </g>
    </g>
  );
}

/** The house is drawn around the walker's last stop: he ends up standing at his door. */
function House({ index, animate }: { index: number; animate: boolean }) {
  return (
    <g transform={`translate(${stopX(index) + WORLD.manX} ${G})`}>
      <g className={animate ? s.plant : undefined}>
        <rect x={110} y={-330} width={30} height={70} fill="#0B2341" />
        <rect x={-150} y={-232} width={320} height={232} fill="#fff" stroke="#0B2341" strokeWidth={4} />
        <path d="M-174 -226 L10 -372 L194 -226 Z" fill="#E41C23" />
        <rect x={34} y={-150} width={66} height={150} fill="#0B2341" />
        <circle cx={88} cy={-74} r={4} fill="#DCE4EE" />
        <rect x={-122} y={-190} width={58} height={50} fill="#DCE4EE" />
        <rect x={114} y={-190} width={36} height={50} fill="#DCE4EE" />
        <rect x={-14} y={-4} width={140} height={8} rx={2} fill="#E1E7EE" />
      </g>
    </g>
  );
}

interface Motion {
  scroll: number;
  target: number;
  phase: number;
  walk: number;
  idle: number;
  moving: boolean;
  arrived: Array<() => void>;
}

interface SceneProps {
  /** Stop where the walker stands when the scene mounts (-1: the start of the path). */
  initialStand: number;
  signs: Record<number, StopKind>;
  house: number | null;
  /** The stop that rises from the ground; the others are drawn in place. */
  planted: number | null;
  onMovingChange?: (moving: boolean) => void;
}

function SceneImpl({ initialStand, signs, house, planted, onMovingChange }: SceneProps, ref: Ref<SceneHandle>) {
  const scenery = useMemo(() => buildScenery(), []);
  const svgRef = useRef<SVGSVGElement>(null);
  const rootRef = useRef<SVGGElement>(null);
  const skyRef = useRef<SVGRectElement>(null);
  const farRef = useRef<SVGGElement>(null);
  const midRef = useRef<SVGGElement>(null);
  const nearRef = useRef<SVGGElement>(null);
  const bodyRef = useRef<SVGGElement>(null);
  const shadowRef = useRef<SVGEllipseElement>(null);
  const legFTop = useRef<SVGGElement>(null);
  const legFJoint = useRef<SVGGElement>(null);
  const legBTop = useRef<SVGGElement>(null);
  const legBJoint = useRef<SVGGElement>(null);
  const armFTop = useRef<SVGGElement>(null);
  const armFJoint = useRef<SVGGElement>(null);
  const armBTop = useRef<SVGGElement>(null);
  const armBJoint = useRef<SVGGElement>(null);
  const motion = useRef<Motion>({
    scroll: stopX(initialStand),
    target: stopX(initialStand),
    phase: 0,
    walk: 0,
    idle: 0,
    moving: false,
    arrived: [],
  });
  const onMoving = useRef(onMovingChange);

  useLayoutEffect(() => {
    onMoving.current = onMovingChange;
  }, [onMovingChange]);

  useImperativeHandle(
    ref,
    () => ({
      walkTo(index: number) {
        const m = motion.current;
        m.target = Math.max(m.scroll, stopX(index));
        return new Promise<void>((resolve) => m.arrived.push(resolve));
      },
      jumpTo(index: number) {
        const m = motion.current;
        m.scroll = m.target = stopX(index);
        m.walk = 0;
        const waiting = m.arrived.splice(0);
        waiting.forEach((resolve) => resolve());
      },
      skip() {
        const m = motion.current;
        m.scroll = m.target;
      },
    }),
    [],
  );

  useLayoutEffect(() => {
    const svg = svgRef.current;
    const root = rootRef.current;
    const sky = skyRef.current;
    if (!svg || !root || !sky) return;
    const m = motion.current;
    const legs = { front: { top: legFTop, joint: legFJoint }, back: { top: legBTop, joint: legBJoint } };
    const arms = { front: { top: armFTop, joint: armFJoint }, back: { top: armBTop, joint: armBJoint } };

    const layout = () => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      const { scale, x, y } = sceneLayout(width, height);
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      root.setAttribute("transform", `translate(${x} ${y}) scale(${scale})`);
      sky.setAttribute("x", String(-x / scale - 10));
      sky.setAttribute("y", String(-y / scale - 10));
      sky.setAttribute("width", String(width / scale + 20));
      sky.setAttribute("height", String(height / scale + 20));
    };
    layout();
    window.addEventListener("resize", layout);

    const pose = (phase: number, walk: number) => {
      const c = Math.cos(phase);
      const hipY = -118 - walk * 3 * Math.abs(c);
      const thigh = (a: number) => -26 * walk * a;
      const knee = (a: number) => walk * (8 + 34 * Math.max(0, a));
      const setLeg = (leg: LimbRefs, ph: number, front: boolean) => {
        const a = Math.sin(ph);
        const k = Math.sin(ph + 1.9);
        leg.top.current?.setAttribute("transform", `translate(0 ${hipY}) rotate(${thigh(a) + (walk ? 0 : front ? -3 : 3)})`);
        leg.joint.current?.setAttribute("transform", `translate(0 60) rotate(${knee(k)})`);
      };
      setLeg(legs.front, phase, true);
      setLeg(legs.back, phase + Math.PI, false);
      const setArm = (arm: LimbRefs, ph: number, base: number) => {
        const a = Math.sin(ph);
        arm.top.current?.setAttribute("transform", `translate(2 ${hipY - 82}) rotate(${base + 22 * walk * a})`);
        arm.joint.current?.setAttribute("transform", `translate(0 46) rotate(${-14 - walk * 16 * Math.max(0, a)})`);
      };
      setArm(arms.front, phase + Math.PI, -4);
      setArm(arms.back, phase, 6);
      bodyRef.current?.setAttribute("transform", `translate(0 ${-118 - hipY})`);
      shadowRef.current?.setAttribute("rx", String(44 + walk * 6 * Math.abs(Math.sin(phase))));
    };

    let last = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const moving = m.scroll < m.target - 0.5;
      if (moving !== m.moving) {
        m.moving = moving;
        onMoving.current?.(moving);
      }
      if (moving) {
        m.scroll = Math.min(m.target, m.scroll + SPEED * dt * Math.min(1, m.walk + 0.25));
        m.phase += (dt * SPEED) / 42;
        m.walk = Math.min(1, m.walk + dt * 3);
        if (m.target - m.scroll < 60) m.walk = Math.max(0.15, (m.target - m.scroll) / 60);
      } else {
        m.walk = Math.max(0, m.walk - dt * 4);
        if (m.walk === 0 && m.arrived.length) m.arrived.splice(0).forEach((resolve) => resolve());
        m.idle += dt;
      }
      farRef.current?.setAttribute("transform", `translate(${-m.scroll * 0.35} 0)`);
      midRef.current?.setAttribute("transform", `translate(${-m.scroll * 0.65} 0)`);
      nearRef.current?.setAttribute("transform", `translate(${-m.scroll} 0)`);
      pose(m.phase, m.walk);
      if (!moving && m.walk === 0) bodyRef.current?.setAttribute("transform", `translate(0 ${Math.sin(m.idle * 2) * 0.8})`);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", layout);
    };
  }, []);

  return (
    <svg ref={svgRef} className={s.scene} aria-hidden focusable="false">
      <g ref={rootRef}>
        <rect ref={skyRef} x={0} y={0} width={4000} height={WORLD.height} fill="#fff" />
        <g ref={farRef}>
          <path d={scenery.hills} fill="#EDF1F6" />
        </g>
        <g ref={midRef}>
          {scenery.blocks.map((block) => (
            <g key={`b${block.x}`}>
              <rect x={block.x} y={G - block.h} width={block.w} height={block.h} fill="#DCE4EE" />
              <path d={block.windows} fill="#fff" />
            </g>
          ))}
          {scenery.trees.map((tree) => (
            <g key={`t${tree.x}`}>
              <rect x={tree.x - 5} y={G - tree.h} width={10} height={tree.h} fill="#C3CFDC" />
              <circle cx={tree.x} cy={G - tree.h - tree.r * 0.7} r={tree.r} fill={tree.fill} />
              {tree.extra ? <circle cx={tree.extra.cx} cy={tree.extra.cy} r={tree.extra.r} fill="#DCE4EE" /> : null}
            </g>
          ))}
        </g>
        <g ref={nearRef}>
          <rect x={-500} y={G} width={scenery.world + 4000} height={WORLD.height - G} fill="#F5F7FA" />
          <rect x={-500} y={G - 2} width={scenery.world + 4000} height={26} fill="#E6EBF1" />
          <path d={scenery.dashes} fill="#fff" />
          <path d={scenery.tufts} fill="#DDE5EE" />
          {Object.entries(signs).map(([index, kind]) => (
            <SignPost key={`${index}-${kind}`} index={Number(index)} kind={kind} animate={planted === Number(index)} />
          ))}
          {house !== null ? <House index={house} animate={planted === house} /> : null}
        </g>
        <g transform={`translate(${WORLD.manX} ${G})`}>
          <ellipse ref={shadowRef} cx={0} cy={3} rx={46} ry={7} fill="#E1E7EE" />
          <g ref={bodyRef}>
            <g>
              <Limb topRef={armBTop} jointRef={armBJoint} upLen={46} loLen={42} wUp={16} wLo={14} cUp={C.jacketB} cLo={C.jacketB} hand={C.skinB} />
            </g>
            <g>
              <Limb topRef={legBTop} jointRef={legBJoint} upLen={60} loLen={60} wUp={23} wLo={20} cUp={C.pantsB} cLo={C.pantsB} foot />
            </g>
            <g>
              <Limb topRef={legFTop} jointRef={legFJoint} upLen={60} loLen={60} wUp={23} wLo={20} cUp={C.pants} cLo={C.pants} foot />
            </g>
            <rect x={-44} y={-204} width={28} height={70} rx={9} fill={C.pack} />
            <rect x={-40} y={-170} width={20} height={18} rx={4} fill={C.packB} />
            <rect x={-22} y={-210} width={44} height={98} rx={18} fill={C.jacket} />
            <path d="M -2 -210 L 10 -184 L 22 -206 Z" fill={C.shirt} />
            <rect x={-17} y={-206} width={6} height={50} rx={3} fill={C.pack} />
            <rect x={-1} y={-226} width={14} height={20} rx={5} fill={C.skin} />
            <g transform="translate(6 -246)">
              <circle cx={0} cy={0} r={23} fill={C.skin} />
              <path d="M 20 -2 q 8 4 2 10" fill={C.skin} stroke={C.skin} strokeWidth={4} />
              <path
                d="M -23 2 C -26 -22 -6 -32 10 -27 C 20 -24 25 -16 24 -10 C 14 -16 2 -14 -6 -8 C -10 -2 -12 6 -18 12 C -22 10 -23 6 -23 2 Z"
                fill={C.hair}
              />
              <circle cx={-8} cy={3} r={5} fill={C.skinB} />
              <circle cx={13} cy={-2} r={2.6} fill="#1A1A1A" />
              <path d="M 10 11 q 6 3 11 -1" fill="none" stroke="#7A4A33" strokeWidth={2} strokeLinecap="round" />
            </g>
            <g>
              <Limb topRef={armFTop} jointRef={armFJoint} upLen={46} loLen={42} wUp={16} wLo={14} cUp={C.jacket} cLo={C.jacket} hand={C.skin} />
            </g>
          </g>
        </g>
      </g>
    </svg>
  );
}

export const Scene = forwardRef(SceneImpl);
