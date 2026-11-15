"use client";

import { ArrowLeftRight, Briefcase, Database, ShieldX, UserRound } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, type ReactNode } from "react";
import { formatMoney, formatPercent, formatSignedMoney, formatSignedPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { DECISION_LOG, GOVERNANCE, GROUPS, SAMPLE_FACTS, WHY, samplePortfolio, tr, type Group, type Holding, type LogIcon, type SamplePortfolio } from "@/lib/sample/portfolio";
import { cn } from "@/components/ui/cn";
import { AllocationBar, DailyStrip, MonthlyBars, StressRange, VolGauge, VsChart, formatDay } from "./charts";
import styles from "./details.module.css";

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
      <p ref={ref} className={styles.worth} aria-hidden>
        {formatMoney(0, locale)}
      </p>
      <span className="sr-only">{formatMoney(value, locale)}</span>
    </>
  );
}

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** The simulated value, its change over the last month, and the last daily returns. */
function HeroTile({ sample }: { sample: SamplePortfolio }) {
  const { t, locale } = useI18n();
  const count = sample.value.length;
  const last = sample.value[count - 1] ?? 0;
  const monthAgo = sample.value[count - 22] ?? last;
  const change = last - monthAgo;
  return (
    <section className={cn(styles.tile, styles.tHero)} aria-label={t.details.hero.aria}>
      <div className={styles.heroTop}>
        <div>
          <p className={styles.hello}>{t.dash.hello}</p>
          <p className={styles.cap} style={{ fontSize: 14 }}>
            {t.details.hero.lead}
          </p>
        </div>
        <div className={styles.right}>
          <p className={styles.cap} style={{ margin: 0 }}>
            {t.details.hero.worth}
          </p>
          <CountUp value={SAMPLE_FACTS.capital} />
          <p className={styles.delta}>
            <span style={{ color: change >= 0 ? "var(--ok)" : "var(--red-dark)", fontWeight: 600 }}>
              {change >= 0 ? "+" : ""}
              {formatSignedMoney(change, locale)} ({formatSignedPercent(last / monthAgo - 1, locale)})
            </span>
            <span className={styles.muted}> · {t.details.periods["1m"]}</span>
          </p>
        </div>
      </div>
      <DailyStrip sample={sample} />
    </section>
  );
}

/** Time left before the planned retirement, and the glide path of the equity share. */
function RetirementTile({ sample }: { sample: SamplePortfolio }) {
  const { t, locale } = useI18n();
  const lastDay = sample.dates[sample.value.length - 1] ?? 0;
  const retire = new Date(SAMPLE_FACTS.retirement.date);
  const end = new Date(lastDay);
  const monthsLeft = (retire.getUTCFullYear() - end.getUTCFullYear()) * 12 + (retire.getUTCMonth() - end.getUTCMonth());
  return (
    <section className={cn(styles.tile, styles.tRet)} aria-label={t.details.retirement.title}>
      <header>
        <h2>{t.details.retirement.title}</h2>
        <span className={cn(styles.chip, styles.navy)}>{capitalize(formatDay(SAMPLE_FACTS.retirement.date, locale, { month: "long", year: "numeric" }))}</span>
      </header>
      <p className={styles.big}>{t.details.retirement.countdown(Math.floor(monthsLeft / 12), monthsLeft % 12)}</p>
      <p className={styles.cap}>{t.details.retirement.before}</p>
      <div className={styles.glide}>
        <div className={styles.glideRow}>
          <span>{t.details.retirement.today}</span>
          <b>{formatPercent(SAMPLE_FACTS.retirement.equityToday, locale)}</b>
        </div>
        <div className={styles.glideBar} role="img" aria-label={t.details.retirement.pathAria(formatPercent(SAMPLE_FACTS.retirement.glidePath, locale))}>
          <i style={{ width: `${SAMPLE_FACTS.retirement.glidePath * 100}%` }} />
        </div>
        <div className={styles.glideRow}>
          <span>{t.details.retirement.target(retire.getUTCFullYear())}</span>
          <b>{formatPercent(SAMPLE_FACTS.retirement.equityTarget, locale)}</b>
        </div>
        <p className={styles.cap} style={{ marginTop: 10 }}>
          {t.details.retirement.note}
        </p>
      </div>
    </section>
  );
}

