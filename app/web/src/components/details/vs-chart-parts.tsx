"use client";

import type { Dispatch, KeyboardEvent, PointerEvent, SetStateAction } from "react";
import { formatCompactMoney, formatMoney, formatSignedPoints } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import type { ChartPoint, ChartRange } from "@/lib/sample/portfolio";
import { niceTicks } from "@/lib/chart/ticks";
import { cn } from "@/components/ui/cn";
import { NAVY, SLATE, formatDay } from "./chart-base";
import styles from "./details.module.css";

/** Size of the comparison chart's drawing; the SVG stretches to its box. */
const PLOT_WIDTH = 640;
const PLOT_HEIGHT = 240;

type PlotPoint = [number, number];

/** A smooth path through the points: each segment is a cubic curve with its control points halfway, at the heights of its ends. */
const smooth = (points: PlotPoint[]) =>
  points
    .map(([x, y], index) => {
      if (index === 0) return `M ${x.toFixed(1)} ${y.toFixed(1)}`;
      const [previousX, previousY] = points[index - 1] ?? [x, y];
      const mid = (previousX + x) / 2;
      return `C ${mid.toFixed(1)} ${previousY.toFixed(1)}, ${mid.toFixed(1)} ${y.toFixed(1)}, ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

export interface VsGeometry {
  /** Height of a value in the drawing; both series share the axis. */
  y: (value: number) => number;
  portfolioPoints: PlotPoint[];
  benchmarkPoints: PlotPoint[];
  portfolioLine: string;
  benchmarkLine: string;
  /** Round values of the axis, without those too close to the top for their label. */
  ticks: number[];
}

/** Both series on one axis, from the lowest value of either to the highest. */
export function vsGeometry(points: ChartPoint[]): VsGeometry {
  const values = points.flatMap((point) => [point.portfolio, point.benchmark]);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const y = (value: number) => PLOT_HEIGHT - 16 - ((value - low) / (high - low || 1)) * (PLOT_HEIGHT - 40);
  const last = points.length - 1;
  const portfolioPoints = points.map((point, index): PlotPoint => [(index / Math.max(1, last)) * PLOT_WIDTH, y(point.portfolio)]);
  const benchmarkPoints = points.map((point, index): PlotPoint => [(index / Math.max(1, last)) * PLOT_WIDTH, y(point.benchmark)]);
  return {
    y,
    portfolioPoints,
    benchmarkPoints,
    portfolioLine: smooth(portfolioPoints),
    benchmarkLine: smooth(benchmarkPoints),
    ticks: niceTicks(low, high).filter((tick) => y(tick) > 14),
  };
}

/** The portfolio's return over the window minus XIU.TO's. A difference of two returns: percentage points, not a percent. */
export function leadOver(points: ChartPoint[]): number {
  const first = points[0];
  const end = points[points.length - 1];
  return first && end ? end.portfolio / first.portfolio - 1 - (end.benchmark / first.benchmark - 1) : 0;
}

/** Where a point of the drawing falls in the stretched box, in percent. */
const plotPosition = (pair: PlotPoint | undefined) => (pair ? { left: `${(pair[0] / PLOT_WIDTH) * 100}%`, top: `${(pair[1] / PLOT_HEIGHT) * 100}%` } : {});

/** The pointer snaps to the nearest date; the arrow keys move by one date (five with Shift), Home and End jump, Escape lets go. */
export function crosshairHandlers(last: number, setHover: Dispatch<SetStateAction<number | null>>) {
  return {
    handleMove: (event: PointerEvent<HTMLDivElement>) => {
      const box = event.currentTarget.getBoundingClientRect();
      setHover(Math.max(0, Math.min(last, Math.round(((event.clientX - box.left) / box.width) * last))));
    },
    handleKey: (event: KeyboardEvent<HTMLDivElement>) => {
      const step = event.shiftKey ? 5 : 1;
      if (event.key === "ArrowLeft") setHover((current) => Math.max(0, (current ?? last) - step));
      else if (event.key === "ArrowRight") setHover((current) => Math.min(last, (current ?? last) + step));
      else if (event.key === "Home") setHover(0);
      else if (event.key === "End") setHover(last);
      else if (event.key === "Escape") setHover(null);
      else return;
      event.preventDefault();
    },
  };
}

/** Values on the focused date, the portfolio's lead over the window, and the date. */
export function VsLegend({ focused, lead, hover }: { focused: ChartPoint | undefined; lead: number; hover: number | null }) {
  const { t, locale } = useI18n();
  return (
    <div className={styles.legend} aria-live="polite">
      <div>
        <p>
          <span className={styles.keyLine} />
          {t.details.chart.portfolio}
        </p>
        <p className={styles.v}>{focused ? formatMoney(focused.portfolio, locale) : "—"}</p>
      </div>
      <div>
        <p>
          <span className={styles.keyDash} />
          {t.details.chart.benchmark}
        </p>
        <p className={cn(styles.v, styles.vMuted)}>{focused ? formatMoney(focused.benchmark, locale) : "—"}</p>
      </div>
      <div className={styles.legendEnd}>
        <span className={cn(styles.chip, styles.navy)}>{t.details.chart.lead(formatSignedPoints(lead, locale))}</span>
        <span className={styles.when}>{hover === null || !focused ? t.details.today : formatDay(focused.at, locale, { day: "numeric", month: "short", year: "numeric" })}</span>
      </div>
    </div>
  );
}

/** The drawing: gridlines, the area under the portfolio, XIU.TO dashed, the portfolio line (redrawn when the window changes). */
export function VsLines({ geometry, range }: { geometry: VsGeometry; range: ChartRange }) {
  const { y, ticks, portfolioLine, benchmarkLine } = geometry;
  return (
    <svg viewBox={`0 0 ${PLOT_WIDTH} ${PLOT_HEIGHT}`} preserveAspectRatio="none" aria-hidden focusable="false">
      <defs>
        <linearGradient id="vs-area" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={NAVY} stopOpacity=".16" />
          <stop offset="1" stopColor={NAVY} stopOpacity="0" />
        </linearGradient>
      </defs>
      {ticks.map((tick) => (
        <line key={tick} x1="0" x2={PLOT_WIDTH} y1={y(tick)} y2={y(tick)} stroke="#EEF2F6" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      ))}
      <path d={`${portfolioLine} L ${PLOT_WIDTH} ${PLOT_HEIGHT} L 0 ${PLOT_HEIGHT} Z`} fill="url(#vs-area)" />
      <path d={benchmarkLine} fill="none" stroke={SLATE} strokeWidth="1.5" strokeDasharray="4 5" vectorEffect="non-scaling-stroke" />
      <path key={range} className={styles.line} d={portfolioLine} fill="none" stroke={NAVY} strokeWidth="2.5" strokeLinecap="round" vectorEffect="non-scaling-stroke" pathLength={1} />
    </svg>
  );
}

/** Over the drawing: the axis labels, and the crosshair with its dots on the focused date. */
export function VsOverlay({ geometry, hover, focusIndex }: { geometry: VsGeometry; hover: number | null; focusIndex: number }) {
  const { locale } = useI18n();
  const { y, ticks, portfolioPoints, benchmarkPoints } = geometry;
  return (
    <>
      {ticks.map((tick) => (
        <span key={tick} className={styles.ytick} style={{ top: `${(y(tick) / PLOT_HEIGHT) * 100}%` }} aria-hidden>
          {formatCompactMoney(tick, locale)}
        </span>
      ))}
      {hover !== null ? <span className={styles.xh} style={{ left: plotPosition(portfolioPoints[focusIndex]).left }} /> : null}
      {hover !== null ? <span className={cn(styles.dot, styles.dotB)} style={plotPosition(benchmarkPoints[focusIndex])} /> : null}
      <span className={cn(styles.dot, styles.dotA)} style={plotPosition(portfolioPoints[focusIndex])} />
    </>
  );
}

/** Five dates under the chart, the last one "today"; months and years on the five-year window. */
export function XLabels({ points, range }: { points: ChartPoint[]; range: ChartRange }) {
  const { t, locale } = useI18n();
  const last = points.length - 1;
  const longRange = range === "5y";
  const labelOf = (when: number) => formatDay(when, locale, longRange ? { month: "short", year: "numeric" } : { day: "numeric", month: "short" });
  const dateLabel = (point: ChartPoint | undefined) => (point ? labelOf(point.at) : "");
  return (
    <div className={styles.xlabels} aria-hidden>
      {Array.from({ length: 5 }, (_, label) => {
        const point = points[Math.round((label / 4) * last)];
        return <span key={label}>{label === 4 ? t.details.today : dateLabel(point)}</span>;
      })}
    </div>
  );
}

/** The chart's values, for screen readers. */
export function VsTable({ points, range }: { points: ChartPoint[]; range: ChartRange }) {
  const { t, locale } = useI18n();
  return (
    <table className="sr-only">
      <caption>{t.details.chart.tableCaption(t.details.periods[range])}</caption>
      <thead>
        <tr>
          <th scope="col">{t.details.date}</th>
          <th scope="col">{t.details.chart.portfolio}</th>
          <th scope="col">{t.details.chart.benchmark}</th>
        </tr>
      </thead>
      <tbody>
        {points.map((point) => (
          <tr key={point.at}>
            <th scope="row">{formatDay(point.at, locale, { day: "numeric", month: "short", year: "numeric" })}</th>
            <td>{formatMoney(point.portfolio, locale)}</td>
            <td>{formatMoney(point.benchmark, locale)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
