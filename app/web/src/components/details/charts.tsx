"use client";

import { useEffect, useMemo, useState, type KeyboardEvent, type PointerEvent } from "react";
import type { Locale } from "@/lib/contract/schemas";
import { formatCompactMoney, formatMoney, formatPercent, formatSignedPercent, formatSignedPoints } from "@/lib/i18n/locale";
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
import { niceTicks } from "@/lib/chart/ticks";
import { cn } from "@/components/ui/cn";
import s from "./details.module.css";

const NAVY = "#0B2341";
const RED = "#E41C23";
const SLATE = "#8D9BAD";

/** Dates of the sample are UTC midnights. */
export function formatDay(at: number, locale: Locale, options: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" }): string {
  return new Intl.DateTimeFormat(locale === "fr" ? "fr-CA" : "en-CA", { timeZone: "UTC", ...options }).format(new Date(at));
}

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
    <div className={s.pills} role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button key={option.value} type="button" role="radio" aria-checked={option.value === value} onClick={() => onChange(option.value)}>
          {option.label}
        </button>
      ))}
    </div>
  );
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
        className={s.strip}
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
              className={s.stripCol}
              aria-label={`${formatDay(days[index] ?? 0, locale)} : ${formatSignedPercent(value, locale, 2)}`}
              onPointerEnter={() => setActive(index)}
              onFocus={() => setActive(index)}
            >
              <span
                style={{
                  height: grown ? `${18 + size * 82}%` : "6%",
                  background: value >= 0 ? NAVY : RED,
                  opacity: active === null ? 0.35 + size * 0.65 : active === index ? 1 : 0.25,
                  transitionDelay: grown && active === null ? `${index * 18}ms` : "0ms",
                }}
              />
            </button>
          );
        })}
      </div>
      <div className={s.stripFoot}>
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
  const R = 62;
  const C = Math.PI * R;
  const MAX = 0.1;
  const vol = windowVol(sample, span);
  const share = Math.min(1, vol / MAX);
  const capShare = SAMPLE_FACTS.volCap / MAX;
  const angle = Math.PI * (1 - capShare);
  const tick = [75 + R * Math.cos(angle), 78 - R * Math.sin(angle), 75 + (R + 9) * Math.cos(angle), 78 - (R + 9) * Math.sin(angle)];
  const windows = Object.keys(VOL_WINDOWS) as VolWindow[];
  return (
    <>
      <svg className={s.gauge} width="160" height="92" viewBox="0 0 150 86" aria-hidden focusable="false">
        <path d="M 13 78 A 62 62 0 0 1 137 78" fill="none" stroke="#EEF2F6" strokeWidth="10" strokeLinecap="round" />
        <path
          className={s.gaugeArc}
          d="M 13 78 A 62 62 0 0 1 137 78"
          fill="none"
          stroke={NAVY}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={C}
          strokeDashoffset={grown ? C * (1 - share) : C}
        />
        <line x1={tick[0]} y1={tick[1]} x2={tick[2]} y2={tick[3]} stroke={RED} strokeWidth="2.5" strokeLinecap="round" />
        <g className={s.gaugeNeedle} style={{ transform: `rotate(${grown ? -90 + share * 180 : -90}deg)` }}>
          <line x1="75" y1="78" x2="75" y2="30" stroke={NAVY} strokeWidth="2.5" strokeLinecap="round" />
        </g>
        <circle cx="75" cy="78" r="5" fill={NAVY} />
      </svg>
      <p className={s.gaugeVal}>
        {formatPercent(vol, locale, 1).replace(/\s?%$/, "")} <small>%</small>
      </p>
      <p className={s.gaugeCap}>{t.details.vol.cap(formatPercent(SAMPLE_FACTS.volCap, locale))}</p>
      <Pills
        label={t.details.periodLabel}
        value={span}
        onChange={setSpan}
        options={windows.map((value) => ({ value, label: t.details.periods[value] }))}
      />
    </>
  );
}