function VolatilityTile({ sample }: { sample: SamplePortfolio }) {
  const { t } = useI18n();
  return (
    <section className={cn(styles.tile, styles.tVol)} aria-label={t.details.vol.title}>
      <header>
        <h2>{t.details.vol.title}</h2>
        <span className={styles.cap} style={{ margin: 0 }}>
          {t.details.vol.annualized}
        </span>
      </header>
      <VolGauge sample={sample} />
    </section>
  );
}

function AllocationTile() {
  const { t, locale } = useI18n();
  return (
    <section className={cn(styles.tile, styles.tAlloc)} aria-label={t.details.alloc.title}>
      <header>
        <h2>{t.details.alloc.title}</h2>
        <a className={styles.cap} style={{ margin: 0 }} href="#positions">
          {t.details.positions.title}
        </a>
      </header>
      <p className={styles.big}>{formatMoney(SAMPLE_FACTS.capital, locale)}</p>
      <AllocationBar />
    </section>
  );
}

/** The profile's limits, as checked on the example portfolio: all respected. */
function GovernanceTile() {
  const { t, locale } = useI18n();
  return (
    <section className={cn(styles.tile, styles.tGov, styles.tGovSolid)} aria-label={t.details.gov.title}>
      <header>
        <h2>{t.details.gov.title}</h2>
        <span className={cn(styles.chip, styles.govChip)}>{t.details.gov.compliant}</span>
      </header>
      <p className={styles.govBig}>
        {SAMPLE_FACTS.limits.respected}
        <small> / {SAMPLE_FACTS.limits.total}</small>
      </p>
      <p className={styles.govSub}>{t.details.gov.sub}</p>
      <div className={styles.govBox}>
        <b>{t.details.gov.lastCheck}</b> {t.details.gov.lastCheckText}
      </div>
      <ul className={styles.govList}>
        {GOVERNANCE.map((check) => (
          <li key={check.label.fr}>
            <span>{tr(check.label, locale)}</span>
            <b>{tr(check.value, locale)}</b>
            <em>{t.details.gov.limit(tr(check.limit, locale))}</em>
          </li>
        ))}
      </ul>
      <div className={styles.govFoot}>
        <a href="#journal">{t.details.gov.journal}</a>
        <p>{t.details.gov.note}</p>
      </div>
    </section>
  );
}

function StressTile({ sample }: { sample: SamplePortfolio }) {
  const { t, locale } = useI18n();
  return (
    <section className={cn(styles.tile, styles.tStress)} aria-label={t.details.stress.title}>
      <header>
        <h2>{t.details.stress.title}</h2>
        <span className={cn(styles.chip, styles.ok)}>{t.details.stress.within}</span>
      </header>
      <p className={styles.big}>{formatSignedPercent(sample.drop2022, locale)}</p>
      <p className={styles.cap}>{t.details.stress.dollars(formatSignedMoney(Math.round((sample.drop2022 * SAMPLE_FACTS.capital) / 100) * 100, locale))}</p>
      <StressRange drop={sample.drop2022} />
      <p className={styles.note}>{t.details.stress.note}</p>
    </section>
  );
}

