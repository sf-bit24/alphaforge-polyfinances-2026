"use client";

import type { RefObject } from "react";
import { WORLD } from "@/lib/journey/geometry";
import { GROUND } from "./scenery";

const COLORS = {
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

/** Lengths and widths of a limb's upper and lower parts, in design units. */
interface LimbSize {
  upperLength: number;
  lowerLength: number;
  upperWidth: number;
  lowerWidth: number;
}

const ARM: LimbSize = { upperLength: 46, lowerLength: 42, upperWidth: 16, lowerWidth: 14 };
const LEG: LimbSize = { upperLength: 60, lowerLength: 60, upperWidth: 23, lowerWidth: 20 };

interface LimbRefs {
  top: RefObject<SVGGElement | null>;
  joint: RefObject<SVGGElement | null>;
}

/** The walker's elements the frame loop moves, as `poseWalker` takes them. */
export interface WalkerRefs {
  body: RefObject<SVGGElement | null>;
  shadow: RefObject<SVGEllipseElement | null>;
  legs: { front: LimbRefs; back: LimbRefs };
  arms: { front: LimbRefs; back: LimbRefs };
}

/** The walker's elements, as `Walker` attaches them. */
export interface WalkerProps {
  bodyRef: RefObject<SVGGElement | null>;
  shadowRef: RefObject<SVGEllipseElement | null>;
  legFTop: RefObject<SVGGElement | null>;
  legFJoint: RefObject<SVGGElement | null>;
  legBTop: RefObject<SVGGElement | null>;
  legBJoint: RefObject<SVGGElement | null>;
  armFTop: RefObject<SVGGElement | null>;
  armFJoint: RefObject<SVGGElement | null>;
  armBTop: RefObject<SVGGElement | null>;
  armBJoint: RefObject<SVGGElement | null>;
}

interface LimbProps {
  topRef: RefObject<SVGGElement | null>;
  jointRef: RefObject<SVGGElement | null>;
  size: LimbSize;
  color: string;
  foot?: boolean;
  hand?: string;
}

function Limb({ topRef, jointRef, size, color, foot, hand }: LimbProps) {
  const { upperLength, lowerLength, upperWidth, lowerWidth } = size;
  return (
    <g ref={topRef}>
      <rect x={-upperWidth / 2} y={-4} width={upperWidth} height={upperLength + 8} rx={upperWidth / 2} fill={color} />
      <g ref={jointRef}>
        <rect x={-lowerWidth / 2} y={-4} width={lowerWidth} height={lowerLength + 6} rx={lowerWidth / 2} fill={color} />
        {foot ? (
          <path d={`M ${-lowerWidth / 2 - 1} ${lowerLength - 4} h ${lowerWidth + 16} a 7 7 0 0 1 0 14 h ${-(lowerWidth + 16)} z`} fill={COLORS.shoe} />
        ) : null}
        {hand ? <circle cx={0} cy={lowerLength + 4} r={7.5} fill={hand} /> : null}
      </g>
    </g>
  );
}

/** The walker, standing at `WORLD.manX` on the ground. */
export function Walker(props: WalkerProps) {
  const { bodyRef, shadowRef, legFTop, legFJoint, legBTop, legBJoint, armFTop, armFJoint, armBTop, armBJoint } = props;
  return (
    <g transform={`translate(${WORLD.manX} ${GROUND})`}>
      <ellipse ref={shadowRef} cx={0} cy={3} rx={46} ry={7} fill="#E1E7EE" />
      <g ref={bodyRef}>
        <g>
          <Limb topRef={armBTop} jointRef={armBJoint} size={ARM} color={COLORS.jacketB} hand={COLORS.skinB} />
        </g>
        <g>
          <Limb topRef={legBTop} jointRef={legBJoint} size={LEG} color={COLORS.pantsB} foot />
        </g>
        <g>
          <Limb topRef={legFTop} jointRef={legFJoint} size={LEG} color={COLORS.pants} foot />
        </g>
        <rect x={-44} y={-204} width={28} height={70} rx={9} fill={COLORS.pack} />
        <rect x={-40} y={-170} width={20} height={18} rx={4} fill={COLORS.packB} />
        <rect x={-22} y={-210} width={44} height={98} rx={18} fill={COLORS.jacket} />
        <path d="M -2 -210 L 10 -184 L 22 -206 Z" fill={COLORS.shirt} />
        <rect x={-17} y={-206} width={6} height={50} rx={3} fill={COLORS.pack} />
        <rect x={-1} y={-226} width={14} height={20} rx={5} fill={COLORS.skin} />
        <g transform="translate(6 -246)">
          <circle cx={0} cy={0} r={23} fill={COLORS.skin} />
          <path d="M 20 -2 q 8 4 2 10" fill={COLORS.skin} stroke={COLORS.skin} strokeWidth={4} />
          <path
            d="M -23 2 C -26 -22 -6 -32 10 -27 C 20 -24 25 -16 24 -10 C 14 -16 2 -14 -6 -8 C -10 -2 -12 6 -18 12 C -22 10 -23 6 -23 2 Z"
            fill={COLORS.hair}
          />
          <circle cx={-8} cy={3} r={5} fill={COLORS.skinB} />
          <circle cx={13} cy={-2} r={2.6} fill="#1A1A1A" />
          <path d="M 10 11 q 6 3 11 -1" fill="none" stroke="#7A4A33" strokeWidth={2} strokeLinecap="round" />
        </g>
        <g>
          <Limb topRef={armFTop} jointRef={armFJoint} size={ARM} color={COLORS.jacket} hand={COLORS.skin} />
        </g>
      </g>
    </g>
  );
}

/** Poses the walker for a phase of his stride and a walk amount (0 standing, 1 in full stride). */
export function poseWalker(walker: WalkerRefs, phase: number, walk: number) {
  const cosPhase = Math.cos(phase);
  const hipY = -118 - walk * 3 * Math.abs(cosPhase);
  const thigh = (swing: number) => -26 * walk * swing;
  const knee = (swing: number) => walk * (8 + 34 * Math.max(0, swing));
  /** `restTilt`: the leg's angle when the walker stands still. */
  const setLeg = (leg: LimbRefs, legPhase: number, restTilt: number) => {
    const swing = Math.sin(legPhase);
    const kneeSwing = Math.sin(legPhase + 1.9);
    leg.top.current?.setAttribute("transform", `translate(0 ${hipY}) rotate(${thigh(swing) + (walk ? 0 : restTilt)})`);
    leg.joint.current?.setAttribute("transform", `translate(0 60) rotate(${knee(kneeSwing)})`);
  };
  setLeg(walker.legs.front, phase, -3);
  setLeg(walker.legs.back, phase + Math.PI, 3);
  const setArm = (arm: LimbRefs, armPhase: number, base: number) => {
    const swing = Math.sin(armPhase);
    arm.top.current?.setAttribute("transform", `translate(2 ${hipY - 82}) rotate(${base + 22 * walk * swing})`);
    arm.joint.current?.setAttribute("transform", `translate(0 46) rotate(${-14 - walk * 16 * Math.max(0, swing)})`);
  };
  setArm(walker.arms.front, phase + Math.PI, -4);
  setArm(walker.arms.back, phase, 6);
  walker.body.current?.setAttribute("transform", `translate(0 ${-118 - hipY})`);
  walker.shadow.current?.setAttribute("rx", String(44 + walk * 6 * Math.abs(Math.sin(phase))));
}
