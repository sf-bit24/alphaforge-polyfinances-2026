"use client";

import { Bot, Info, ListChecks } from "lucide-react";
import type { Question } from "@/lib/contract/schemas";
import { questionDomId, type Draft } from "@/lib/client/answers";
import { curly } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/components/ui/cn";
import { AnswerInput } from "./answer-input";

function SourceBadge({ question, fallback }: { question: Question; fallback: boolean }) {
  const { t } = useI18n();
  if (question.source === "a1") {
    return (
      <Badge tone="outline" icon={<Bot aria-hidden className="size-3" />}>
        {t.question.a1}
      </Badge>
    );
  }
  return (
    <Badge tone="outline" icon={<ListChecks aria-hidden className="size-3" />}>
      {fallback ? t.question.fallback : t.question.deterministic}
    </Badge>
  );
}

function QuestionBadges({ question, fallback }: { question: Question; fallback: boolean }) {
  const { t } = useI18n();
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <Badge tone="brand">{t.dimensions[question.dimension]}</Badge>
      <SourceBadge question={question} fallback={fallback} />
      {fallback ? <span className="text-xs text-ink-500">{t.question.fallbackHelp}</span> : null}
      {!question.required ? <span className="text-xs text-ink-500">({t.common.optional})</span> : null}
    </div>
  );
}

function QuestionHelp({ id, help }: { id: string | undefined; help: string }) {
  const { t } = useI18n();
  return (
    <p id={id} className="mt-2 flex items-start gap-2 text-sm text-ink-600">
      <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-navy" />
      <span>
        <span className="sr-only">{t.question.help} : </span>
        {curly(help)}
      </span>
    </p>
  );
}

interface QuestionFieldProps {
  question: Question;
  draft: Draft;
  onChange: (draft: Draft) => void;
  error?: string | null;
  disabled?: boolean;
  size?: "lg" | "md";
  autoFocus?: boolean;
  headingLevel?: 2 | 3;
  /** Asked during the follow-ups: a `deterministic` question there is a fallback, asked when A1 is unavailable. */
  followup?: boolean;
}

/** A question as the runtime sent it: dimension, source, prompt, help, widget. */
export function QuestionField({
  question,
  draft,
  onChange,
  error,
  disabled,
  size = "lg",
  autoFocus,
  headingLevel = 2,
  followup = false,
}: QuestionFieldProps) {
  const domId = questionDomId(question.id);
  const legendId = `legend-${domId}`;
  const helpId = question.help ? `help-${domId}` : undefined;
  const errorId = error ? `error-${domId}` : undefined;
  const describedBy = [helpId, errorId].filter(Boolean).join(" ") || undefined;
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <div role="group" aria-labelledby={legendId} className="min-w-0">
      <QuestionBadges question={question} fallback={followup && question.source === "deterministic"} />
      <Heading
        id={legendId}
        className={cn(
          "font-semibold tracking-tight text-balance text-ink-950",
          size === "lg" ? "text-xl leading-snug sm:text-[1.4rem]" : "text-base leading-snug",
        )}
      >
        {curly(question.prompt)}
      </Heading>
      {question.help ? <QuestionHelp id={helpId} help={question.help} /> : null}
      <div className="mt-4">
        <AnswerInput
          question={question}
          draft={draft}
          onChange={onChange}
          disabled={disabled}
          labelledBy={legendId}
          describedBy={describedBy}
          invalid={Boolean(error)}
          autoFocus={autoFocus}
        />
      </div>
      {error ? (
        <p id={errorId} role="alert" className="mt-2 text-sm font-medium text-critical-ink">
          {error}
        </p>
      ) : null}
    </div>
  );
}
