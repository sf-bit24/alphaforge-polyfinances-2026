"use client";

import type { Dispatch, KeyboardEvent, PointerEvent, SetStateAction } from "react";
import type { Locale } from "@/lib/contract/schemas";
import { formatSignedPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import type { MonthlyReturn } from "@/lib/sample/portfolio";
import { NAVY, RED, formatDay } from "./chart-base";
import styles from "./details.module.css";

const longMonth = (at: number, locale: Locale) => formatDay(at, locale, { month: "long", year: "numeric" });
export const shortMonth = (at: number, locale: Locale) => formatDay(at, locale, { month: "short", year: "numeric" });

/** The pointer picks the month under it; the arrow keys move by one month, Escape goes back to the last one. */
export function monthHandlers(count: number, setActive: Dispatch<SetStateAction<number | null>>) {
  return {
    handleMove: (event: PointerEvent<HTMLDivElement>) => {
      const box = event.currentTarget.getBoundingClientRect();
      setActive(Math.max(0, Math.min(count - 1, Math.floor(((event.clientX - box.left) / box.width) * count))));
    },
    handleKey: (event: KeyboardEvent<HTMLDivElement>) => {
      const lastIndex = count - 1;
      if (event.key === "ArrowLeft") setActive((current) => Math.max(0, (current ?? lastIndex) - 1));
      else if (event.key === "ArrowRight") setActive((current) => Math.min(lastIndex, (current ?? lastIndex) + 1));
      else if (event.key === "Escape") setActive(null);
      else return;
      event.preventDefault();
    },
  };
}

/** The month being read, and its date: "last month" until the investor picks another. */
export function MonthReading({ shown, active }: { shown: MonthlyReturn | undefined; active: number | null }) {
  const { t, locale } = useI18n();
  const caption = (month: MonthlyReturn) => (active === null ? t.details.months.lastMonth(longMonth(month.at, locale)) : longMonth(month.at, locale));
  return (
    <div aria-live="polite">
      <p className={styles.big}>{shown ? formatSignedPercent(shown.value, locale) : "—"}</p>
      <p className={styles.cap}>{shown ? caption(shown) : null}</p>
    </div>
  );
}

/** One bar per month around the zero line, 2022 in full colour; while a month is read, the others fade. */
export function MonthColumns({ months, grown, active }: { months: MonthlyReturn[]; grown: boolean; active: number | null }) {
  const max = Math.max(...months.map((month) => Math.abs(month.value)), 1e-9);
  return months.map((month, index) => (
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
  ));
}

/** How many months ended up, and the best and worst ones. */
export function MonthStats({ months }: { months: MonthlyReturn[] }) {
  const { t, locale } = useI18n();
  const positive = months.filter((month) => month.value >= 0).length;
  const best = months.reduce((kept, month) => (month.value > kept.value ? month : kept), months[0] ?? { at: 0, value: 0 });
  const worst = months.reduce((kept, month) => (month.value < kept.value ? month : kept), months[0] ?? { at: 0, value: 0 });
  return (
    <dl className={styles.mstats}>
      <div>
        <dt>{t.details.months.positive}</dt>
        <dd>{t.details.months.positiveValue(positive, months.length)}</dd>
      </div>
      <div>
        <dt>{t.details.months.best}</dt>
        <dd>
          {formatSignedPercent(best.value, locale)} · {shortMonth(best.at, locale)}
        </dd>
      </div>
      <div>
        <dt>{t.details.months.worst}</dt>
        <dd>
          {formatSignedPercent(worst.value, locale)} · {shortMonth(worst.at, locale)}
        </dd>
      </div>
    </dl>
  );
}

/** The monthly returns, for screen readers. */
export function MonthsTable({ months }: { months: MonthlyReturn[] }) {
  const { t, locale } = useI18n();
  return (
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
            <th scope="row">{longMonth(month.at, locale)}</th>
            <td>{formatSignedPercent(month.value, locale)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
