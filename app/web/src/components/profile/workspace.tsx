"use client";

import { Briefcase, ChevronDown, CircleCheck, Play } from "lucide-react";
import { useState } from "react";
import type { ClientState } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import { formatMoney, formatPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { TracePanel } from "@/components/trace/trace-panel";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Spinner } from "@/components/ui/spinner";
import { BaseStep } from "./base-step";
import { CompletionStep } from "./completion-step";
import { FollowupsStep } from "./conversation";
import { ExposuresView } from "./exposures";
import { PortfolioInputStep } from "./portfolio-input-step";
import { PortfolioReviewStep } from "./portfolio-review-step";
import { ProfilePanel } from "./profile-panel";
import { StageStepper } from "./stage-stepper";

/** Errors each stage view shows next to its own controls; any other error shows at the top. */
const INLINE_ERRORS: Record<ClientState["stage"], string[]> = {
  base_questions: ["base.answer"],
  existing_portfolio: ["portfolio.submit", "portfolio.skip"],
  portfolio_review: ["portfolio.confirm"],
  followups: ["followup.reply"],
  complete: ["followup.reply"],
};

function ConfirmedPortfolio({ state }: { state: ClientState }) {
  const { t, locale } = useI18n();
  const portfolio = state.portfolio;
  if (!portfolio || portfolio.status !== "confirmed") return null;
  return (
    <Card>
      <details>
        <summary className="flex items-center gap-2 px-5 py-3.5 text-sm font-semibold text-ink-900 focus-visible:outline-2 focus-visible:outline-brand-500">
          <Briefcase aria-hidden className="size-4 text-brand-600" />
          <span className="flex-1">
            {t.review.confirmedTitle}
            <span className="ml-2 font-normal text-ink-500">
              {t.review.positionsCount(portfolio.positions.length)} · {formatMoney(portfolio.exposures.total_value_cad, locale)}
            </span>
          </span>
          <ChevronDown aria-hidden className="size-4 text-ink-400" />
        </summary>
        <div className="border-t border-ink-150 px-5 py-5">
          <ExposuresView exposures={portfolio.exposures} positions={portfolio.positions} sources={portfolio.sources} fx={portfolio.fx} />
        </div>
      </details>
    </Card>
  );
}

function StageView({ state }: { state: ClientState }) {
  const [interacted, setInteracted] = useState(false);
  const baseCount = new Set(state.profile.facts.filter((fact) => fact.provenance.startsWith("base:")).map((fact) => fact.provenance)).size;
  switch (state.stage) {
    case "base_questions": {
      const question = state.questions[0];
      if (!question) return null;
      return <BaseStep key={question.id} question={question} number={baseCount + 1} autoFocus={interacted} onAnswered={() => setInteracted(true)} />;
    }
    case "existing_portfolio":
      return <PortfolioInputStep />;
    case "portfolio_review":
      return state.portfolio ? (
        <PortfolioReviewStep key={state.portfolio.positions.map((position) => position.id).join("|")} portfolio={state.portfolio} message={state.message} />
      ) : null;
    case "followups":
      return (
        <div className="space-y-5">
          <ConfirmedPortfolio state={state} />
          <FollowupsStep state={state} />
        </div>
      );
    case "complete":
      return <CompletionStep state={state} />;
  }
}

/** Mobile and tablet: the completeness stays visible above the flow. */
function CompactSummary({ state }: { state: ClientState }) {
  const { t, locale } = useI18n();
  const { displayed, threshold, ready } = state.completeness;
  return (
    <div className="sticky top-[5.5rem] z-20 md:top-14 -mx-4 border-b border-ink-200 bg-white/95 px-4 py-2.5 backdrop-blur sm:-mx-6 sm:px-6 lg:hidden">
      <div className="flex items-center gap-3 text-sm">
        <span className="font-medium text-ink-700">{t.panel.completeness}</span>
        <span className="relative h-2 flex-1 overflow-hidden rounded-full bg-brand-100">
          <span className="absolute inset-y-0 left-0 rounded-full bg-brand-500" style={{ width: `${displayed * 100}%` }} />
          <span className="absolute inset-y-0 w-0.5 bg-ink-800" style={{ left: `${threshold * 100}%` }} />
        </span>
        <span className="font-semibold text-ink-950 tabular-nums">{formatPercent(displayed, locale)}</span>
        {ready ? (
          <CircleCheck aria-label={t.panel.ready} className="size-4 text-good" />
        ) : (
          <span className="text-xs text-ink-500">{t.panel.threshold}</span>
        )}
      </div>
    </div>
  );
}

function StartCard() {
  const { t } = useI18n();
  const session = useSession();
  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-16 sm:px-6">
      <Card className="px-8 py-10 text-center">
        <h1 className="text-2xl font-semibold tracking-tight text-ink-950">{t.session.none}</h1>
        <p className="mx-auto mt-2 max-w-md text-ink-600">{session.notice === "not_found" ? t.session.notFound : t.session.noneText}</p>
        {session.error ? <ErrorNotice className="mt-6 text-left" error={session.error} onDismiss={session.dismissError} /> : null}
        <Button size="lg" className="mt-8" onClick={() => void session.start()} loading={session.pending === "session.start"} icon={<Play aria-hidden className="size-4" />}>
          {session.notice === "not_found" ? t.session.startNew : t.home.start}
        </Button>
      </Card>
    </div>
  );
}

export function ProfileWorkspace() {
  const { t } = useI18n();
  const session = useSession();

  if (!session.hydrated || (session.resuming && !session.state)) {
    return (
      <div className="flex flex-1 items-center justify-center py-24">
        <Spinner label={t.session.loading} />
      </div>
    );
  }
  const state = session.state;
  if (!state) return <StartCard />;

  const inline = INLINE_ERRORS[state.stage];
  const topError = session.error && !inline.includes(session.errorAction ?? "") ? session.error : null;

  return (
    <div className="mx-auto w-full max-w-[1680px] px-4 pb-10 sm:px-6">
      <CompactSummary state={state} />
      <h1 className="sr-only">{t.nav.profile}</h1>
      <div className="mt-6 grid gap-6 [grid-template-areas:'flow'_'profile'_'trace'] lg:grid-cols-[minmax(0,1fr)_22rem] lg:[grid-template-areas:'flow_profile'_'flow_trace'] lg:grid-rows-[auto_1fr] xl:grid-cols-[19rem_minmax(0,1fr)_23rem] xl:[grid-template-areas:'profile_flow_trace'] xl:grid-rows-1">
        <aside aria-label={t.panel.title} className="min-w-0 [grid-area:profile] xl:sticky xl:top-[4.5rem] xl:max-h-[calc(100dvh-5.5rem)] xl:self-start xl:overflow-y-auto xl:rounded-xl">
          <ProfilePanel state={state} />
        </aside>
        <div className="min-w-0 space-y-5 [grid-area:flow]">
          <Card className="px-5 py-4">
            <StageStepper state={state} />
          </Card>
          {topError ? <ErrorNotice error={topError} onRetry={session.retry} onDismiss={session.dismissError} /> : null}
          <StageView state={state} />
        </div>
        <aside aria-label={t.trace.title} className="min-w-0 [grid-area:trace] xl:sticky xl:top-[4.5rem] xl:max-h-[calc(100dvh-5.5rem)] xl:self-start xl:overflow-y-auto xl:rounded-xl">
          <TracePanel />
        </aside>
      </div>
    </div>
  );
}
