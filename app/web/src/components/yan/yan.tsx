import { cn } from "@/components/ui/cn";
import styles from "./yan.module.css";

/**
 * Yan, the personal assistant: a small accountant robot. Its screen face wears the
 * accountant's eyeshade (the red visor), its antenna lights up, and in full figure its
 * body is a calculator whose display draws a little return curve. Drawn in the brand's
 * navy and red, so it reads on white as on the soft backgrounds.
 */
const NAVY = "#0B2341";
const RED = "#E41C23";
const SCREEN = "#EAF1F8";
const KEY = "#DCE4EE";

/** The head alone, in the coordinates of a 48 × 48 box. */
function Head() {
  return (
    <>
      <path d="M24 10.5V6" stroke={NAVY} strokeWidth={2.4} strokeLinecap="round" />
      <circle className={styles.light} cx={24} cy={4.6} r={3} fill={RED} />
      <rect x={3.5} y={21} width={5} height={11} rx={2.5} fill={NAVY} />
      <rect x={39.5} y={21} width={5} height={11} rx={2.5} fill={NAVY} />
      <rect x={7} y={10} width={34} height={32} rx={10} fill={NAVY} />
      <rect x={11} y={18} width={26} height={19} rx={6} fill={SCREEN} />
      <g className={styles.eyes}>
        <circle cx={18.5} cy={26.2} r={2.6} fill={NAVY} />
        <circle cx={29.5} cy={26.2} r={2.6} fill={NAVY} />
      </g>
      <path d="M20.5 31.2Q24 33.9 27.5 31.2" stroke={NAVY} strokeWidth={1.9} fill="none" strokeLinecap="round" />
      <path d="M6 18.6C12 12.6 36 12.6 42 18.6L44.5 21.6C34 17.6 14 17.6 3.5 21.6Z" fill={RED} />
    </>
  );
}

/** Yan's head, as the avatar of its messages. Decorative: the name is always written beside it. */
export function YanMark({ size = 34, className }: { size?: number; className?: string }) {
  return (
    <svg className={cn(styles.yan, className)} width={size} height={size} viewBox="0 0 48 48" aria-hidden focusable="false">
      <Head />
    </svg>
  );
}

const KEYS = [0, 1, 2].flatMap((row) => [0, 1, 2, 3].map((col) => ({ row, col })));

/** The calculator body: the display with its curve, and the keypad (« = » in red). */
function Body() {
  return (
    <>
      <rect x={54} y={70} width={12} height={7} rx={2} fill={NAVY} />
      <rect x={28} y={75} width={64} height={58} rx={11} fill="#fff" stroke={NAVY} strokeWidth={3.5} />
      <rect x={36} y={83} width={48} height={15} rx={3.5} fill={NAVY} />
      <path className={styles.curve} d="M40 94L47 90L53 92L60 87L67 88.5L79 85" stroke="#fff" strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      {KEYS.map(({ row, col }) => (
        <rect key={`${row}-${col}`} x={37 + col * 12} y={103 + row * 9} width={9} height={6} rx={1.8} fill={row === 2 && col === 3 ? RED : KEY} />
      ))}
      <rect x={40} y={132} width={14} height={7} rx={3.5} fill={NAVY} />
      <rect x={66} y={132} width={14} height={7} rx={3.5} fill={NAVY} />
    </>
  );
}

/** The arms: one at rest, the other raised with a red pencil (it waves on arrival). */
function Arms() {
  return (
    <>
      <path d="M29 93Q19 98 16 107" stroke={NAVY} strokeWidth={5} fill="none" strokeLinecap="round" />
      <circle cx={15.5} cy={108.5} r={4.2} fill={NAVY} />
      <g className={styles.wave}>
        <path d="M91 92Q101 87 104 77" stroke={NAVY} strokeWidth={5} fill="none" strokeLinecap="round" />
        <path d="M103.5 76L111.5 60.5" stroke={RED} strokeWidth={4.2} strokeLinecap="round" />
        <path d="M111.5 60.5L113.6 55.6L109.6 58.6Z" fill={NAVY} />
        <circle cx={104.5} cy={75.5} r={4.2} fill={NAVY} />
      </g>
    </>
  );
}

/** Yan in full, where it introduces itself (the opening of its conversation). */
export function YanFigure({ height = 128, className }: { height?: number; className?: string }) {
  return (
    <svg className={cn(styles.yan, styles.figure, className)} height={height} viewBox="0 0 120 144" aria-hidden focusable="false">
      <ellipse cx={60} cy={140} rx={30} ry={3.5} fill={KEY} />
      <Arms />
      <Body />
      <g transform="translate(19.2 0) scale(1.7)">
        <Head />
      </g>
    </svg>
  );
}
