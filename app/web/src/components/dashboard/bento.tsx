"use client";

import { Activity, ChartPie, Compass, GraduationCap, ShieldCheck, TrendingDown, Wallet } from "lucide-react";
import Link from "next/link";
import type { ClientState } from "@/lib/contract/schemas";
import { formatMoney, formatPercent, formatSignedMoney, formatSignedPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { GROUPS, SAMPLE_FACTS, groupWeight, samplePortfolio, tr } from "@/lib/sample/portfolio";
import { cn } from "@/components/ui/cn";
import { horizonTileText } from "./bento-text";
import styles from "./dashboard.module.css";

const ICON = { className: styles.ic, strokeWidth: 1.75, "aria-hidden": true } as const;

function AllocationRows({ rows, label }: { rows: Array<{ name: string; share: number; color: string }>; label: string }) {
  const { locale } = useI18n();
  const max = Math.max(...rows.map((row) => row.share), 0.0001);
  return (
    <div className={styles.allocRows} role="img" aria-label={label}>
      {rows.map((row) => (
        <div key={row.name}>
          <span>{row.name}</span>
          <em>{formatPercent(row.share, locale)}</em>
          <i>
            <b style={{ width: `${(row.share / max) * 100}%`, background: row.color }} />
          </i>
        </div>
      ))}
    </div>
  );
}

/** `mock` mode: the draft's example portfolio, labelled as an example in the header. */
export function SampleBento() {
  const { t, locale } = useI18n();
  const sample = samplePortfolio();
  const capital = SAMPLE_FACTS.capital;
  const protective = (groupWeight(GROUPS[0]!) + groupWeight(GROUPS[3]!)) / 100;
  const rows = GROUPS.map((group) => ({ name: tr(group.name, locale), share: groupWeight(group) / 100, color: group.color }));
  const allocLabel = t.dash.sample.allocAria(rows.map((row) => `${row.name} ${formatPercent(row.share, locale)}`).join(", "));
  return (
    <section className={styles.bento} aria-label={t.dash.bento}>
      <div className={cn(styles.tile, styles.tNavy)}>
        <Wallet {...ICON} />
        <span className={styles.num}>{formatMoney(capital, locale)}</span>
        <p className={styles.lbl}>{t.dash.sample.value}</p>
        <p className={styles.sub}>{t.dash.sample.valueSub}</p>
      </div>
      <div className={cn(styles.tile, styles.tBlue)}>
        <Activity {...ICON} />
        <span className={styles.num}>{formatPercent(sample.vol5y, locale, 1)}</span>
        <p className={styles.lbl}>{t.dash.sample.vol}</p>
        <p className={styles.sub}>{t.dash.sample.volSub(formatPercent(SAMPLE_FACTS.volCap, locale))}</p>
      </div>
      <div className={cn(styles.tile, styles.tRed)}>
        <ChartPie {...ICON} />
        <span className={styles.num}>{formatPercent(protective, locale)}</span>
        <p className={styles.lbl}>{t.dash.sample.alloc}</p>
        <AllocationRows rows={rows} label={allocLabel} />
        <Link className={styles.more} href="/details#positions">
          {t.dash.sample.allocMore}
        </Link>
      </div>
      <div className={cn(styles.tile, styles.tGold)}>
        <TrendingDown {...ICON} />
        <span className={styles.num}>{formatSignedPercent(sample.drop2022, locale)}</span>
        <p className={styles.lbl}>{t.dash.sample.drop}</p>
        <p className={styles.sub}>{t.dash.sample.dropSub(formatSignedMoney(Math.round((sample.drop2022 * capital) / 100) * 100, locale))}</p>
      </div>
      <div className={cn(styles.tile, styles.tGreen)}>
        <ShieldCheck {...ICON} />
        <span className={styles.num}>
          {SAMPLE_FACTS.limits.respected} / {SAMPLE_FACTS.limits.total}
        </span>
        <p className={styles.lbl}>{t.dash.sample.limits}</p>
        <p className={styles.sub}>{t.dash.sample.limitsSub}</p>
      </div>
    </section>
  );
}

/** The existing portfolio once confirmed (its five largest asset classes), or the way to the simulated portfolio. */
function PortfolioTile({ portfolio }: { portfolio: ClientState["portfolio"] }) {
  const { t, locale } = useI18n();
  const confirmed = portfolio && portfolio.status === "confirmed" ? portfolio : null;
  const classes = confirmed
    ? Object.entries(confirmed.exposures.by_asset_class)
        .sort(([, first], [, second]) => second - first)
        .slice(0, 5)
        .map(([key, share], index) => ({
          name: t.assetClasses[key as keyof typeof t.assetClasses] ?? key,
          share,
          color: ["#0B2341", "#E41C23", "#F08A8E", "#A8831C", "#8D9BAD"][index] ?? "#8D9BAD",
        }))
    : [];
  return (
    <div className={cn(styles.tile, styles.tRed)}>
      <ChartPie {...ICON} />
      {confirmed ? (
        <>
          <span className={styles.num}>{formatMoney(confirmed.exposures.total_value_cad, locale)}</span>
          <p className={styles.lbl}>{t.dash.real.portfolio}</p>
          <AllocationRows rows={classes} label={t.dash.real.portfolioAria} />
          <Link className={styles.more} href="/details">
            {t.dash.real.portfolioMore}
          </Link>
        </>
      ) : (
        <>
          <span className={styles.numText}>{t.dash.real.simulated.title}</span>
          <p className={styles.lbl}>{t.dash.real.simulated.lead}</p>
          <p className={styles.tileText}>{t.dash.real.simulated.text(t.appNav.portfolio, t.portfolioView.personas.self.name)}</p>
          <Link className={styles.more} href="/portfolio">
            {t.dash.real.simulated.cta}
          </Link>
        </>
      )}
    </div>
  );
}

/**
 * The horizon band as the figure, then the label, the other horizon facts and the objective. Each text
 * is capped in lines so that none hides the next; the capped ones keep their full text as a tooltip,
 * and in full in the profile panel (« Les cinq dimensions »).
 */
function HorizonTile({ profile }: { profile: ClientState["profile"] }) {
  const { t } = useI18n();
  const { figure, details } = horizonTileText(profile.dimensions.horizon.summary);
  const objective = profile.dimensions.objective.summary;
  return (
    <div className={cn(styles.tile, styles.tGold)}>
      <Compass {...ICON} />
      <span className={cn(styles.numText, styles.clamp2)} title={figure}>
        {figure}
      </span>
      <p className={styles.lbl}>{t.dash.real.horizon}</p>
      {details ? (
        <p className={cn(styles.sub, styles.clamp5)} title={details}>
          {details}
        </p>
      ) : null}
      {objective ? (
        <p className={cn(styles.sub, styles.clamp3)} title={objective}>
          {objective}
        </p>
      ) : null}
    </div>
  );
}

/** `local` and `aws` modes: what the code computes, the profile and the existing portfolio. */
export function ProfileBento({ state }: { state: ClientState }) {
  const { t, locale } = useI18n();
  const { profile, completeness, portfolio } = state;
  const risk = profile.risk;
  return (
    <section className={styles.bento} aria-label={t.dash.bento}>
      <div className={cn(styles.tile, styles.tNavy)}>
        <ShieldCheck {...ICON} />
        <span className={styles.num}>{formatPercent(completeness.displayed, locale)}</span>
        <p className={styles.lbl}>{t.dash.real.completeness}</p>
        <p className={styles.sub}>
          {completeness.ready
            ? t.dash.real.completenessReady(formatPercent(completeness.threshold, locale))
            : t.dash.real.completenessNotReady(formatPercent(Math.max(0, completeness.threshold - completeness.score), locale))}
        </p>
      </div>
      <div className={cn(styles.tile, styles.tBlue)}>
        <Activity {...ICON} />
        <span className={styles.numText}>{profile.effective_risk ? t.riskLevels[profile.effective_risk] : "—"}</span>
        <p className={styles.lbl}>{t.dash.real.risk}</p>
        <p className={styles.sub}>
          {risk?.tolerance && risk.capacity
            ? t.dash.real.riskSub(t.riskLevels[risk.tolerance].toLowerCase(), t.riskLevels[risk.capacity].toLowerCase())
            : t.panel.riskCaption}
        </p>
      </div>
      <PortfolioTile portfolio={portfolio} />
      <HorizonTile profile={profile} />
      <div className={cn(styles.tile, styles.tGreen)}>
        <GraduationCap {...ICON} />
        <span className={styles.numText}>{profile.knowledge_level ? t.knowledgeLevels[profile.knowledge_level] : "—"}</span>
        <p className={styles.lbl}>{t.dash.real.knowledge}</p>
        <p className={styles.sub}>{t.dash.real.knowledgeSub}</p>
      </div>
    </section>
  );
}
