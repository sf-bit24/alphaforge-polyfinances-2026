"use client";

import { useEffect, useMemo, useState } from "react";
import { formatPercent, formatSignedPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import {
  CHART_RANGES,
  GROUPS,
  SAMPLE_FACTS,
  VOL_WINDOWS,
  chartPoints,
  groupWeight,
  tr,
  windowVol,
  type ChartRange,
  type SamplePortfolio,
  type VolWindow,
} from "@/lib/sample/portfolio";
import { NAVY, RED, formatDay } from "./chart-base";
import styles from "./details.module.css";
import { MonthColumns, MonthReading, MonthStats, MonthsTable, monthHandlers, shortMonth } from "./monthly-bars-parts";
import { VsLegend, VsLines, VsOverlay, VsTable, XLabels, crosshairHandlers, leadOver, vsGeometry } from "./vs-chart-parts";

export { formatDay } from "./chart-base";

/** True two frames after mount, so the draft's entrance transitions start from their initial state. */
function useGrown(): boolean {
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    let inner = 0;
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => setGrown(true));
    });
    return () => {
      cancelAnimationFrame(outer);
      cancelAnimationFrame(inner);
    };
  }, []);
  return grown;
}

/** A radio group of the draft's pills (period choices). */
export function Pills<T extends string>({ options, value, onChange, label }: { options: Array<{ value: T; label: string }>; value: T; onChange: (value: T) => void; label: string }) {
  return (
    <div className={styles.pills} role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button key={option.value} type="button" role="radio" aria-checked={option.value === value} onClick={() => onChange(option.value)}>
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** Columns show their size by their opacity; while one is read, the others dim. */
function stripOpacity(active: number | null, index: number, size: number): number {
  if (active === null) return 0.35 + size * 0.65;
  return active === index ? 1 : 0.25;
}

/** The last 21 daily returns: navy up, red down, opacity by size; each column is a hit target. */
export function DailyStrip({ sample }: { sample: SamplePortfolio }) {
  const { t, locale } = useI18n();
  const grown = useGrown();
  const [active, setActive] = useState<number | null>(null);
  const daily = sample.returns.slice(-21);
  const days = sample.dates.slice(-21);
  const max = Math.max(...daily.map(Math.abs), 1e-9);
  const current = active === null ? null : { day: days[active] ?? 0, value: daily[active] ?? 0 };
  return (
    <>
      <div
        className={styles.strip}
        onPointerLeave={() => setActive(null)}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setActive(null);
        }}
      >
        {daily.map((value, index) => {
          const size = Math.abs(value) / max;
          return (
            <button
              key={days[index]}
              type="button"
              className={styles.stripCol}
              aria-label={`${formatDay(days[index] ?? 0, locale)} : ${formatSignedPercent(value, locale, 2)}`}
              onPointerEnter={() => setActive(index)}
              onFocus={() => setActive(index)}
            >
              <span
                style={{
                  height: grown ? `${18 + size * 82}%` : "6%",
                  background: value >= 0 ? NAVY : RED,
                  opacity: stripOpacity(active, index, size),
                  transitionDelay: grown && active === null ? `${index * 18}ms` : "0ms",
                }}
              />
            </button>
          );
        })}
      </div>
      <div className={styles.stripFoot}>
        <span>{formatDay(days[0] ?? 0, locale)}</span>
        <b aria-live="polite">{current ? `${formatDay(current.day, locale)} · ${formatSignedPercent(current.value, locale, 2)}` : t.details.hero.daily}</b>
        <span>{t.details.today}</span>
      </div>
    </>
  );
}

