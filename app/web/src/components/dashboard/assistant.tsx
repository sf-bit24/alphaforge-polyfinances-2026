"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import type { ClientState, TraceStep } from "@/lib/contract/schemas";
import { displayAnswer, draftToValue, emptyDraft, isDraftEmpty, type Draft } from "@/lib/client/answers";
import type { ConversationEntry, ReplyInput, TraceRun } from "@/lib/client/session-store";
import { useSession } from "@/lib/client/session";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { formatDuration, formatPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { DEMO, DEMO_CHIPS, type DemoAction, type DemoKey } from "@/lib/sample/assistant-demo";
import { tr } from "@/lib/sample/portfolio";
import { QuestionField } from "@/components/profile/question-field";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Markdown } from "@/components/ui/markdown";
import s from "./dashboard.module.css";
import { IntroScene, type IntroChip } from "./intro-scene";

type DemoEntry = { id: string; at: string; role: "demo-user"; key: DemoKey } | { id: string; at: string; role: "demo-reply"; key: DemoKey };
type Entry = ConversationEntry | DemoEntry;

const DEMO_DELAY_MS: Partial<Record<DemoKey, number>> = { trap: 1400, sandbox: 1200 };
const isDemoKey = (value: string): value is DemoKey => value in DEMO;

interface HowStep {
  tone: "neutral" | "stop" | "ok";
  title: string;
  detail?: string | null;
  meta?: string;
}

/** The trace of a request, in the draft's timeline style, folded under the message. */
function HowIAnswered({ steps, t }: { steps: HowStep[]; t: Dictionary }) {
  if (steps.length === 0) return null;
  return (
    <details
      className={s.how}
      onToggle={(event) => {
        // Opening the steps of the last answer brings them into view in the thread.
        if (event.currentTarget.open) event.currentTarget.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }}
    >
      <summary>
        <ChevronRight aria-hidden />
        {t.assistant.how(steps.length)}
      </summary>
      <ul className={s.trace}>
        {steps.map((step, index) => (
          <li key={`${step.title}-${index}`} className={step.tone === "neutral" ? undefined : s[step.tone]}>
            <b>{step.title}</b>
            {step.detail}
            {step.meta ? <small>{step.meta}</small> : null}
          </li>
        ))}
      </ul>
    </details>
  );
}

function stepsOfRun(run: TraceRun | undefined, t: Dictionary, locale: "fr" | "en"): HowStep[] {
  if (!run) return [];
  return run.steps.map((step: TraceStep, index) => ({
    tone: run.status === "error" && index === run.steps.length - 1 ? "stop" : step.kind === "guardrail" ? "ok" : "neutral",
    title: step.title,
    detail: step.detail,
    meta: [t.trace.kinds[step.kind], step.actor, typeof step.duration_ms === "number" ? formatDuration(step.duration_ms, locale) : null]
      .filter(Boolean)
      .join(" · "),
  }));
}

function sourcesOfRun(run: TraceRun | undefined): string[] {
  if (!run) return [];
  const seen = new Map<string, string>();
  for (const step of run.steps) for (const source of step.sources) if (!seen.has(source.id)) seen.set(source.id, source.title);
  return [...seen.values()];
}

function Sources({ items, tag }: { items: string[]; tag?: string }) {
  if (items.length === 0 && !tag) return null;
  return (
    <div className={s.meta}>
      {tag ? <span className={s.tag}>{tag}</span> : null}
      {items.map((item) => (
        <span key={item} className={s.src}>
          {item}
        </span>
      ))}
    </div>
  );
}

function AgentMessage({ children, asks = false }: { children: ReactNode; asks?: boolean }) {
  return (
    <div className={s.msg} data-asks={asks || undefined}>
      <span className={s.avatar} aria-hidden>
        Y
      </span>
      <div className={s.body}>{children}</div>
    </div>
  );
}

function UserBubble({ children }: { children: ReactNode }) {
  return (
    <div className={cn(s.msg, s.user)}>
      <div className={s.bubble}>{children}</div>
    </div>
  );
}

