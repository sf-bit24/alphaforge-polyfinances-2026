"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { cn } from "@/components/ui/cn";
import s from "./dashboard.module.css";
import { startFlock, type Flock } from "./flock";

export interface IntroChip {
  key: string;
  label: string;
  tone?: "trap" | "ok";
}

/** Length of the send animation (message rises, birds dive, scene folds), as in the draft. */
const FOLD_MS = 1100;
const DONE_MS = 1550;

const WINDOWS: Array<[number, number]> = [
  [574, 276], [598, 276], [574, 306], [598, 306],
  [648, 242], [672, 242], [648, 272], [672, 272], [648, 302], [672, 302],
  [714, 286], [738, 286], [714, 316], [738, 316],
];

/**
 * The assistant's first screen: the draft's landscape with the man and the flock, the
 * prompt and suggested questions. Sending folds the scene into the conversation.
 */
export function IntroScene({
  heading,
  lead,
  placeholder,
  sendLabel,
  hint,
  chips,
  disabled,
  onDone,
}: {
  heading: string;
  lead: string;
  placeholder: string;
  sendLabel: string;
  hint: string;
  chips: IntroChip[];
  disabled: boolean;
  /** Called once the scene has folded away, with what the investor sent. */
  onDone: (text: string, chip: string | null) => void;
}) {
  const sceneRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const flipRef = useRef<SVGGElement>(null);
  const thoughtRef = useRef<HTMLDivElement>(null);
  const flock = useRef<Flock | null>(null);
  const timers = useRef<number[]>([]);
  const [text, setText] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    const scene = sceneRef.current;
    const canvas = canvasRef.current;
    const input = inputRef.current;
    const form = formRef.current;
    const flip = flipRef.current;
    const thought = thoughtRef.current;
    if (!scene || !canvas || !input || !form || !flip || !thought) return;
    flock.current = startFlock({ scene, canvas, input, form, flip, thought });
    const pending = timers.current;
    return () => {
      flock.current?.stop();
      flock.current = null;
      pending.forEach((id) => window.clearTimeout(id));
    };
  }, []);

  const go = (value: string, chip: string | null) => {
    if (sent !== null || disabled || !value) return;
    setSent(value);
    setText("");
    flock.current?.gulp();
    timers.current.push(window.setTimeout(() => setLeaving(true), FOLD_MS));
    timers.current.push(window.setTimeout(() => onDone(value, chip), DONE_MS));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    go(text.trim(), null);
  };

  return (
    <div className={s.sceneWrap}>
      <div ref={sceneRef} className={cn(s.scene, leaving && s.leaving)}>
        <svg className={s.land} viewBox="0 0 900 470" preserveAspectRatio="xMidYMax meet" aria-hidden focusable="false">
          <path d="M0 330 C 120 270, 220 300, 330 280 S 560 250, 680 290 S 840 270, 900 285 L 900 400 L 0 400 Z" fill="#EDF1F6" />
          <g fill="#DCE4EE">
            <rect x="560" y="260" width="70" height="140" />
            <rect x="636" y="225" width="58" height="175" />
            <rect x="700" y="270" width="80" height="130" />
          </g>
          <g fill="#fff">
            {WINDOWS.map(([x, y]) => (
              <rect key={`${x}-${y}`} x={x} y={y} width="10" height="14" />
            ))}
          </g>
          <g>
            <rect x="822" y="330" width="10" height="70" fill="#C3CFDC" />
            <circle cx="827" cy="312" r="40" fill="#D5DFEA" />
            <rect x="40" y="340" width="9" height="60" fill="#C3CFDC" />
            <circle cx="44" cy="322" r="34" fill="#D5DFEA" />
          </g>
          <rect x="0" y="398" width="900" height="72" fill="#F5F7FA" />
          <rect x="0" y="396" width="900" height="24" fill="#E6EBF1" />
          <g fill="#fff">
            {Array.from({ length: 13 }, (_, index) => (
              <rect key={index} x={20 + index * 70} y="406" width="30" height="3" rx="1.5" />
            ))}
          </g>
          {/* The man, standing; he turns to face the pointer. */}
          <g transform="translate(118 398) scale(.8)">
            <g ref={flipRef}>
              <ellipse cx="0" cy="3" rx="44" ry="7" fill="#E1E7EE" />
              <rect x="-16" y="-124" width="22" height="122" rx="11" fill="#2E3D50" />
              <rect x="-16" y="-12" width="36" height="13" rx="6.5" fill="#1A1A1A" />
              <rect x="-2" y="-124" width="22" height="122" rx="11" fill="#3A4B60" />
              <rect x="-2" y="-12" width="36" height="13" rx="6.5" fill="#1A1A1A" />
              <rect x="-44" y="-204" width="28" height="70" rx="9" fill="#E41C23" />
              <rect x="-40" y="-170" width="20" height="18" rx="4" fill="#B8141A" />
              <rect x="-22" y="-210" width="44" height="98" rx="18" fill="#0B2341" />
              <path d="M -2 -210 L 10 -184 L 22 -206 Z" fill="#fff" />
              <rect x="-17" y="-206" width="6" height="50" rx="3" fill="#E41C23" />
              <rect x="-6" y="-202" width="16" height="90" rx="8" fill="#0B2341" transform="rotate(-6 2 -200)" />
              <circle cx="12" cy="-110" r="7.5" fill="#C98E6B" />
              <rect x="-1" y="-226" width="14" height="20" rx="5" fill="#C98E6B" />
              <g transform="translate(6 -246)">
                <circle r="23" fill="#C98E6B" />
                <path d="M 20 -2 q 8 4 2 10" fill="#C98E6B" stroke="#C98E6B" strokeWidth="4" />
                <path
                  d="M -23 2 C -26 -22 -6 -32 10 -27 C 20 -24 25 -16 24 -10 C 14 -16 2 -14 -6 -8 C -10 -2 -12 6 -18 12 C -22 10 -23 6 -23 2 Z"
                  fill="#2B2321"
                />
                <circle cx="-8" cy="3" r="5" fill="#B57B59" />
                <circle cx="13" cy="-2" r="2.6" fill="#1A1A1A" />
                <path d="M 10 11 q 6 3 11 -1" fill="none" stroke="#7A4A33" strokeWidth="2" strokeLinecap="round" />
              </g>
            </g>
          </g>
        </svg>
        <canvas ref={canvasRef} className={s.birds} aria-hidden />
        <div ref={thoughtRef} className={cn(s.thought, text && s.thoughtOn)} aria-hidden>
          …
        </div>
        <div className={s.sceneUi}>
          <h1 id="assistant-intro">{heading}</h1>
          <p className={s.lead}>{lead}</p>
          <form ref={formRef} className={s.sform} onSubmit={submit} autoComplete="off">
            <input
              ref={inputRef}
              className={s.input}
              value={text}
              onChange={(event) => {
                setText(event.target.value);
                flock.current?.typed();
              }}
              placeholder={placeholder}
              aria-labelledby="assistant-intro"
              maxLength={4000}
              disabled={sent !== null}
            />
            <button className={s.ssend} type="submit" aria-label={sendLabel} disabled={!text.trim() || disabled || sent !== null}>
              <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
                <path d="M9 15V3.5M4.5 8L9 3.5 13.5 8" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <div className={cn(s.floatmsg, sent !== null && s.go)} aria-live="polite">
              {sent}
            </div>
          </form>
          {chips.length > 0 ? (
            <div className={s.schips}>
              {chips.map((chip) => (
                <button
                  key={chip.key}
                  type="button"
                  className={cn(s.chip, chip.tone === "trap" && s.chipTrap, chip.tone === "ok" && s.chipOk)}
                  onClick={() => go(chip.label, chip.key)}
                  disabled={disabled || sent !== null}
                >
                  {chip.label}
                </button>
              ))}
            </div>
          ) : null}
          <p className={s.shint}>{hint}</p>
        </div>
      </div>
    </div>
  );
}
