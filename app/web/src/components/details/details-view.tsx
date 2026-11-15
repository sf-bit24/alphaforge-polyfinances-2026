"use client";

import { ArrowLeftRight, Briefcase, Database, ShieldX, UserRound } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, type ReactNode } from "react";
import type { ClientState } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import { formatMoney, formatPercent, formatSignedMoney, formatSignedPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { DECISION_LOG, GOVERNANCE, GROUPS, SAMPLE_FACTS, WHY, samplePortfolio, tr, type LogIcon } from "@/lib/sample/portfolio";
import { useSampleMode } from "@/components/dashboard/dashboard-view";
import { ExposuresView } from "@/components/profile/exposures";
import { cn } from "@/components/ui/cn";
import { Spinner } from "@/components/ui/spinner";
import { AllocationBar, DailyStrip, MonthlyBars, StressRange, VolGauge, VsChart, formatDay } from "./charts";
import s from "./details.module.css";

const LOG_ICON: Record<LogIcon, ReactNode> = {
  stop: <ShieldX aria-hidden strokeWidth={1.9} />,
  box: <Briefcase aria-hidden strokeWidth={1.9} />,
  user: <UserRound aria-hidden strokeWidth={1.9} />,
  swap: <ArrowLeftRight aria-hidden strokeWidth={1.9} />,
  data: <Database aria-hidden strokeWidth={1.9} />,
};

/** The portfolio value counts up on arrival, as in the draft; screen readers get the value at once. */
function CountUp({ value }: { value: number }) {
  const { locale } = useI18n();
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / 1100);
      node.textContent = formatMoney(value * (1 - (1 - progress) ** 4), locale);
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, locale]);
  return (
    <>
      <p ref={ref} className={s.worth} aria-hidden>
        {formatMoney(0, locale)}
      </p>
      <span className="sr-only">{formatMoney(value, locale)}</span>
    </>
  );
}

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** `mock` mode: the draft's details page on the example portfolio; every value is synthetic. */
function SampleDetails() {
  const { t, locale } = useI18n();
  const sample = samplePortfolio();
  const count = sample.value.length;
  const last = sample.value[count - 1] ?? 0;
  const monthAgo = sample.value[count - 22] ?? last;
  const change = last - monthAgo;
  const lastDay = sample.dates[count - 1] ?? 0;
  const retire = new Date(SAMPLE_FACTS.retirement.date);
  const end = new Date(lastDay);
  const monthsLeft = (retire.getUTCFullYear() - end.getUTCFullYear()) * 12 + (retire.getUTCMonth() - end.getUTCMonth());
  const capital = SAMPLE_FACTS.capital;
  const holdings = GROUPS.reduce((sum, group) => sum + group.holdings.length, 0);

  return (
    <>
      <div className={s.main}>
        <div className={s.head}>
          <div>
            <h1>{t.details.title}</h1>
            <p>{t.details.lead}</p>
          </div>
          <div className={s.headRight}>
            <span className={cn(s.chip, s.wait)}>{t.dash.exampleChip}</span>
            <Link className={s.btn} href="/dashboard">
              {t.details.back}
            </Link>
          </div>
        </div>

        <div className={s.grid}>
          <section className={cn(s.tile, s.tHero)} aria-label={t.details.hero.aria}>
            <div className={s.heroTop}>
              <div>
                <p className={s.hello}>{t.dash.hello}</p>
                <p className={s.cap} style={{ fontSize: 14 }}>
                  {t.details.hero.lead}
                </p>
              </div>
              <div className={s.right}>
                <p className={s.cap} style={{ margin: 0 }}>
                  {t.details.hero.worth}
                </p>
                <CountUp value={capital} />
                <p className={s.delta}>
                  <span style={{ color: change >= 0 ? "var(--ok)" : "var(--red-dark)", fontWeight: 600 }}>
                    {change >= 0 ? "+" : ""}
                    {formatSignedMoney(change, locale)} ({formatSignedPercent(last / monthAgo - 1, locale)})
                  </span>
                  <span className={s.muted}> · {t.details.periods["1m"]}</span>
                </p>
              </div>
            </div>
            <DailyStrip sample={sample} />
          </section>

          <section className={cn(s.tile, s.tRet)} aria-label={t.details.retirement.title}>
            <header>
              <h2>{t.details.retirement.title}</h2>
              <span className={cn(s.chip, s.navy)}>{capitalize(formatDay(SAMPLE_FACTS.retirement.date, locale, { month: "long", year: "numeric" }))}</span>
            </header>
            <p className={s.big}>{t.details.retirement.countdown(Math.floor(monthsLeft / 12), monthsLeft % 12)}</p>
            <p className={s.cap}>{t.details.retirement.before}</p>
            <div className={s.glide}>
              <div className={s.glideRow}>
                <span>{t.details.retirement.today}</span>
                <b>{formatPercent(SAMPLE_FACTS.retirement.equityToday, locale)}</b>
              </div>
              <div className={s.glideBar} role="img" aria-label={t.details.retirement.pathAria(formatPercent(SAMPLE_FACTS.retirement.glidePath, locale))}>
                <i style={{ width: `${SAMPLE_FACTS.retirement.glidePath * 100}%` }} />
              </div>
              <div className={s.glideRow}>
                <span>{t.details.retirement.target(retire.getUTCFullYear())}</span>
                <b>{formatPercent(SAMPLE_FACTS.retirement.equityTarget, locale)}</b>
              </div>
              <p className={s.cap} style={{ marginTop: 10 }}>
                {t.details.retirement.note}
              </p>
            </div>
          </section>

          <section className={cn(s.tile, s.tVol)} aria-label={t.details.vol.title}>
            <header>
              <h2>{t.details.vol.title}</h2>
              <span className={s.cap} style={{ margin: 0 }}>
                {t.details.vol.annualized}
              </span>
            </header>
            <VolGauge sample={sample} />
          </section>

          <section className={cn(s.tile, s.tChart)} aria-label={t.details.chart.title}>
            <VsChart sample={sample} />
          </section>

          <section className={cn(s.tile, s.tAlloc)} aria-label={t.details.alloc.title}>
            <header>
              <h2>{t.details.alloc.title}</h2>
              <a className={s.cap} style={{ margin: 0 }} href="#positions">
                {t.details.positions.title}
              </a>
            </header>
            <p className={s.big}>{formatMoney(capital, locale)}</p>
            <AllocationBar />
          </section>

          <section className={cn(s.tile, s.tGov, s.tGovSolid)} aria-label={t.details.gov.title}>
            <header>
              <h2>{t.details.gov.title}</h2>
              <span className={cn(s.chip, s.govChip)}>{t.details.gov.compliant}</span>
            </header>
            <p className={s.govBig}>
              {SAMPLE_FACTS.limits.respected}
              <small> / {SAMPLE_FACTS.limits.total}</small>
            </p>
            <p className={s.govSub}>{t.details.gov.sub}</p>
            <div className={s.govBox}>
              <b>{t.details.gov.lastCheck}</b> {t.details.gov.lastCheckText}
            </div>
            <ul className={s.govList}>
              {GOVERNANCE.map((check) => (
                <li key={check.label.fr}>
                  <span>{tr(check.label, locale)}</span>
                  <b>{tr(check.value, locale)}</b>
                  <em>{t.details.gov.limit(tr(check.limit, locale))}</em>
                </li>
              ))}
            </ul>
            <div className={s.govFoot}>
              <a href="#journal">{t.details.gov.journal}</a>
              <p>{t.details.gov.note}</p>
            </div>
          </section>

          <section className={cn(s.tile, s.tStress)} aria-label={t.details.stress.title}>
            <header>
              <h2>{t.details.stress.title}</h2>
              <span className={cn(s.chip, s.ok)}>{t.details.stress.within}</span>
            </header>
            <p className={s.big}>{formatSignedPercent(sample.drop2022, locale)}</p>
            <p className={s.cap}>{t.details.stress.dollars(formatSignedMoney(Math.round((sample.drop2022 * capital) / 100) * 100, locale))}</p>
            <StressRange drop={sample.drop2022} />
            <p className={s.note}>{t.details.stress.note}</p>
          </section>

          <section className={cn(s.tile, s.tMonths)} aria-label={t.details.months.title}>
            <MonthlyBars sample={sample} />
          </section>

          <section className={cn(s.tile, s.tLog)} id="journal" aria-label={t.details.log.title}>
            <header>
              <h2>{t.details.log.title}</h2>
              <span className={s.cap} style={{ margin: 0 }}>
                {t.details.log.who}
              </span>
            </header>
            <ul className={s.log}>
              {DECISION_LOG.map((entry) => (
                <li key={entry.title.fr}>
                  <span className={s.ico}>{LOG_ICON[entry.icon]}</span>
                  <div className={s.txt}>
                    <p>{tr(entry.title, locale)}</p>
                    <small>
                      {tr(entry.by, locale)} · {tr(entry.when, locale)}
                    </small>
                  </div>
                  <span className={cn(s.chip, s[entry.status])}>{tr(entry.statusLabel, locale)}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className={cn(s.tile, s.tWide)} aria-label={t.details.why.title}>
            <header>
              <h2>{t.details.why.title}</h2>
            </header>
            <div className={s.why4}>
              {WHY.map((item) => (
                <div key={item.title.fr}>
                  <h3>{tr(item.title, locale)}</h3>
                  <p>{tr(item.text, locale)}</p>
                </div>
              ))}
            </div>
          </section>

          <section className={cn(s.tile, s.tWide)} id="positions" aria-label={t.details.positions.title}>
            <header>
              <h2>{t.details.positions.title}</h2>
              <span className={s.cap} style={{ margin: 0 }}>
                {t.details.positions.count(holdings)}
              </span>
            </header>
            <div className={s.tableWrap}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th scope="col">{t.details.positions.security}</th>
                    <th scope="col">{t.details.positions.pocket}</th>
                    <th scope="col" className={s.n}>
                      {t.details.positions.weight}
                    </th>
                    <th scope="col" className={s.n}>
                      {t.details.positions.value}
                    </th>
                    <th scope="col" className={s.n}>
                      {t.details.positions.vol}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {GROUPS.flatMap((group) =>
                    group.holdings.map((holding) => (
                      <tr key={holding.ticker}>
                        <td>
                          <span className={s.ticker}>{holding.ticker}</span>
                          <span className={s.name}>{tr(holding.name, locale)}</span>
                        </td>
                        <td>
                          <span className={s.pocket}>
                            <i style={{ background: group.color }} aria-hidden />
                            {tr(group.name, locale)}
                          </span>
                        </td>
                        <td className={s.n}>{formatPercent(holding.weight / 100, locale)}</td>
                        <td className={s.n}>{formatMoney((holding.weight / 100) * capital, locale)}</td>
                        <td className={s.n}>{holding.vol1y === null ? "—" : formatPercent(holding.vol1y / 100, locale, 1)}</td>
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
      <p className={s.pageNote}>{t.details.pageNote}</p>
    </>
  );
}

/** `local` and `aws` modes: no portfolio engine in version 1, so only what is computed is shown. */
function RealDetails({ state }: { state: ClientState | null }) {
  const { t } = useI18n();
  const confirmed = state?.portfolio && state.portfolio.status === "confirmed" ? state.portfolio : null;
  return (
    <div className={s.main}>
      <div className={s.head}>
        <div>
          <h1>{t.details.title}</h1>
          <p>{t.details.realLead}</p>
        </div>
        <Link className={s.btn} href="/dashboard">
          {t.details.back}
        </Link>
      </div>
      <div className={s.grid}>
        <section className={cn(s.tile, s.tWide, s.v2)}>
          <h2>{t.details.v2.title}</h2>
          <p>{t.details.v2.text}</p>
          <ul>
            {t.details.v2.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>{t.details.v2.honest}</p>
        </section>
        <section className={cn(s.tile, s.tWide)} aria-label={t.details.existing.title}>
          <header>
            <h2>{t.details.existing.title}</h2>
          </header>
          {confirmed ? (
            <ExposuresView exposures={confirmed.exposures} positions={confirmed.positions} sources={confirmed.sources} fx={confirmed.fx} />
          ) : (
            <div className={s.v2}>
              <p>{t.details.existing.none}</p>
              <p>
                <Link href="/" className={s.btn}>
                  {t.details.existing.cta}
                </Link>
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export function DetailsView() {
  const { t } = useI18n();
  const session = useSession();
  const sample = useSampleMode();
  if (sample === null || (!sample && (!session.hydrated || (session.resuming && !session.state)))) {
    return (
      <div className={s.page}>
        <div className="flex items-center justify-center py-24">
          <Spinner label={t.common.loading} />
        </div>
      </div>
    );
  }
  return <div className={s.page}>{sample ? <SampleDetails /> : <RealDetails state={session.state} />}</div>;
}
