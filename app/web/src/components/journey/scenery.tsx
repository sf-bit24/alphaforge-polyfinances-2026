"use client";

import { stopX, WORLD } from "@/lib/journey/geometry";
import type { StopKind } from "@/lib/journey/path";
import styles from "./journey.module.css";

const MAX_STOPS = 48;
export const GROUND = WORLD.ground;

export interface Scenery {
  world: number;
  hills: string;
  blocks: Array<{ x: number; width: number; height: number; windows: string }>;
  trees: Array<{ x: number; height: number; radius: number; fill: string; extra: { x: number; y: number; radius: number } | null }>;
  tufts: string;
  dashes: string;
}

function hillsPath(world: number): string {
  let hills = `M -200 ${GROUND}`;
  const hillsEnd = world * 0.35 + 3000;
  for (let x = -200; x <= hillsEnd; x += 40) hills += ` L ${x} ${(GROUND - 120 - 50 * Math.sin(x / 260) - 26 * Math.sin(x / 97)).toFixed(1)}`;
  hills += ` L ${hillsEnd} ${GROUND} Z`;
  return hills;
}

function windowsPath(x: number, width: number, height: number): string {
  let windows = "";
  for (let windowY = GROUND - height + 18; windowY < GROUND - 30; windowY += 30)
    for (let windowX = x + 14; windowX < x + width - 18; windowX += 24) windows += `M${windowX.toFixed(1)} ${windowY.toFixed(1)}h10v14h-10z`;
  return windows;
}

/** The middle layer, left to right: city blocks near the start, then the park's and the countryside's trees. */
function blocksAndTrees(world: number, random: () => number) {
  const blocks: Scenery["blocks"] = [];
  const trees: Scenery["trees"] = [];
  let x = -100;
  while (x < world * 0.65 + 3000) {
    const worldX = x / 0.65;
    if (worldX < 2600) {
      const width = 90 + random() * 90;
      const height = 140 + random() * 200;
      blocks.push({ x, width, height, windows: windowsPath(x, width, height) });
      x += width + 10 + random() * 30;
    } else {
      const radius = 34 + random() * 30;
      const height = 50 + random() * 40;
      const extra = random() > 0.5 ? { x: x + radius * 0.6, y: GROUND - height - radius * 0.3, radius: radius * 0.65 } : null;
      trees.push({ x, height, radius, fill: worldX < 5200 ? "#D5DFEA" : "#CFDAE6", extra });
      x += radius * 2 + 40 + random() * 140;
    }
  }
  return { blocks, trees };
}

function dashesPath(world: number): string {
  let dashes = "";
  for (let dashX = -400; dashX < world + 3000; dashX += 70) dashes += `M${dashX} ${GROUND + 10}h30v3h-30z`;
  return dashes;
}

function tuftsPath(world: number, random: () => number): string {
  let tufts = "";
  for (let tuftX = 0; tuftX < world + 2000; tuftX += 180 + random() * 260) {
    const tuftY = GROUND + 48 + random() * 50;
    tufts += `M${tuftX.toFixed(1)} ${tuftY.toFixed(1)}q6 -22 12 0q6 -30 12 0q6 -18 12 0z`;
  }
  return tufts;
}

/** The draft's city, park and countryside, from the same seeded random sequence. */
export function buildScenery(): Scenery {
  let seed = 7;
  const random = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const world = stopX(MAX_STOPS) + 2400;
  const hills = hillsPath(world);
  const { blocks, trees } = blocksAndTrees(world, random);
  const dashes = dashesPath(world);
  const tufts = tuftsPath(world, random);
  return { world, hills, blocks, trees, tufts, dashes };
}

export function CityLayer({ scenery }: { scenery: Scenery }) {
  return (
    <>
      {scenery.blocks.map((block) => (
        <g key={`b${block.x}`}>
          <rect x={block.x} y={GROUND - block.height} width={block.width} height={block.height} fill="#DCE4EE" />
          <path d={block.windows} fill="#fff" />
        </g>
      ))}
      {scenery.trees.map((tree) => (
        <g key={`t${tree.x}`}>
          <rect x={tree.x - 5} y={GROUND - tree.height} width={10} height={tree.height} fill="#C3CFDC" />
          <circle cx={tree.x} cy={GROUND - tree.height - tree.radius * 0.7} r={tree.radius} fill={tree.fill} />
          {tree.extra ? <circle cx={tree.extra.x} cy={tree.extra.y} r={tree.extra.radius} fill="#DCE4EE" /> : null}
        </g>
      ))}
    </>
  );
}

export function Road({ scenery }: { scenery: Scenery }) {
  return (
    <>
      <rect x={-500} y={GROUND} width={scenery.world + 4000} height={WORLD.height - GROUND} fill="#F5F7FA" />
      <rect x={-500} y={GROUND - 2} width={scenery.world + 4000} height={26} fill="#E6EBF1" />
      <path d={scenery.dashes} fill="#fff" />
      <path d={scenery.tufts} fill="#DDE5EE" />
    </>
  );
}

export function SignPost({ index, kind, animate }: { index: number; kind: StopKind; animate: boolean }) {
  return (
    <g transform={`translate(${stopX(index) + WORLD.manX + 110} ${GROUND})`}>
      <g className={animate ? styles.plant : undefined}>
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
export function House({ index, animate }: { index: number; animate: boolean }) {
  return (
    <g transform={`translate(${stopX(index) + WORLD.manX} ${GROUND})`}>
      <g className={animate ? styles.plant : undefined}>
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
