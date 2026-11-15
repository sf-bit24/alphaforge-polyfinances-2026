"use client";

import type { ClientState } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { useI18n } from "@/lib/i18n/provider";
import { sayFor, type SayKey } from "@/lib/journey/path";
import { PortfolioReviewStep } from "@/components/profile/portfolio-review-step";
import { ErrorNotice } from "@/components/ui/error-notice";
import { AssistantLine } from "./assistant-line";
import { PortfolioCard } from "./portfolio-card";
import { QuestionCard } from "./question-card";
import { SummaryCard } from "./summary-card";
import type { Flow } from "./use-journey-flow";

function sayText(t: Dictionary, key: SayKey): string {
  switch (key.kind) {
    case "first":
      return t.journey.say.first;
    case "resume":
      return t.journey.say.resume;
    case "dimension":
      return t.journey.say.dimension[key.dimension];
    case "same":
      return t.journey.say.same[key.n % t.journey.say.same.length] ?? t.journey.say.first;
  }
}

interface StageProps {
  state: ClientState;
  flow: Flow;
  /** The walker stands at the card's stop. */
  visible: boolean;
}

/** `base_questions`: the question of this stop, with the error of the last answer under it. */
function QuestionStage({ state, flow, visible }: StageProps) {
  const { t } = useI18n();
  const session = useSession();
  const question = state.questions[0];
  if (!question) return null;
  return (
    <QuestionCard
      key={question.id}
      question={question}
      say={sayText(t, sayFor(question.dimension, flow.previous, flow.layout.stand, flow.greetBack))}
      busy={!visible || session.pending === "base.answer"}
      autoFocus={visible && flow.interacted}
      onAnswer={(value) => flow.answer(question.dimension, question.id, value)}
    >
      {session.error && session.errorAction === "base.answer" ? (
        <ErrorNotice error={session.error} onRetry={() => void flow.advance(session.retry)} onDismiss={session.dismissError} />
      ) : null}
    </QuestionCard>
  );
}

/** `existing_portfolio`: the briefcase stop. */
function PortfolioStage({ flow, visible }: StageProps) {
  const { t } = useI18n();
  const session = useSession();
  return (
    <PortfolioCard
      say={flow.greetBack ? t.journey.say.resume : t.journey.say.portfolio}
      autoFocus={visible && flow.interacted}
      onSkip={() => void flow.advance(session.skipPortfolio)}
    />
  );
}

/** `portfolio_review`: A2's positions to correct, across the screen. */
function ReviewStage({ state, flow }: StageProps) {
  const { t } = useI18n();
  const session = useSession();
  if (!state.portfolio) return null;
  return (
    <>
      <AssistantLine>{t.journey.say.review}</AssistantLine>
      <PortfolioReviewStep
        key={state.portfolio.positions.map((position) => position.id).join("|")}
        portfolio={state.portfolio}
        message={state.message}
        onConfirm={(positions) => flow.advance(() => session.confirmPortfolio(positions))}
      />
    </>
  );
}

/** `followups` and `complete`: the summary at the house. */
function SummaryStage({ state, flow, visible }: StageProps) {
  const session = useSession();
  return (
    <SummaryCard
      state={state}
      autoFocus={visible && flow.interacted}
      busy={Boolean(session.pending)}
      onOpenProfile={() => flow.setDrawer("profile")}
      onRestart={flow.restart}
    />
  );
}

/** The card of the stop where the walker stands, by stage. */
export function StageCard(props: StageProps) {
  switch (props.state.stage) {
    case "base_questions":
      return <QuestionStage {...props} />;
    case "existing_portfolio":
      return <PortfolioStage {...props} />;
    case "portfolio_review":
      return <ReviewStage {...props} />;
    case "followups":
    case "complete":
      return <SummaryStage {...props} />;
  }
}
