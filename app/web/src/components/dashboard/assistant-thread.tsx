"use client";

import type { ReactNode, RefObject } from "react";
import type { ClientState, Question, TraceStep } from "@/lib/contract/schemas";
import { emptyDraft } from "@/lib/client/answers";
import type { ConversationEntry, TraceRun } from "@/lib/client/session-store";
import { useSession, type SessionValue } from "@/lib/client/session";
import { useI18n } from "@/lib/i18n/provider";
import { DEMO, type DemoKey } from "@/lib/sample/assistant-demo";
import { tr } from "@/lib/sample/portfolio";
import { QuestionField } from "@/components/profile/question-field";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Markdown } from "@/components/ui/markdown";
import { AgentMessage, HowIAnswered, Sources, UserBubble, type HowStep } from "./assistant-messages";
import styles from "./dashboard.module.css";
import { DemoReply } from "./demo-reply";
import { isDemoKey, type DemoEntry, type FollowupForm } from "./use-assistant";

type Entry = ConversationEntry | DemoEntry;
type AgentEntry = Extract<ConversationEntry, { role: "agent" }>;
type UserEntry = Extract<ConversationEntry, { role: "user" }>;

export interface ThreadView {
  /** A1's conversation and the demo exchanges, in time order. */
  entries: Entry[];
  lastAgent: ConversationEntry | undefined;
  /** A1's reply is being written. */
  replying: boolean;
  followups: boolean;
  /** A1's questions can be answered under its last message. */
  askQuestions: boolean;
}

export function threadView(state: ClientState, session: Pick<SessionValue, "pending" | "conversation">, demoEntries: DemoEntry[]): ThreadView {
  const replying = session.pending === "followup.reply";
  const followups = state.stage === "followups";
  const conversation = session.conversation;
  const entries: Entry[] = [...conversation, ...demoEntries].sort((first, second) => first.at.localeCompare(second.at));
  const lastAgent = [...conversation].reverse().find((entry) => entry.role === "agent");
  const askQuestions = followups && state.questions.length > 0 && !replying && lastAgent !== undefined;
  return { entries, lastAgent, replying, followups, askQuestions };
}

function stepTone(run: TraceRun, step: TraceStep, index: number): HowStep["tone"] {
  if (run.status === "error" && index === run.steps.length - 1) return "stop";
  return step.kind === "guardrail" ? "ok" : "neutral";
}

function stepsOfRun(run: TraceRun | undefined): HowStep[] {
  if (!run) return [];
  return run.steps.map((step: TraceStep, index) => ({
    tone: stepTone(run, step, index),
    title: step.title,
    detail: step.detail,
  }));
}

function sourcesOfRun(run: TraceRun | undefined): string[] {
  if (!run) return [];
  const seen = new Map<string, string>();
  for (const step of run.steps) for (const source of step.sources) if (!seen.has(source.id)) seen.set(source.id, source.title);
  return [...seen.values()];
}

function UserTurn({ entry }: { entry: UserEntry }) {
  const { t } = useI18n();
  return (
    <UserBubble>
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
      {entry.stop ? <p className={styles.bubbleNote}>{t.followups.stoppedNote}</p> : null}
    </UserBubble>
  );
}

/** A1's questions under its last message, while they can be answered. */
function FollowupQuestions({ questions, form, replying }: { questions: Question[]; form: FollowupForm; replying: boolean }) {
  const { t } = useI18n();
  return (
    <div className={styles.questions}>
      {questions.map((question) => (
        <QuestionField
          key={question.id}
          question={question}
          draft={form.drafts[question.id] ?? emptyDraft(question)}
          onChange={(draft) => form.changeDraft(question.id, draft)}
          error={form.errors[question.id] ?? null}
          disabled={replying}
          size="md"
          headingLevel={3}
          followup
        />
      ))}
      <div>
        <button type="button" className={cn(styles.btn, styles.btnPrimary)} onClick={() => void form.send({ stop: false, text: form.message })} disabled={replying}>
          {t.followups.sendAnswers}
        </button>
      </div>
    </div>
  );
}

