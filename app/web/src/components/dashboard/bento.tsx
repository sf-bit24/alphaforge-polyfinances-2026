"use client";

import { Activity, ChartPie, Compass, GraduationCap, ShieldCheck, TrendingDown, Wallet } from "lucide-react";
import Link from "next/link";
import type { ClientState } from "@/lib/contract/schemas";
import { formatMoney, formatPercent, formatSignedMoney, formatSignedPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { GROUPS, SAMPLE_FACTS, groupWeight, samplePortfolio, tr } from "@/lib/sample/portfolio";
import { cn } from "@/components/ui/cn";
import s from "./dashboard.module.css";

const ICON = { className: s.ic, strokeWidth: 1.75, "aria-hidden": true } as const;

function AllocRows({ rows, label }: { rows: Array<{ name: string; share: number; color: string }>; label: string }) {
  const { locale } = useI18n();
  const max = Math.max(...rows.map((row) => row.share), 0.0001);
  return (
    <div className={s.allocRows} role="img" aria-label={label}>
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
    <section className={s.bento} aria-label={t.dash.bento}>
      <div className={cn(s.tile, s.tNavy)}>
        <Wallet {...ICON} />
        <span className={s.num}>{formatMoney(capital, locale)}</span>
        <p className={s.lbl}>{t.dash.sample.value}</p>
        <p className={s.sub}>{t.dash.sample.valueSub}</p>
      </div>
      <div className={cn(s.tile, s.tBlue)}>
        <Activity {...ICON} />
        <span className={s.num}>{formatPercent(sample.vol5y, locale, 1)}</span>
        <p className={s.lbl}>{t.dash.sample.vol}</p>
        <p className={s.sub}>{t.dash.sample.volSub(formatPercent(SAMPLE_FACTS.volCap, locale))}</p>
      </div>
      <div className={cn(s.tile, s.tRed)}>
        <ChartPie {...ICON} />
        <span className={s.num}>{formatPercent(protective, locale)}</span>
        <p className={s.lbl}>{t.dash.sample.alloc}</p>
        <AllocRows rows={rows} label={allocLabel} />
        <Link className={s.more} href="/details#positions">
          {t.dash.sample.allocMore}
        </Link>
      </div>
      <div className={cn(s.tile, s.tGold)}>
        <TrendingDown {...ICON} />
        <span className={s.num}>{formatSignedPercent(sample.drop2022, locale)}</span>
        <p className={s.lbl}>{t.dash.sample.drop}</p>
        <p className={s.sub}>{t.dash.sample.dropSub(formatSignedMoney(Math.round((sample.drop2022 * capital) / 100) * 100, locale))}</p>
      </div>
      <div className={cn(s.tile, s.tGreen)}>
        <ShieldCheck {...ICON} />
        <span className={s.num}>
          {SAMPLE_FACTS.limits.respected} / {SAMPLE_FACTS.limits.total}
        </span>
        <p className={s.lbl}>{t.dash.sample.limits}</p>
        <p className={s.sub}>{t.dash.sample.limitsSub}</p>
      </div>
    </section>
  );
}

/** `local` and `aws` modes: what version 1 computes, the profile and the existing portfolio. */
export function ProfileBento({ state }: { state: ClientState }) {
  const { t, locale } = useI18n();
  const { profile, completeness, portfolio } = state;
  const confirmed = portfolio && portfolio.status === "confirmed" ? portfolio : null;
  const classes = confirmed
    ? Object.entries(confirmed.exposures.by_asset_class)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 5)
        .map(([key, share], index) => ({
          name: t.assetClasses[key as keyof typeof t.assetClasses] ?? key,
          share,
          color: ["#0B2341", "#E41C23", "#F08A8E", "#A8831C", "#8D9BAD"][index] ?? "#8D9BAD",
        }))
    : [];
  const risk = profile.risk;
  return (
    <section className={s.bento} aria-label={t.dash.bento}>
      <div className={cn(s.tile, s.tNavy)}>
        <ShieldCheck {...ICON} />
        <span className={s.num}>{formatPercent(completeness.displayed, locale)}</span>
        <p className={s.lbl}>{t.dash.real.completeness}</p>
        <p className={s.sub}>
          {completeness.ready
            ? t.dash.real.completenessReady(formatPercent(completeness.threshold, locale))
            : t.dash.real.completenessNotReady(formatPercent(Math.max(0, completeness.threshold - completeness.score), locale))}
        </p>
      </div>
      <div className={cn(s.tile, s.tBlue)}>
        <Activity {...ICON} />
        <span className={s.numText}>{profile.effective_risk ? t.riskLevels[profile.effective_risk] : "—"}</span>
        <p className={s.lbl}>{t.dash.real.risk}</p>
        <p className={s.sub}>
          {risk?.tolerance && risk.capacity
            ? t.dash.real.riskSub(t.riskLevels[risk.tolerance].toLowerCase(), t.riskLevels[risk.capacity].toLowerCase())
            : t.panel.riskCaption}
        </p>
      </div>
      <div className={cn(s.tile, s.tRed)}>
        <ChartPie {...ICON} />
        {confirmed ? (
          <>
            <span className={s.num}>{formatMoney(confirmed.exposures.total_value_cad, locale)}</span>
            <p className={s.lbl}>{t.dash.real.portfolio}</p>
            <AllocRows rows={classes} label={t.dash.real.portfolioAria} />
            <Link className={s.more} href="/details">
              {t.dash.real.portfolioMore}
            </Link>
          </>
        ) : (
          <>
            <span className={s.numText}>{t.dash.real.v2Title}</span>
            <p className={s.lbl}>{t.dash.real.v2Lead}</p>
            <p className={s.v2}>{t.dash.real.v2Text}</p>
          </>
        )}
      </div>
      <div className={cn(s.tile, s.tGold)}>
        <Compass {...ICON} />
        <span className={s.numText}>{profile.dimensions.horizon.summary ?? "—"}</span>
        <p className={s.lbl}>{t.dash.real.horizon}</p>
        {profile.dimensions.objective.summary ? <p className={s.sub}>{profile.dimensions.objective.summary}</p> : null}
      </div>
      <div className={cn(s.tile, s.tGreen)}>
        <GraduationCap {...ICON} />
        <span className={s.numText}>{profile.knowledge_level ? t.knowledgeLevels[profile.knowledge_level] : "—"}</span>
        <p className={s.lbl}>{t.dash.real.knowledge}</p>
        <p className={s.sub}>{t.dash.real.knowledgeSub}</p>
      </div>
    </section>
  );
}