const smooth = (points: Array<[number, number]>) =>
  points
    .map(([x, y], index) => {
      if (index === 0) return `M ${x.toFixed(1)} ${y.toFixed(1)}`;
      const [px, py] = points[index - 1] ?? [x, y];
      const mid = (px + x) / 2;
      return `C ${mid.toFixed(1)} ${py.toFixed(1)}, ${mid.toFixed(1)} ${y.toFixed(1)}, ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

/** The portfolio against XIU.TO alone, on one axis; the crosshair snaps to the nearest date (pointer or arrow keys). */
export function VsChart({ sample }: { sample: SamplePortfolio }) {
  const { t, locale } = useI18n();
  const [range, setRange] = useState<ChartRange>("1y");
  const [hover, setHover] = useState<number | null>(null);
  const points = useMemo(() => chartPoints(sample, range), [sample, range]);
  const W = 640;
  const H = 240;
  const values = points.flatMap((point) => [point.portfolio, point.benchmark]);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const y = (value: number) => H - 16 - ((value - lo) / (hi - lo || 1)) * (H - 40);
  const last = points.length - 1;
  const pa = points.map((point, index): [number, number] => [(index / Math.max(1, last)) * W, y(point.portfolio)]);
  const pb = points.map((point, index): [number, number] => [(index / Math.max(1, last)) * W, y(point.benchmark)]);
  const lineA = smooth(pa);
  const lineB = smooth(pb);
  const index = hover ?? last;
  const at = points[index];
  const first = points[0];
  const end = points[last];
  // A difference of two returns: percentage points, not a percent.
  const lead = first && end ? end.portfolio / first.portfolio - 1 - (end.benchmark / first.benchmark - 1) : 0;
  const ticks = niceTicks(lo, hi).filter((tick) => y(tick) > 14);
  const position = (pair: [number, number] | undefined) => (pair ? { left: `${(pair[0] / W) * 100}%`, top: `${(pair[1] / H) * 100}%` } : {});
  const longRange = range === "5y";
  const labelOf = (when: number) => formatDay(when, locale, longRange ? { month: "short", year: "numeric" } : { day: "numeric", month: "short" });
  const ranges = Object.keys(CHART_RANGES) as ChartRange[];

  const onMove = (event: PointerEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    setHover(Math.max(0, Math.min(last, Math.round(((event.clientX - box.left) / box.width) * last))));
  };
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 5 : 1;
    if (event.key === "ArrowLeft") setHover((current) => Math.max(0, (current ?? last) - step));
    else if (event.key === "ArrowRight") setHover((current) => Math.min(last, (current ?? last) + step));
    else if (event.key === "Home") setHover(0);
    else if (event.key === "End") setHover(last);
    else if (event.key === "Escape") setHover(null);
    else return;
    event.preventDefault();
  };

  return (
    <>
      <header>
        <h2 id="vs-title">{t.details.chart.title}</h2>
        <Pills label={t.details.chart.periodLabel} value={range} onChange={(next) => {
            setRange(next);
            setHover(null);
          }} options={ranges.map((value) => ({ value, label: t.details.periods[value] }))} />
      </header>
      <div className={s.legend} aria-live="polite">
        <div>
          <p>
            <span className={s.keyLine} />
            {t.details.chart.portfolio}
          </p>
          <p className={s.v}>{at ? formatMoney(at.portfolio, locale) : "—"}</p>
        </div>
        <div>
          <p>
            <span className={s.keyDash} />
            {t.details.chart.benchmark}
          </p>
          <p className={cn(s.v, s.vMuted)}>{at ? formatMoney(at.benchmark, locale) : "—"}</p>
        </div>
        <div className={s.legendEnd}>
          <span className={cn(s.chip, s.navy)}>{t.details.chart.lead(formatSignedPoints(lead, locale))}</span>
          <span className={s.when}>{hover === null || !at ? t.details.today : formatDay(at.at, locale, { day: "numeric", month: "short", year: "numeric" })}</span>
        </div>
      </div>
      <div
        className={s.plot}
        tabIndex={0}
        role="group"
        aria-labelledby="vs-title"
        aria-describedby="vs-help"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
        onKeyDown={onKey}
        onBlur={() => setHover(null)}
      >
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden focusable="false">
          <defs>
            <linearGradient id="vs-area" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor={NAVY} stopOpacity=".16" />
              <stop offset="1" stopColor={NAVY} stopOpacity="0" />
            </linearGradient>
          </defs>
          {ticks.map((tick) => (
            <line key={tick} x1="0" x2={W} y1={y(tick)} y2={y(tick)} stroke="#EEF2F6" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          ))}
          <path d={`${lineA} L ${W} ${H} L 0 ${H} Z`} fill="url(#vs-area)" />
          <path d={lineB} fill="none" stroke={SLATE} strokeWidth="1.5" strokeDasharray="4 5" vectorEffect="non-scaling-stroke" />
          <path key={range} className={s.line} d={lineA} fill="none" stroke={NAVY} strokeWidth="2.5" strokeLinecap="round" vectorEffect="non-scaling-stroke" pathLength={1} />
        </svg>
        {ticks.map((tick) => (
          <span key={tick} className={s.ytick} style={{ top: `${(y(tick) / H) * 100}%` }} aria-hidden>
            {formatCompactMoney(tick, locale)}
          </span>
        ))}
        {hover !== null ? <span className={s.xh} style={{ left: position(pa[index]).left }} /> : null}
        {hover !== null ? <span className={cn(s.dot, s.dotB)} style={position(pb[index])} /> : null}
        <span className={cn(s.dot, s.dotA)} style={position(pa[index])} />
      </div>
      <p id="vs-help" className="sr-only">
        {t.details.chart.keyboard}
      </p>
      <div className={s.xlabels} aria-hidden>
        {Array.from({ length: 5 }, (_, label) => {
          const point = points[Math.round((label / 4) * last)];
          return <span key={label}>{label === 4 ? t.details.today : point ? labelOf(point.at) : ""}</span>;
        })}
      </div>
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
      <div className={s.seg} aria-hidden>
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
      <ul className={s.segList}>
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
      <div className={s.range} role="img" aria-label={t.details.stress.aria(formatPercent(Math.abs(drop), locale, 1), formatPercent(limit, locale))}>
        <div className={s.track} />
        <div className={s.zone} style={{ left: 0, width: `${(limit / scale) * 100}%` }} />
        <div className={s.mark} style={{ left: grown ? `${(Math.abs(drop) / scale) * 100}%` : "0%" }} />
      </div>
      <div className={s.rangeL} aria-hidden>
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
  const max = Math.max(...months.map((month) => Math.abs(month.value)), 1e-9);
  const shown = months[active ?? months.length - 1];
  const longDate = (at: number) => formatDay(at, locale, { month: "long", year: "numeric" });
  const shortDate = (at: number) => formatDay(at, locale, { month: "short", year: "numeric" });
  const positive = months.filter((month) => month.value >= 0).length;
  const best = months.reduce((a, b) => (b.value > a.value ? b : a), months[0] ?? { at: 0, value: 0 });
  const worst = months.reduce((a, b) => (b.value < a.value ? b : a), months[0] ?? { at: 0, value: 0 });
  const onMove = (event: PointerEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    setActive(Math.max(0, Math.min(months.length - 1, Math.floor(((event.clientX - box.left) / box.width) * months.length))));
  };
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const lastIndex = months.length - 1;
    if (event.key === "ArrowLeft") setActive((current) => Math.max(0, (current ?? lastIndex) - 1));
    else if (event.key === "ArrowRight") setActive((current) => Math.min(lastIndex, (current ?? lastIndex) + 1));
    else if (event.key === "Escape") setActive(null);
    else return;
    event.preventDefault();
  };
  const first = months[0];
  const lastMonth = months[months.length - 1];
  return (
    <>
      <header>
        <h2 id="months-title">{t.details.months.title}</h2>
        <span className={s.cap} style={{ margin: 0 }}>
          {first && lastMonth ? t.details.months.span(shortDate(first.at), shortDate(lastMonth.at)) : null}
        </span>
      </header>
      <div className={s.mTop}>
        <div aria-live="polite">
          <p className={s.big}>{shown ? formatSignedPercent(shown.value, locale) : "—"}</p>
          <p className={s.cap}>{shown ? (active === null ? t.details.months.lastMonth(longDate(shown.at)) : longDate(shown.at)) : null}</p>
        </div>
        <p className={s.cap} style={{ margin: 0 }}>
          {t.details.months.hint(months.length)}
        </p>
      </div>
      <div
        className={s.mbars}
        tabIndex={0}
        role="group"
        aria-labelledby="months-title"
        aria-describedby="months-help"
        onPointerMove={onMove}
        onPointerLeave={() => setActive(null)}
        onKeyDown={onKey}
        onBlur={() => setActive(null)}
      >
        {months.map((month, index) => (
          <span key={month.at} aria-hidden>
            <i
              style={{
                ...(month.value >= 0 ? { bottom: "50%" } : { top: "50%" }),
                height: grown ? `${(Math.abs(month.value) / max) * 50}%` : "0%",
                background: month.value >= 0 ? NAVY : RED,
                opacity: new Date(month.at).getUTCFullYear() === 2022 ? 1 : 0.55,
                filter: active !== null && active !== index ? "saturate(.3) opacity(.45)" : "none",
                transitionDelay: grown && active === null ? `${index * 10}ms` : "0ms",
              }}
            />
          </span>
        ))}
      </div>
      <p id="months-help" className="sr-only">
        {t.details.months.keyboard}
      </p>
      <dl className={s.mstats}>
        <div>
          <dt>{t.details.months.positive}</dt>
          <dd>{t.details.months.positiveValue(positive, months.length)}</dd>
        </div>
        <div>
          <dt>{t.details.months.best}</dt>
          <dd>
            {formatSignedPercent(best.value, locale)} · {shortDate(best.at)}
          </dd>
        </div>
        <div>
          <dt>{t.details.months.worst}</dt>
          <dd>
            {formatSignedPercent(worst.value, locale)} · {shortDate(worst.at)}
          </dd>
        </div>
      </dl>
      <table className="sr-only">
        <caption>{t.details.months.title}</caption>
        <thead>
          <tr>
            <th scope="col">{t.details.date}</th>
            <th scope="col">{t.details.months.return}</th>
          </tr>
        </thead>
        <tbody>
          {months.map((month) => (
            <tr key={month.at}>
              <th scope="row">{longDate(month.at)}</th>
              <td>{formatSignedPercent(month.value, locale)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