function DemoReply({ demoKey, onAction }: { demoKey: DemoKey; onAction: (action: DemoAction) => void }) {
  const { t, locale } = useI18n();
  const reply = DEMO[demoKey];
  return (
    <AgentMessage>
      {reply.paragraphs.map((paragraph) => (
        <p key={paragraph.fr}>{tr(paragraph, locale)}</p>
      ))}
      {reply.verdict ? (
        <div className={cn(s.verdict, reply.verdict.ok && s.verdictOk)}>
          <div className={s.verdictH}>
            {tr(reply.verdict.title, locale)}
            <span>{tr(reply.verdict.by, locale)}</span>
          </div>
          <div className={s.checks}>
            {reply.verdict.checks.map((check) => (
              <div key={check.label.fr} className={s.check}>
                <span>{tr(check.label, locale)}</span>
                <b className={check.ok ? s.good : s.bad}>{tr(check.value, locale)}</b>
                <span>{tr(check.cap, locale)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {reply.reasons ? (
        <div className={cn(s.verdict, s.verdictPlain)}>
          <ol className={s.reasons}>
            {reply.reasons.map((reason) => (
              <li key={reason.title.fr}>
                <span>
                  <b>{tr(reason.title, locale)}</b> {tr(reason.text, locale)}
                </span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      {reply.closing ? <p style={{ marginTop: 14 }}>{tr(reply.closing, locale)}</p> : null}
      <Sources items={reply.sources.map((source) => tr(source, locale))} tag={t.assistant.sampleTag} />
      {reply.actions.length > 0 ? (
        <div className={s.actions}>
          {reply.actions.map((action) =>
            action.href ? (
              <Link key={action.key} href={action.href} className={cn(s.btn, action.primary && s.btnPrimary)}>
                {tr(action.label, locale)}
              </Link>
            ) : (
              <button
                key={action.key}
                type="button"
                className={cn(s.btn, action.primary && s.btnPrimary)}
                onClick={() => onAction(action)}
                disabled={action.key === "noop"}
                title={action.key === "noop" ? t.assistant.exampleOnly : undefined}
              >
                {tr(action.label, locale)}
              </button>
            ),
          )}
        </div>
      ) : null}
      <HowIAnswered steps={reply.trace.map((step) => ({ tone: step.tone, title: tr(step.title, locale), detail: tr(step.detail, locale) }))} t={t} />
    </AgentMessage>
  );
}

/**
 * Yan, the assistant of the dashboard draft. Its conversation is A1's (`followup.reply`):
 * it asks the follow-ups that complete the profile, and answers within the profile's scope.
 * In `mock` mode, the draft's portfolio questions also get their example answers.
 * At the end of the questionnaire, the journey shows it without the birds' scene
 * (`intro={false}`) and lets Yan ask its first follow-ups on its own (`autoStart`).
 */
export function Assistant({
  state,
  sample,
  intro: withIntro = true,
  autoStart = false,
}: {
  state: ClientState;
  sample: boolean;
  intro?: boolean;
  autoStart?: boolean;
}) {
  const { t, locale } = useI18n();
  const session = useSession();
  const [intro, setIntro] = useState(() => withIntro && session.conversation.length === 0);
  const [demo, setDemo] = useState<DemoEntry[]>([]);
  const [demoTyping, setDemoTyping] = useState(false);
  const [used, setUsed] = useState<DemoKey[]>([]);
  const [message, setMessage] = useState("");
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const timers = useRef<number[]>([]);
  const replying = session.pending === "followup.reply";
  const followups = state.stage === "followups";
  const ready = state.completeness.ready;
  const conversation = session.conversation;

  const entries: Entry[] = [...conversation, ...demo].sort((a, b) => a.at.localeCompare(b.at));
  const lastAgent = [...conversation].reverse().find((entry) => entry.role === "agent");
  const askQuestions = followups && state.questions.length > 0 && !replying && lastAgent !== undefined;
  const readFromStart = askQuestions && !demoTyping && entries.at(-1) === lastAgent;

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((id) => window.clearTimeout(id));
  }, []);

  // Yan opens the follow-ups once, when nothing has been said yet (a retry goes through the error notice).
  const started = useRef(false);
  const shouldStart = autoStart && followups && conversation.length === 0 && !session.pending;
  useEffect(() => {
    if (!shouldStart || started.current) return;
    started.current = true;
    void session.reply({});
  }, [shouldStart, session]);

  useEffect(() => {
    const thread = threadRef.current;
    if (!thread) return;
    // A message from Yan with questions is read from its start; the rest follows the bottom.
    const asking = readFromStart ? thread.querySelector<HTMLElement>("[data-asks]") : null;
    const top = asking ? asking.offsetTop - 12 : thread.scrollHeight;
    thread.scrollTo({ top, behavior: "smooth" });
  }, [entries.length, replying, demoTyping, session.streamText, readFromStart]);

  const playDemo = (key: DemoKey) => {
    setUsed((current) => (current.includes(key) ? current : [...current, key]));
    setDemo((current) => [...current, { id: crypto.randomUUID(), at: new Date().toISOString(), role: "demo-user", key }]);
    setDemoTyping(true);
    timers.current.push(
      window.setTimeout(() => {
        setDemo((current) => [...current, { id: crypto.randomUUID(), at: new Date().toISOString(), role: "demo-reply", key }]);
        setDemoTyping(false);
      }, DEMO_DELAY_MS[key] ?? 900),
    );
  };

  /** Answers to A1's questions (when filled in), the message, or the request to stop. */
  const send = async (stop: boolean, text: string) => {
    const answers: NonNullable<ReplyInput["answers"]> = [];
    const nextErrors: Record<string, string> = {};
    if (askQuestions) {
      for (const question of state.questions) {
        const draft = drafts[question.id] ?? emptyDraft(question);
        if (isDraftEmpty(question, draft)) continue;
        const result = draftToValue(question, draft, t, locale);
        if (!result.ok) nextErrors[question.id] = result.error;
        else answers.push({ question_id: question.id, value: result.value, prompt: question.prompt, display: displayAnswer(question, result.value, t, locale) });
      }
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    if (!stop && answers.length === 0 && !text.trim()) {
      setProblem(t.followups.nothingToSend);
      return;
    }
    setProblem(null);
    const ok = await session.reply({ answers, message: text, stop });
    if (ok) {
      setMessage("");
      setDrafts({});
    }
  };

  const act = (chip: string, text: string) => {
    if (chip === "followups") void session.reply({});
    else if (chip === "stop") void send(true, "");
    else if (isDemoKey(chip)) playDemo(chip);
    else void send(false, text);
  };

  const chips = (inThread: boolean): IntroChip[] => {
    const list: IntroChip[] = [];
    if (followups && conversation.length === 0 && !replying) list.push({ key: "followups", label: t.assistant.chipFollowups, tone: "ok" });
    if (sample)
      for (const chip of DEMO_CHIPS)
        if (!inThread || !used.includes(chip.key)) list.push({ key: chip.key, label: tr(DEMO[chip.key].user, locale), tone: chip.trap ? "trap" : undefined });
    // Stopping the follow-ups only means something once they have started.
    if (inThread && followups && ready) list.push({ key: "stop", label: t.assistant.chipStop, tone: "ok" });
    return list;
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send(false, message);
  };

  if (intro) {
    return (
      <IntroScene
        heading={followups ? t.assistant.introFollowups : t.assistant.introComplete}
        lead={followups ? t.assistant.leadFollowups : t.assistant.leadComplete}
        placeholder={t.assistant.placeholder}
        sendLabel={t.assistant.send}
        hint={t.assistant.hintBirds}
        chips={chips(false)}
        disabled={Boolean(session.pending)}
        onDone={(text, chip) => {
          setIntro(false);
          act(chip ?? "", text);
        }}
      />
    );
  }

  const renderEntry = (entry: Entry) => {
    if (entry.role === "demo-user") {
      return (
        <UserBubble key={entry.id}>
          <p>{tr(DEMO[entry.key].user, locale)}</p>
        </UserBubble>
      );
    }
    if (entry.role === "demo-reply") {
      return <DemoReply key={entry.id} demoKey={entry.key} onAction={(action) => (isDemoKey(action.key) ? playDemo(action.key) : undefined)} />;
    }
    if (entry.role === "user") {
      return (
        <UserBubble key={entry.id}>
          {entry.answers.length > 0 ? (
            <dl>
              {entry.answers.map((item) => (
                <div key={item.question_id}>
                  <dt>{item.prompt}</dt>
                  <dd>{item.display}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {entry.message ? <p className="whitespace-pre-wrap">{entry.message}</p> : null}
          {entry.stop ? <p className={s.bubbleNote}>{t.followups.stoppedNote}</p> : null}
        </UserBubble>
      );
    }
    if (!entry.message && entry.questions.length === 0) return null;
    const run = entry.runId ? session.runs.find((candidate) => candidate.id === entry.runId) : undefined;
    const isLast = entry === lastAgent;
    return (
      <AgentMessage key={entry.id} asks={isLast && askQuestions}>
        {entry.message ? <Markdown>{entry.message}</Markdown> : null}
        {isLast && askQuestions ? (
          <div className={s.questions}>
            {state.questions.map((question) => (
              <QuestionField
                key={question.id}
                question={question}
                draft={drafts[question.id] ?? emptyDraft(question)}
                onChange={(draft) => {
                  setDrafts((current) => ({ ...current, [question.id]: draft }));
                  setErrors((current) => {
                    if (!(question.id in current)) return current;
                    const next = { ...current };
                    delete next[question.id];
                    return next;
                  });
                }}
                error={errors[question.id] ?? null}
                disabled={replying}
                size="md"
                headingLevel={3}
                followup
              />
            ))}
            <div>
              <button type="button" className={cn(s.btn, s.btnPrimary)} onClick={() => void send(false, message)} disabled={replying}>
                {t.followups.sendAnswers}
              </button>
            </div>
          </div>
        ) : entry.questions.length > 0 ? (
          <ul className={s.asked}>
            {entry.questions.map((question) => (
              <li key={question.id}>· {question.prompt}</li>
            ))}
          </ul>
        ) : null}
        <Sources items={sourcesOfRun(run)} />
        <HowIAnswered steps={stepsOfRun(run, t, locale)} t={t} />
      </AgentMessage>
    );
  };

  const threadChips = chips(true);
  return (
    <section className={s.frame} aria-label={t.assistant.conversation}>
      <div ref={threadRef} className={s.thread}>
        <div className={s.threadIn} aria-live="polite">
          <p className={s.day}>{t.assistant.day}</p>
          <AgentMessage>
            <p>
              {t.assistant.welcome}
              {sample ? ` ${t.assistant.welcomeSample}` : ""}
            </p>
          </AgentMessage>
          {entries.map(renderEntry)}
          {replying || demoTyping ? (
            <AgentMessage>
              {replying && session.streamText ? (
                <Markdown>{session.streamText}</Markdown>
              ) : (
                <span className={s.typing} aria-label={t.assistant.writing}>
                  <i />
                  <i />
                  <i />
                </span>
              )}
            </AgentMessage>
          ) : null}
          {!replying && followups && conversation.length > 0 && state.questions.length === 0 ? (
            <p className={s.day}>{t.followups.noQuestions}</p>
          ) : null}
          {session.error && session.errorAction === "followup.reply" ? (
            <ErrorNotice error={session.error} onRetry={session.retry} onDismiss={session.dismissError} />
          ) : null}
        </div>
      </div>
      <div className={s.compose}>
        <div className={s.composeIn}>
          {threadChips.length > 0 ? (
            <div className={s.chips}>
              {threadChips.map((chip) => (
                <button
                  key={chip.key}
                  type="button"
                  className={cn(s.chip, chip.tone === "trap" && s.chipTrap, chip.tone === "ok" && s.chipOk)}
                  onClick={() => act(chip.key, chip.label)}
                  disabled={Boolean(session.pending) || demoTyping}
                >
                  {chip.label}
                </button>
              ))}
            </div>
          ) : null}
          <form className={s.form} onSubmit={submit} autoComplete="off">
            <input
              className={s.input}
              value={message}
              onChange={(event) => {
                setMessage(event.target.value);
                if (problem) setProblem(null);
              }}
              placeholder={t.assistant.placeholder}
              aria-label={t.assistant.inputLabel}
              maxLength={4000}
              disabled={replying}
            />
            <button className={cn(s.btn, s.btnPrimary)} type="submit" disabled={replying}>
              {t.assistant.send}
            </button>
          </form>
          {problem ? (
            <p role="alert" className={cn(s.hint, s.bad)}>
              {problem}
            </p>
          ) : null}
          <p className={s.hint}>
            {t.assistant.hint}
            {followups ? ` ${ready ? t.followups.stopHintReady : t.followups.stopHintLocked(formatPercent(state.completeness.score, locale))}` : ""}
          </p>
        </div>
      </div>
    </section>
  );
}