function DecisionLogTile() {
  const { t, locale } = useI18n();
  return (
    <section className={cn(styles.tile, styles.tLog)} id="journal" aria-label={t.details.log.title}>
      <header>
        <h2>{t.details.log.title}</h2>
        <span className={styles.cap} style={{ margin: 0 }}>
          {t.details.log.who}
        </span>
      </header>
      <ul className={styles.log}>
        {DECISION_LOG.map((entry) => (
          <li key={entry.title.fr}>
            <span className={styles.ico}>{LOG_ICON[entry.icon]}</span>
            <div className={styles.txt}>
              <p>{tr(entry.title, locale)}</p>
              <small>
                {tr(entry.by, locale)} · {tr(entry.when, locale)}
              </small>
            </div>
            <span className={cn(styles.chip, styles[entry.status])}>{tr(entry.statusLabel, locale)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function WhyTile() {
  const { t, locale } = useI18n();
  return (
    <section className={cn(styles.tile, styles.tWide)} aria-label={t.details.why.title}>
      <header>
        <h2>{t.details.why.title}</h2>
      </header>
      <div className={styles.why4}>
        {WHY.map((item) => (
          <div key={item.title.fr}>
            <h3>{tr(item.title, locale)}</h3>
            <p>{tr(item.text, locale)}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function HoldingRow({ group, holding }: { group: Group; holding: Holding }) {
  const { locale } = useI18n();
  return (
    <tr>
      <td>
        <span className={styles.ticker}>{holding.ticker}</span>
        <span className={styles.name}>{tr(holding.name, locale)}</span>
      </td>
      <td>
        <span className={styles.pocket}>
          <i style={{ background: group.color }} aria-hidden />
          {tr(group.name, locale)}
        </span>
      </td>
      <td className={styles.n}>{formatPercent(holding.weight / 100, locale)}</td>
      <td className={styles.n}>{formatMoney((holding.weight / 100) * SAMPLE_FACTS.capital, locale)}</td>
      <td className={styles.n}>{holding.vol1y === null ? "—" : formatPercent(holding.vol1y / 100, locale, 1)}</td>
    </tr>
  );
}

function PositionsTile() {
  const { t } = useI18n();
  const holdingCount = GROUPS.reduce((sum, group) => sum + group.holdings.length, 0);
  return (
    <section className={cn(styles.tile, styles.tWide)} id="positions" aria-label={t.details.positions.title}>
      <header>
        <h2>{t.details.positions.title}</h2>
        <span className={styles.cap} style={{ margin: 0 }}>
          {t.details.positions.count(holdingCount)}
        </span>
      </header>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">{t.details.positions.security}</th>
              <th scope="col">{t.details.positions.pocket}</th>
              <th scope="col" className={styles.n}>
                {t.details.positions.weight}
              </th>
              <th scope="col" className={styles.n}>
                {t.details.positions.value}
              </th>
              <th scope="col" className={styles.n}>
                {t.details.positions.vol}
              </th>
            </tr>
          </thead>
          <tbody>{GROUPS.flatMap((group) => group.holdings.map((holding) => <HoldingRow key={holding.ticker} group={group} holding={holding} />))}</tbody>
        </table>
      </div>
    </section>
  );
}

/** `mock` mode: the draft's details page on the example portfolio; every value is synthetic. */
export function SampleDetails() {
  const { t } = useI18n();
  const sample = samplePortfolio();
  return (
    <>
      <div className={styles.main}>
        <div className={styles.head}>
          <div>
            <h1>{t.details.title}</h1>
            <p>{t.details.lead}</p>
          </div>
          <div className={styles.headRight}>
            <span className={cn(styles.chip, styles.wait)}>{t.dash.exampleChip}</span>
            <Link className={styles.btn} href="/dashboard">
              {t.details.back}
            </Link>
          </div>
        </div>

        <div className={styles.grid}>
          <HeroTile sample={sample} />
          <RetirementTile sample={sample} />
          <VolatilityTile sample={sample} />
          <section className={cn(styles.tile, styles.tChart)} aria-label={t.details.chart.title}>
            <VsChart sample={sample} />
          </section>
          <AllocationTile />
          <GovernanceTile />
          <StressTile sample={sample} />
          <section className={cn(styles.tile, styles.tMonths)} aria-label={t.details.months.title}>
            <MonthlyBars sample={sample} />
          </section>
          <DecisionLogTile />
          <WhyTile />
          <PositionsTile />
        </div>
      </div>
      <p className={styles.pageNote}>{t.details.pageNote}</p>
    </>
  );
}