/** Half-circle gauge of the annualized volatility (0 to 10 %), with the profile's 7 % cap as a red tick. */
export function VolGauge({ sample }: { sample: SamplePortfolio }) {
  const { t, locale } = useI18n();
  const grown = useGrown();
  const [span, setSpan] = useState<VolWindow>("5y");
  const radius = 62;
  const arc = Math.PI * radius;
  const fullScale = 0.1;
  const vol = windowVol(sample, span);
  const share = Math.min(1, vol / fullScale);
  const capShare = SAMPLE_FACTS.volCap / fullScale;
  const angle = Math.PI * (1 - capShare);
  const capTick = [75 + radius * Math.cos(angle), 78 - radius * Math.sin(angle), 75 + (radius + 9) * Math.cos(angle), 78 - (radius + 9) * Math.sin(angle)];
  const windows = Object.keys(VOL_WINDOWS) as VolWindow[];
  return (
    <>
      <svg className={styles.gauge} width="160" height="92" viewBox="0 0 150 86" aria-hidden focusable="false">
        <path d="M 13 78 A 62 62 0 0 1 137 78" fill="none" stroke="#EEF2F6" strokeWidth="10" strokeLinecap="round" />
        <path
          className={styles.gaugeArc}
          d="M 13 78 A 62 62 0 0 1 137 78"
          fill="none"
          stroke={NAVY}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={arc}
          strokeDashoffset={grown ? arc * (1 - share) : arc}
        />
        <line x1={capTick[0]} y1={capTick[1]} x2={capTick[2]} y2={capTick[3]} stroke={RED} strokeWidth="2.5" strokeLinecap="round" />
        <g className={styles.gaugeNeedle} style={{ transform: `rotate(${grown ? -90 + share * 180 : -90}deg)` }}>
          <line x1="75" y1="78" x2="75" y2="30" stroke={NAVY} strokeWidth="2.5" strokeLinecap="round" />
        </g>
        <circle cx="75" cy="78" r="5" fill={NAVY} />
      </svg>
      <p className={styles.gaugeVal}>
        {formatPercent(vol, locale, 1).replace(/\s?%$/, "")} <small>%</small>
      </p>
      <p className={styles.gaugeCap}>{t.details.vol.cap(formatPercent(SAMPLE_FACTS.volCap, locale))}</p>
      <Pills
        label={t.details.periodLabel}
        value={span}
        onChange={setSpan}
        options={windows.map((value) => ({ value, label: t.details.periods[value] }))}
      />
    </>
  );
}

/** The portfolio against XIU.TO alone, on one axis; the crosshair snaps to the nearest date (pointer or arrow keys). */
export function VsChart({ sample }: { sample: SamplePortfolio }) {
  const { t } = useI18n();
  const [range, setRange] = useState<ChartRange>("1y");
  const [hover, setHover] = useState<number | null>(null);
  const points = useMemo(() => chartPoints(sample, range), [sample, range]);
  const geometry = vsGeometry(points);
  const last = points.length - 1;
  const focusIndex = hover ?? last;
  const ranges = Object.keys(CHART_RANGES) as ChartRange[];
  const { handleMove, handleKey } = crosshairHandlers(last, setHover);
  const changeRange = (next: ChartRange) => {
    setRange(next);
    setHover(null);
  };

  return (
    <>
      <header>
        <h2 id="vs-title">{t.details.chart.title}</h2>
        <Pills label={t.details.chart.periodLabel} value={range} onChange={changeRange} options={ranges.map((value) => ({ value, label: t.details.periods[value] }))} />
      </header>
      <VsLegend focused={points[focusIndex]} lead={leadOver(points)} hover={hover} />
      <div
        className={styles.plot}
        tabIndex={0}
        role="group"
        aria-labelledby="vs-title"
        aria-describedby="vs-help"
        onPointerMove={handleMove}
        onPointerLeave={() => setHover(null)}
        onKeyDown={handleKey}
        onBlur={() => setHover(null)}
      >
        <VsLines geometry={geometry} range={range} />
        <VsOverlay geometry={geometry} hover={hover} focusIndex={focusIndex} />
      </div>
      <p id="vs-help" className="sr-only">
        {t.details.chart.keyboard}
      </p>
      <XLabels points={points} range={range} />
      <VsTable points={points} range={range} />
    </>
  );
}

