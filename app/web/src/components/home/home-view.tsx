"use client";

import { ArrowRight, Bot, Briefcase, ListChecks, Play, RotateCcw, ShieldCheck, Workflow } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { TRACE_KINDS } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import { formatPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { KIND_STYLE } from "@/components/trace/trace-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";

const FEATURE_ICONS: ReactNode[] = [
  <ListChecks key="base" aria-hidden className="size-5" />,
  <Briefcase key="portfolio" aria-hidden className="size-5" />,
  <Bot key="a1" aria-hidden className="size-5" />,
  <Workflow key="trace" aria-hidden className="size-5" />,
];

function SessionActions() {
  const { t, locale } = useI18n();
  const session = useSession();
  const router = useRouter();
  const begin = async () => {
    if (await session.start()) router.push("/profile");
  };
  const restart = async () => {
    if (!window.confirm(t.home.restartConfirm)) return;
    if (await session.restart()) router.push("/profile");
  };
  const state = session.state;
  if (!session.hydrated || session.resuming) {
    return <div className="h-12" aria-hidden />;
  }
  return (
    <div className="space-y-4">
      {state ? (
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href="/profile"
            className="inline-flex h-12 items-center gap-2 rounded-lg bg-white px-5 text-base font-semibold text-ink-950 shadow-sm hover:bg-brand-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-300"
          >
            <Play aria-hidden className="size-4" />
            {t.home.resume}
          </Link>
          <Button
            variant="inverseGhost"
            size="lg"
            onClick={() => void restart()}
            loading={session.pending === "session.start"}
            icon={<RotateCcw aria-hidden className="size-4" />}
          >
            {t.home.restart}
          </Button>
        </div>
      ) : (
        <Button
          variant="inverse"
          size="lg"
          onClick={() => void begin()}
          loading={session.pending === "session.start"}
          icon={<Play aria-hidden className="size-4" />}
        >
          {t.home.start}
        </Button>
      )}
      {state ? (
        <div className="inline-flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg bg-white/8 px-4 py-2.5 text-sm ring-1 ring-white/15">
          <span className="font-semibold text-white">{t.home.current}</span>
          <span className="text-ink-200">
            {t.home.currentStage} : <span className="text-white">{t.stages[state.stage]}</span>
          </span>
          <span className="text-ink-200">
            {t.home.currentCompleteness} : <span className="text-white tabular-nums">{formatPercent(state.completeness.displayed, locale)}</span>
          </span>
        </div>
      ) : null}
      {session.notice === "not_found" ? <p className="max-w-xl text-sm text-warning">{t.session.notFound}</p> : null}
      {session.error && !state ? <ErrorNotice className="max-w-xl" error={session.error} onDismiss={session.dismissError} /> : null}
    </div>
  );
}

export function HomeView() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col">
      <section className="relative overflow-hidden bg-ink-950 text-white">
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(60rem_30rem_at_85%_-10%,rgb(42_120_214/0.35),transparent),radial-gradient(40rem_25rem_at_-10%_110%,rgb(16_66_129/0.6),transparent)]" />
        <div className="relative mx-auto grid max-w-[1280px] gap-12 px-4 py-16 sm:px-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:py-20">
          <div>
            <p className="text-sm font-semibold tracking-wide text-brand-300 uppercase">{t.home.eyebrow}</p>
            <h1 className="mt-3 max-w-2xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">{t.home.title}</h1>
            <p className="mt-5 max-w-2xl text-lg leading-relaxed text-ink-200">{t.home.subtitle}</p>
            <div className="mt-8">
              <SessionActions />
            </div>
            <p className="mt-8 flex max-w-xl items-start gap-2 rounded-lg bg-warning/10 px-4 py-3 text-sm font-medium text-warning ring-1 ring-warning/30">
              <ShieldCheck aria-hidden className="mt-0.5 size-4 shrink-0" />
              {t.banner.text}
            </p>
          </div>
          <section aria-label={t.trace.title} className="self-start rounded-xl bg-white/[0.04] text-white shadow-card ring-1 ring-white/15">
            <div className="border-b border-white/10 px-5 py-4">
              <p className="text-sm font-semibold">{t.trace.title}</p>
              <p className="mt-0.5 text-xs text-ink-300">{t.trace.subtitle}</p>
            </div>
            <ul className="space-y-3 px-5 py-5">
              {TRACE_KINDS.map((kind) => (
                <li key={kind} className="flex items-start gap-3">
                  <span
                    aria-hidden
                    className={cn("flex size-7 shrink-0 items-center justify-center rounded-full", KIND_STYLE[kind].ink)}
                    style={{ backgroundColor: KIND_STYLE[kind].color }}
                  >
                    {KIND_STYLE[kind].icon}
                  </span>
                  <div>
                    <p className="text-sm font-semibold">{t.trace.kinds[kind]}</p>
                    <p className="text-[0.8rem] leading-snug text-ink-300">{t.trace.kindHelp[kind]}</p>
                  </div>
                </li>
              ))}
            </ul>
            <p className="border-t border-white/10 px-5 py-3 text-xs text-ink-300">{t.trace.footnote}</p>
          </section>
        </div>
      </section>

      <section aria-labelledby="features" className="mx-auto w-full max-w-[1280px] px-4 py-14 sm:px-6">
        <h2 id="features" className="text-2xl font-semibold tracking-tight text-ink-950">
          {t.home.featuresTitle}
        </h2>
        <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {t.home.features.map((feature, index) => (
            <li key={feature.title}>
              <Card className="h-full px-5 py-5">
                <span className="flex size-10 items-center justify-center rounded-lg bg-brand-50 text-brand-600 ring-1 ring-brand-100">
                  {FEATURE_ICONS[index]}
                </span>
                <h3 className="mt-4 font-semibold text-ink-950">{feature.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-600">{feature.text}</p>
              </Card>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="flow" className="border-y border-ink-200 bg-white">
        <div className="mx-auto max-w-[1280px] px-4 py-14 sm:px-6">
          <h2 id="flow" className="text-2xl font-semibold tracking-tight text-ink-950">
            {t.home.flowTitle}
          </h2>
          <ol className="mt-6 grid gap-4 md:grid-cols-4">
            {t.home.flow.map((step, index) => (
              <li key={step.title} className="relative rounded-xl bg-ink-50 px-5 py-5 ring-1 ring-ink-150">
                <span className="flex size-8 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white">{index + 1}</span>
                <h3 className="mt-3 font-semibold text-ink-950">{step.title}</h3>
                <p className="mt-1 text-sm text-ink-600">{step.text}</p>
                {index < t.home.flow.length - 1 ? (
                  <ArrowRight aria-hidden className="absolute top-1/2 -right-3.5 hidden size-5 -translate-y-1/2 text-ink-300 md:block" />
                ) : null}
              </li>
            ))}
          </ol>
          <p className="mt-5 max-w-3xl text-sm text-ink-600">{t.home.thresholdNote}</p>
        </div>
      </section>

      <section aria-labelledby="agents" className="mx-auto w-full max-w-[1280px] px-4 py-14 sm:px-6">
        <h2 id="agents" className="text-2xl font-semibold tracking-tight text-ink-950">
          {t.home.agentsTitle}
        </h2>
        <p className="mt-2 text-ink-600">{t.home.agentsLead}</p>
        <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {t.home.agents.map((agent) => (
            <li key={agent.id}>
              <Card className="h-full px-5 py-5">
                <Badge tone="brand" className="font-mono">
                  {agent.id}
                </Badge>
                <h3 className="mt-3 font-semibold text-ink-950">{agent.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-600">{agent.text}</p>
              </Card>
            </li>
          ))}
        </ul>
        <p className="mt-8 text-sm text-ink-500">{t.home.versionNote}</p>
      </section>
    </div>
  );
}
