"use client";

import { ArrowRight } from "lucide-react";
import { useState, type FormEvent } from "react";
import type { Dimension, Question } from "@/lib/contract/schemas";
import { draftToValue, emptyDraft, type Draft } from "@/lib/client/answers";
import { useSession } from "@/lib/client/session";
import { useI18n } from "@/lib/i18n/provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { QuestionField } from "./question-field";

/** Order of the base questions (CONTRACTS.md 3.1): level, the five dimensions, then the portfolio. */
const TRACK: Dimension[] = ["knowledge", "objective", "horizon", "risk_tolerance", "risk_capacity", "constraints", "preferences", "context"];

function DimensionTrack({ current }: { current: Dimension }) {
  const { t } = useI18n();
  const position = TRACK.indexOf(current);
  return (
    <ol aria-label={t.stepper.label} className="flex gap-1">
      {TRACK.map((dimension, index) => (
        <li key={dimension} className="flex-1" title={t.dimensions[dimension]}>
          <span
            aria-hidden
            className={cn(
              "block h-1 rounded-full",
              index < position ? "bg-brand-500" : index === position ? "bg-brand-300" : "bg-ink-150",
            )}
          />
          <span className={cn("sr-only")}>
            {t.dimensions[dimension]}
            {index === position ? ` (${t.stepper.current})` : index < position ? ` (${t.stepper.done})` : ""}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** `base_questions`: exactly one deterministic question at a time. */
export function BaseStep({ question, number, autoFocus, onAnswered }: { question: Question; number: number; autoFocus: boolean; onAnswered: () => void }) {
  const { t, locale } = useI18n();
  const session = useSession();
  const [draft, setDraft] = useState<Draft>(() => emptyDraft(question));
  const [error, setError] = useState<string | null>(null);
  const sending = session.pending === "base.answer";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const result = draftToValue(question, draft, t, locale);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setError(null);
    onAnswered();
    await session.answerBase(question.id, result.value);
  };

  return (
    <Card className="animate-fade-in">
      <form onSubmit={submit} noValidate>
        <div className="border-b border-ink-150 px-6 pt-4 pb-3">
          <div className="mb-2 flex items-center justify-between text-xs font-medium text-ink-500">
            <span>{t.question.progress(number)}</span>
            <span>{t.dimensions[question.dimension]}</span>
          </div>
          <DimensionTrack current={question.dimension} />
        </div>
        <div className="px-6 py-6">
          <QuestionField
            question={question}
            draft={draft}
            onChange={(next) => {
              setDraft(next);
              if (error) setError(null);
            }}
            error={error}
            disabled={sending}
            autoFocus={autoFocus}
          />
          {session.error && session.errorAction === "base.answer" ? (
            <ErrorNotice className="mt-5" error={session.error} onRetry={session.retry} onDismiss={session.dismissError} />
          ) : null}
        </div>
        <footer className="flex justify-end border-t border-ink-150 px-6 py-4">
          <Button type="submit" size="lg" loading={sending} icon={<ArrowRight aria-hidden className="size-4" />}>
            {sending ? t.question.sending : t.question.submit}
          </Button>
        </footer>
      </form>
    </Card>
  );
}
