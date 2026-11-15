"use client";

import { Bot, CircleStop, Send, UserRound } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import type { ClientState, Question } from "@/lib/contract/schemas";
import { displayAnswer, draftToValue, emptyDraft, isDraftEmpty, type Draft } from "@/lib/client/answers";
import type { ConversationEntry } from "@/lib/client/session-store";
import { useSession } from "@/lib/client/session";
import { formatPercent, formatTime } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Markdown } from "@/components/ui/markdown";
import { QuestionField } from "./question-field";

function AgentAvatar() {
  return (
    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-kind-agent text-white shadow-sm">
      <Bot aria-hidden className="size-4" />
    </span>
  );
}

function TypingDots() {
  return (
    <span aria-hidden className="inline-flex gap-1">
      {[0, 1, 2].map((dot) => (
        <span key={dot} className="size-1.5 animate-pulse-dot rounded-full bg-ink-400" style={{ animationDelay: `${dot * 180}ms` }} />
      ))}
    </span>
  );
}

function EntryView({ entry }: { entry: ConversationEntry }) {
  const { t, locale } = useI18n();
  if (entry.role === "user") {
    return (
      <li className="animate-fade-in flex justify-end gap-3">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-brand-600 px-4 py-3 text-sm text-white shadow-sm">
          <p className="mb-1 text-[0.7rem] font-semibold text-brand-100">
            {t.followups.you} · <time dateTime={entry.at}>{formatTime(entry.at, locale)}</time>
          </p>
          {entry.answers.length > 0 ? (
            <dl className="space-y-1.5">
              {entry.answers.map((answer) => (
                <div key={answer.question_id}>
                  <dt className="text-[0.75rem] text-brand-100">{answer.prompt}</dt>
                  <dd className="font-medium">{answer.display}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {entry.message ? <p className={cn("whitespace-pre-wrap", entry.answers.length > 0 && "mt-2")}>{entry.message}</p> : null}
          {entry.stop ? <p className="mt-1 text-[0.75rem] font-semibold text-brand-100">{t.followups.stoppedNote}</p> : null}
        </div>
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-ink-200 text-ink-700">
          <UserRound aria-hidden className="size-4" />
        </span>
      </li>
    );
  }
  // A null message (deterministic transition) without questions renders nothing.
  if (!entry.message && entry.questions.length === 0) return null;
  return (
    <li className="animate-fade-in flex gap-3">
      <AgentAvatar />
      <div className="min-w-0 max-w-[92%] rounded-2xl rounded-tl-sm bg-white px-4 py-3 shadow-sm ring-1 ring-ink-200">
        <p className="mb-1 text-[0.7rem] font-semibold text-ink-500">
          {t.followups.agent} · <time dateTime={entry.at}>{formatTime(entry.at, locale)}</time>
        </p>
        {entry.message ? <Markdown>{entry.message}</Markdown> : null}
        {entry.questions.length > 0 ? (
          <ul className="mt-2 space-y-1 border-t border-ink-150 pt-2">
            {entry.questions.map((question) => (
              <li key={question.id} className="text-[0.8rem] text-ink-600">
                · {question.prompt}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </li>
  );
}

/** Read-only thread, for the completion view. */
export function ConversationHistory({ entries }: { entries: ConversationEntry[] }) {
  return (
    <ol className="space-y-4">
      {entries.map((entry) => (
        <EntryView key={entry.id} entry={entry} />
      ))}
    </ol>
  );
}

function QuestionsForm({
  questions,
  drafts,
  errors,
  onChange,
  disabled,
}: {
  questions: Question[];
  drafts: Record<string, Draft>;
  errors: Record<string, string>;
  onChange: (id: string, draft: Draft) => void;
  disabled: boolean;
}) {
  return (
    <div className="space-y-6">
      {questions.map((question) => (
        <QuestionField
          key={question.id}
          question={question}
          draft={drafts[question.id] ?? emptyDraft(question)}
          onChange={(draft) => onChange(question.id, draft)}
          error={errors[question.id] ?? null}
          disabled={disabled}
          size="md"
          headingLevel={3}
          followup
        />
      ))}
    </div>
  );
}

/** `followups`: A1 as a conversation; its structured questions render as widgets. */
export function FollowupsStep({ state }: { state: ClientState }) {
  const { t, locale } = useI18n();
  const session = useSession();
  const messageId = useId();
  const [message, setMessage] = useState("");
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const kicked = useRef(false);
  const endRef = useRef<HTMLDivElement>(null);
  const replying = session.pending === "followup.reply";
  const questionsKey = state.questions.map((question) => question.id).join("|");

  // On arrival in `followups`, A1 asks its first follow-ups (no answers, no message).
  const needsKickoff = state.stage === "followups" && state.questions.length === 0 && state.message === null;
  const { pending, error, reply } = session;
  useEffect(() => {
    if (!needsKickoff || kicked.current || pending || error) return;
    kicked.current = true;
    void reply({});
  }, [needsKickoff, pending, error, reply]);

  const entryCount = session.conversation.length;
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [entryCount]);

  const send = async (stop: boolean) => {
    const answers: Array<{ question_id: string; value: Parameters<typeof displayAnswer>[1]; prompt: string; display: string }> = [];
    const nextErrors: Record<string, string> = {};
    for (const question of state.questions) {
      const draft = drafts[question.id] ?? emptyDraft(question);
      if (isDraftEmpty(question, draft)) continue;
      const result = draftToValue(question, draft, t, locale);
      if (!result.ok) {
        nextErrors[question.id] = result.error;
        continue;
      }
      answers.push({ question_id: question.id, value: result.value, prompt: question.prompt, display: displayAnswer(question, result.value, t, locale) });
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    if (!stop && answers.length === 0 && !message.trim()) {
      setProblem(t.followups.nothingToSend);
      return;
    }
    setProblem(null);
    const ok = await session.reply({ answers, message, stop });
    if (ok) {
      setMessage("");
      setDrafts({});
    }
  };

  const ready = state.completeness.ready;
  const lastEntry = session.conversation[session.conversation.length - 1];
  const showQuestions = state.stage === "followups" && state.questions.length > 0 && !replying;

  return (
    <div className="animate-fade-in space-y-4">
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-ink-950 sm:text-[1.4rem]">{t.followups.title}</h2>
        <p className="mt-1 text-sm text-ink-600">{t.followups.intro}</p>
      </div>

      <Card className="bg-ink-50/50">
        <ol aria-live="polite" className="space-y-4 px-4 py-5 sm:px-5">
          {session.conversation.map((entry) =>
            entry === lastEntry && entry.role === "agent" && showQuestions ? (
              <li key={entry.id} className="animate-fade-in flex gap-3">
                <AgentAvatar />
                <div className="min-w-0 flex-1 rounded-2xl rounded-tl-sm bg-white px-4 py-4 shadow-sm ring-1 ring-ink-200 sm:px-5">
                  <p className="mb-1 text-[0.7rem] font-semibold text-ink-500">
                    {t.followups.agent} · <time dateTime={entry.at}>{formatTime(entry.at, locale)}</time>
                  </p>
                  {entry.message ? <Markdown>{entry.message}</Markdown> : null}
                  <div className="mt-4 border-t border-ink-150 pt-4">
                    <QuestionsForm
                      key={questionsKey}
                      questions={state.questions}
                      drafts={drafts}
                      errors={errors}
                      onChange={(id, draft) => {
                        setDrafts((current) => ({ ...current, [id]: draft }));
                        setErrors((current) => {
                          if (!(id in current)) return current;
                          const next = { ...current };
                          delete next[id];
                          return next;
                        });
                      }}
                      disabled={replying}
                    />
                  </div>
                </div>
              </li>
            ) : (
              <EntryView key={entry.id} entry={entry} />
            ),
          )}
          {replying ? (
            <li className="flex gap-3">
              <AgentAvatar />
              <div className="min-w-0 max-w-[92%] rounded-2xl rounded-tl-sm bg-white px-4 py-3 shadow-sm ring-1 ring-brand-200">
                <p className="mb-1 flex items-center gap-2 text-[0.7rem] font-semibold text-ink-500">
                  {t.followups.agent} <TypingDots />
                </p>
                {session.streamText ? (
                  <Markdown>{session.streamText}</Markdown>
                ) : (
                  <p className="text-sm text-ink-500">{session.conversation.length === 0 ? t.followups.preparing : t.followups.thinking}</p>
                )}
              </div>
            </li>
          ) : null}
          {!replying && session.conversation.length === 0 && !session.error ? (
            <li className="text-sm text-ink-500">{t.followups.preparing}</li>
          ) : null}
          {!replying && state.stage === "followups" && state.questions.length === 0 && session.conversation.length > 0 ? (
            <li className="text-sm text-ink-500">{t.followups.noQuestions}</li>
          ) : null}
        </ol>
        <div ref={endRef} />
      </Card>

      {session.error && session.errorAction === "followup.reply" ? (
        <ErrorNotice error={session.error} onRetry={session.retry} onDismiss={session.dismissError} />
      ) : null}

      <Card>
        <div className="px-5 pt-4 pb-3">
          <label htmlFor={messageId} className="text-sm font-medium text-ink-900">
            {t.followups.messageLabel}
          </label>
          <textarea
            id={messageId}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                void send(false);
              }
            }}
            rows={2}
            maxLength={4000}
            disabled={replying}
            placeholder={t.followups.messagePlaceholder}
            className="mt-1.5 block w-full resize-y rounded-lg border-0 bg-white px-3.5 py-2.5 text-[0.95rem] text-ink-950 shadow-sm ring-1 ring-ink-300 ring-inset placeholder:text-ink-400 focus:ring-2 focus:ring-brand-500 focus:outline-none disabled:bg-ink-50"
          />
          {problem ? (
            <p role="alert" className="mt-2 text-sm font-medium text-critical-ink">
              {problem}
            </p>
          ) : null}
        </div>
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-ink-150 px-5 py-3">
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              onClick={() => void send(true)}
              disabled={!ready || replying}
              aria-describedby={`${messageId}-stop`}
              icon={<CircleStop aria-hidden className="size-4" />}
            >
              {t.followups.stop}
            </Button>
            <p id={`${messageId}-stop`} className={cn("max-w-xs text-xs", ready ? "text-good-ink" : "text-ink-500")}>
              {ready ? t.followups.stopHintReady : t.followups.stopHintLocked(formatPercent(state.completeness.score, locale))}
            </p>
          </div>
          <Button onClick={() => void send(false)} loading={replying} icon={<Send aria-hidden className="size-4" />}>
            {showQuestions && state.questions.length > 0 ? t.followups.sendAnswers : t.followups.send}
          </Button>
        </footer>
      </Card>
    </div>
  );
}
