"use client";

import { forwardRef, useImperativeHandle, useLayoutEffect, useMemo, useRef, type Ref, type RefObject } from "react";
import type { StopKind } from "@/lib/journey/path";
import { buildScenery, CityLayer, House, Road, SignPost } from "./scenery";
import { poseWalker, Walker, type WalkerRefs } from "./walker";
import styles from "./journey.module.css";

import { sceneLayout, stopX, WORLD } from "@/lib/journey/geometry";

export { sceneLayout, stopX, WORLD };

const WALK_SPEED = 400; // design px / s

/** The walk plays even with reduced motion (it is the core of this screen); « Passer la marche » skips it. */
export interface SceneHandle {
  walkTo(index: number): Promise<void>;
  jumpTo(index: number): void;
  skip(): void;
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

type Layer = RefObject<SVGGElement | null>;

function restingAt(stand: number): Motion {
  return { scroll: stopX(stand), target: stopX(stand), phase: 0, walk: 0, idle: 0, moving: false, arrived: [] };
}

function walkHandle(motion: RefObject<Motion>): SceneHandle {
  return {
    walkTo(index: number) {
      const state = motion.current;
      state.target = Math.max(state.scroll, stopX(index));
      return new Promise<void>((resolve) => state.arrived.push(resolve));
    },
    jumpTo(index: number) {
      const state = motion.current;
      state.scroll = state.target = stopX(index);
      state.walk = 0;
      const waiting = state.arrived.splice(0);
      waiting.forEach((resolve) => resolve());
    },
    skip() {
      const state = motion.current;
      state.scroll = state.target;
    },
  };
}

/** Draws the world at the window's size, with a sky that covers the whole window. */
function fitToWindow(svg: SVGSVGElement, root: SVGGElement, sky: SVGRectElement) {
  const width = window.innerWidth;
  const height = window.innerHeight;
  const { scale, x, y } = sceneLayout(width, height);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  root.setAttribute("transform", `translate(${x} ${y}) scale(${scale})`);
  sky.setAttribute("x", String(-x / scale - 10));
  sky.setAttribute("y", String(-y / scale - 10));
  sky.setAttribute("width", String(width / scale + 20));
  sky.setAttribute("height", String(height / scale + 20));
}

/** One frame on the way: the walker speeds up from a stand, then slows down over the last 60 units. */
function walkOn(motion: Motion, deltaSeconds: number) {
  motion.scroll = Math.min(motion.target, motion.scroll + WALK_SPEED * deltaSeconds * Math.min(1, motion.walk + 0.25));
  motion.phase += (deltaSeconds * WALK_SPEED) / 42;
  motion.walk = Math.min(1, motion.walk + deltaSeconds * 3);
  if (motion.target - motion.scroll < 60) motion.walk = Math.max(0.15, (motion.target - motion.scroll) / 60);
}

/** One frame at the stop: the stride dies down, then the walks waiting for the arrival resolve. */
function settle(motion: Motion, deltaSeconds: number) {
  motion.walk = Math.max(0, motion.walk - deltaSeconds * 4);
  if (motion.walk === 0 && motion.arrived.length) motion.arrived.splice(0).forEach((resolve) => resolve());
  motion.idle += deltaSeconds;
}

function scrollLayers(layers: { far: Layer; mid: Layer; near: Layer }, scroll: number) {
  layers.far.current?.setAttribute("transform", `translate(${-scroll * 0.35} 0)`);
  layers.mid.current?.setAttribute("transform", `translate(${-scroll * 0.65} 0)`);
  layers.near.current?.setAttribute("transform", `translate(${-scroll} 0)`);
}

interface SceneElements {
  svg: SVGSVGElement;
  root: SVGGElement;
  sky: SVGRectElement;
  layers: { far: Layer; mid: Layer; near: Layer };
  walker: WalkerRefs;
}

/** Fits the scene to the window and runs the frame loop; returns the cleanup that stops both. */
function runScene({ svg, root, sky, layers, walker }: SceneElements, motion: Motion, onMoving: RefObject<SceneProps["onMovingChange"]>) {
  const layout = () => fitToWindow(svg, root, sky);
  layout();
  window.addEventListener("resize", layout);

  let last = performance.now();
  let frame = 0;
  const tick = (now: number) => {
    const deltaSeconds = Math.min(0.05, (now - last) / 1000);
    last = now;
    const moving = motion.scroll < motion.target - 0.5;
    if (moving !== motion.moving) {
      motion.moving = moving;
      onMoving.current?.(moving);
    }
    if (moving) walkOn(motion, deltaSeconds);
    else settle(motion, deltaSeconds);
    scrollLayers(layers, motion.scroll);
    poseWalker(walker, motion.phase, motion.walk);
    if (!moving && motion.walk === 0) walker.body.current?.setAttribute("transform", `translate(0 ${Math.sin(motion.idle * 2) * 0.8})`);
    frame = requestAnimationFrame(tick);
  };
  frame = requestAnimationFrame(tick);
  return () => {
    cancelAnimationFrame(frame);
    window.removeEventListener("resize", layout);
  };
}

/** The scene's elements, the walker's motion, the handle for the journey, and the frame loop. */
function useSceneAnimation(ref: Ref<SceneHandle>, initialStand: number, onMovingChange: SceneProps["onMovingChange"]) {
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
  const motion = useRef<Motion>(restingAt(initialStand));
  const onMoving = useRef(onMovingChange);

  useLayoutEffect(() => {
    onMoving.current = onMovingChange;
  }, [onMovingChange]);

  useImperativeHandle(ref, () => walkHandle(motion), []);

  useLayoutEffect(() => {
    const svg = svgRef.current;
    const root = rootRef.current;
    const sky = skyRef.current;
    if (!svg || !root || !sky) return;
    const layers = { far: farRef, mid: midRef, near: nearRef };
    const walker: WalkerRefs = {
      body: bodyRef,
      shadow: shadowRef,
      legs: { front: { top: legFTop, joint: legFJoint }, back: { top: legBTop, joint: legBJoint } },
      arms: { front: { top: armFTop, joint: armFJoint }, back: { top: armBTop, joint: armBJoint } },
    };
    return runScene({ svg, root, sky, layers, walker }, motion.current, onMoving);
  }, []);

  const walker = { bodyRef, shadowRef, legFTop, legFJoint, legBTop, legBJoint, armFTop, armFJoint, armBTop, armBJoint };
  return { svgRef, rootRef, skyRef, farRef, midRef, nearRef, walker };
}

function SceneImpl({ initialStand, signs, house, planted, onMovingChange }: SceneProps, ref: Ref<SceneHandle>) {
  const scenery = useMemo(() => buildScenery(), []);
  const { svgRef, rootRef, skyRef, farRef, midRef, nearRef, walker } = useSceneAnimation(ref, initialStand, onMovingChange);

  return (
    <svg ref={svgRef} className={styles.scene} aria-hidden focusable="false">
      <g ref={rootRef}>
        <rect ref={skyRef} x={0} y={0} width={4000} height={WORLD.height} fill="#fff" />
        <g ref={farRef}>
          <path d={scenery.hills} fill="#EDF1F6" />
        </g>
        <g ref={midRef}>
          <CityLayer scenery={scenery} />
        </g>
        <g ref={nearRef}>
          <Road scenery={scenery} />
          {Object.entries(signs).map(([index, kind]) => (
            <SignPost key={`${index}-${kind}`} index={Number(index)} kind={kind} animate={planted === Number(index)} />
          ))}
          {house !== null ? <House index={house} animate={planted === house} /> : null}
        </g>
        <Walker {...walker} />
      </g>
    </svg>
  );
}

export const Scene = forwardRef(SceneImpl);