/** The questions of an earlier message, listed. */
function AskedQuestions({ questions }: { questions: Question[] }) {
  if (questions.length === 0) return null;
  return (
    <ul className={styles.asked}>
      {questions.map((question) => (
        <li key={question.id}>· {question.prompt}</li>
      ))}
    </ul>
  );
}

/** A message of A1; `children` shows its questions. */
function AgentTurn({ entry, run, asks, children }: { entry: AgentEntry; run: TraceRun | undefined; asks: boolean; children: ReactNode }) {
  const { t } = useI18n();
  return (
    <AgentMessage asks={asks}>
      {entry.message ? <Markdown>{entry.message}</Markdown> : null}
      {children}
      <Sources items={sourcesOfRun(run)} />
      <HowIAnswered steps={stepsOfRun(run)} t={t} />
    </AgentMessage>
  );
}

export function ThreadEntries({ view, questions, form, onPlayDemo }: { view: ThreadView; questions: Question[]; form: FollowupForm; onPlayDemo: (key: DemoKey) => void }) {
  const { locale } = useI18n();
  const session = useSession();
  return view.entries.map((entry) => {
    if (entry.role === "demo-user") {
      return (
        <UserBubble key={entry.id}>
          <p>{tr(DEMO[entry.key].user, locale)}</p>
        </UserBubble>
      );
    }
    if (entry.role === "demo-reply") {
      return <DemoReply key={entry.id} demoKey={entry.key} onAction={(action) => (isDemoKey(action.key) ? onPlayDemo(action.key) : undefined)} />;
    }
    if (entry.role === "user") return <UserTurn key={entry.id} entry={entry} />;
    if (!entry.message && entry.questions.length === 0) return null;
    const run = entry.runId ? session.runs.find((candidate) => candidate.id === entry.runId) : undefined;
    const asks = entry === view.lastAgent && view.askQuestions;
    return (
      <AgentTurn key={entry.id} entry={entry} run={run} asks={asks}>
        {asks ? <FollowupQuestions questions={questions} form={form} replying={view.replying} /> : <AskedQuestions questions={entry.questions} />}
      </AgentTurn>
    );
  });
}

/** A reply being written: A1's streamed text so far, or the typing dots. */
export function PendingReply({ replying, streamText }: { replying: boolean; streamText: string }) {
  const { t } = useI18n();
  return (
    <AgentMessage mood={replying && streamText ? undefined : "think"}>
      {replying && streamText ? (
        <Markdown>{streamText}</Markdown>
      ) : (
        <span className={styles.typing} aria-label={t.assistant.writing}>
          <i />
          <i />
          <i />
        </span>
      )}
    </AgentMessage>
  );
}

/** Under the last message: A1 has no question left, or the reply failed. */
export function ThreadNotices({ view, questions }: { view: ThreadView; questions: Question[] }) {
  const { t } = useI18n();
  const session = useSession();
  return (
    <>
      {!view.replying && view.followups && session.conversation.length > 0 && questions.length === 0 ? <p className={styles.day}>{t.followups.noQuestions}</p> : null}
      {session.error && session.errorAction === "followup.reply" ? (
        <ErrorNotice error={session.error} onRetry={session.retry} onDismiss={session.dismissError} />
      ) : null}
    </>
  );
}

/** The scrolling thread: the day and the welcome message, then `children`. */
export function Thread({ threadRef, sample, children }: { threadRef: RefObject<HTMLDivElement | null>; sample: boolean; children: ReactNode }) {
  const { t } = useI18n();
  return (
    <div ref={threadRef} className={styles.thread}>
      <div className={styles.threadIn} aria-live="polite">
        <p className={styles.day}>{t.assistant.day}</p>
        <AgentMessage>
          <p>
            {t.assistant.welcome}
            {sample ? ` ${t.assistant.welcomeSample}` : ""}
          </p>
        </AgentMessage>
        {children}
      </div>
    </div>
  );
}