/** Tall segmented bar of the five pockets, with its legend (names and weights stay visible). */
export function AllocationBar() {
  const { locale } = useI18n();
  const grown = useGrown();
  const [highlight, setHighlight] = useState<number | null>(null);
  return (
    <>
      <div className={styles.seg} aria-hidden>
        {GROUPS.map((group, index) => (
          <span
            key={group.key}
            onPointerEnter={() => setHighlight(index)}
            onPointerLeave={() => setHighlight(null)}
            style={{
              flexBasis: grown ? `${groupWeight(group)}%` : "20%",
              background: group.color,
              opacity: highlight === null || highlight === index ? 1 : 0.3,
              transitionDelay: grown && highlight === null ? `${200 + index * 60}ms` : "0ms",
            }}
          />
        ))}
      </div>
      <ul className={styles.segList}>
        {GROUPS.map((group, index) => (
          <li key={group.key} onPointerEnter={() => setHighlight(index)} onPointerLeave={() => setHighlight(null)}>
            <span>
              <i style={{ background: group.color }} aria-hidden />
              {tr(group.name, locale)}
            </span>
            <em>{formatPercent(groupWeight(group) / 100, locale)}</em>
          </li>
        ))}
      </ul>
    </>
  );
}

/** The 2022 fall on a 0 to −20 % range, with the profile's tolerable zone hatched. */
export function StressRange({ drop }: { drop: number }) {
  const { t, locale } = useI18n();
  const grown = useGrown();
  const scale = Math.abs(SAMPLE_FACTS.stressScale);
  const limit = Math.abs(SAMPLE_FACTS.stressLimit);
  return (
    <>
      <div className={styles.range} role="img" aria-label={t.details.stress.aria(formatPercent(Math.abs(drop), locale, 1), formatPercent(limit, locale))}>
        <div className={styles.track} />
        <div className={styles.zone} style={{ left: 0, width: `${(limit / scale) * 100}%` }} />
        <div className={styles.mark} style={{ left: grown ? `${(Math.abs(drop) / scale) * 100}%` : "0%" }} />
      </div>
      <div className={styles.rangeL} aria-hidden>
        <span style={{ left: 0 }}>{formatPercent(0, locale)}</span>
        <span style={{ left: `${(limit / scale) * 100}%`, transform: "translateX(-50%)" }}>{t.details.stress.limitLabel(formatSignedPercent(-limit, locale, 0))}</span>
        <span style={{ right: 0 }}>{formatSignedPercent(-scale, locale, 0)}</span>
      </div>
    </>
  );
}

/** Sixty monthly returns around a zero line; the pointer (or the arrow keys) reads the nearest month. */
export function MonthlyBars({ sample }: { sample: SamplePortfolio }) {
  const { t, locale } = useI18n();
  const grown = useGrown();
  const [active, setActive] = useState<number | null>(null);
  const months = sample.months;
  const { handleMove, handleKey } = monthHandlers(months.length, setActive);
  const first = months[0];
  const lastMonth = months[months.length - 1];
  return (
    <>
      <header>
        <h2 id="months-title">{t.details.months.title}</h2>
        <span className={styles.cap} style={{ margin: 0 }}>
          {first && lastMonth ? t.details.months.span(shortMonth(first.at, locale), shortMonth(lastMonth.at, locale)) : null}
        </span>
      </header>
      <div className={styles.mTop}>
        <MonthReading shown={months[active ?? months.length - 1]} active={active} />
        <p className={styles.cap} style={{ margin: 0 }}>
          {t.details.months.hint(months.length)}
        </p>
      </div>
      <div
        className={styles.mbars}
        tabIndex={0}
        role="group"
        aria-labelledby="months-title"
        aria-describedby="months-help"
        onPointerMove={handleMove}
        onPointerLeave={() => setActive(null)}
        onKeyDown={handleKey}
        onBlur={() => setActive(null)}
      >
        <MonthColumns months={months} grown={grown} active={active} />
      </div>
      <p id="months-help" className="sr-only">
        {t.details.months.keyboard}
      </p>
      <MonthStats months={months} />
      <MonthsTable months={months} />
    </>
  );
}
