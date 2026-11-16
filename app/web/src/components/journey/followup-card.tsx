"use client";

import { CircleCheck, Send } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import type { AnswerValue, ClientState, Question } from "@/lib/contract/schemas";
import { displayAnswer } from "@/lib/client/answers";
import { useAccount } from "@/lib/client/account";
import type { ReplyInput } from "@/lib/client/session-store";
import { useSession } from "@/lib/client/session";
import { useI18n } from "@/lib/i18n/provider";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Markdown } from "@/components/ui/markdown";
import { YanFigure } from "@/components/yan/yan";
import { AssistantLine } from "./assistant-line";
import { QuestionCard } from "./question-card";
import styles from "./journey.module.css";

type ReplyAnswer = NonNullable<ReplyInput["answers"]>[number];

interface FollowupProps {
  state: ClientState;
  visible: boolean;
  /** The investor has acted on the page (focus may move to the card). */
  interacted: boolean;
  onRestart: () => void;
}

/** At the top of each follow-up card: the questionnaire is over, and where Yan's questions stand. */
function DoneBadge({ index, total }: { index: number; total: number }) {
  const { t } = useI18n();
  return (
    <p className={styles.kicker}>
      <CircleCheck aria-hidden />
      {t.journey.end.done}
      {total > 0 ? <span className={styles.kickerPct}>{t.journey.end.progress(index + 1, total)}</span> : null}
    </p>
  );
}

/** Yan opens a batch with its own message: its first paragraph, the rest folded under it. */
function YanMessage({ message }: { message: string }) {
  const { t } = useI18n();
  const [first = "", ...rest] = message.trim().split(/\n\s*\n/u);
  return (
    <>
      <Markdown>{first}</Markdown>
      {rest.length > 0 ? (
        <details className={styles.more}>
          <summary>{t.journey.end.more}</summary>
          <Markdown>{rest.join("\n\n")}</Markdown>
        </details>
      ) : null}
    </>
  );
}

/** Answering in one's own words: the text goes to Yan with the answers given so far. */
function OwnWords({ busy, onSend, onBack }: { busy: boolean; onSend: (text: string) => void; onBack: () => void }) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => ref.current?.focus({ preventScroll: true }), []);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (text.trim()) onSend(text.trim());
  };
  return (
    <form onSubmit={submit} noValidate>
      <textarea
        ref={ref}
        className={styles.textarea}
        rows={3}
        maxLength={2000}
        value={text}
        onChange={(event) => setText(event.target.value)}
        aria-label={t.journey.end.ownWordsLabel}
        placeholder={t.journey.end.ownWordsPlaceholder}
        disabled={busy}
      />
      <div className={styles.actions}>
        <button type="submit" className={styles.primary} disabled={busy || !text.trim()}>
          {t.journey.end.send}
          <Send aria-hidden className="size-4" />
        </button>
        <button type="button" className={styles.ghost} onClick={onBack} disabled={busy}>
          {t.journey.end.choices}
        </button>
      </div>
    </form>
  );
}

interface ActionsProps {
  canSkip: boolean;
  canStop: boolean;
  busy: boolean;
  on: { skip: () => void; write: () => void; stop: () => void };
}

/** Under the answers: skip, answer in one's own words, or stop once the profile is usable. */
function FollowupActions({ canSkip, canStop, busy, on }: ActionsProps) {
  const { t } = useI18n();
  return (
    <div className={styles.followupActions}>
      <button type="button" className={styles.ghost} onClick={on.write} disabled={busy}>
        {t.journey.end.ownWords}
      </button>
      {canSkip ? (
        <button type="button" className={styles.ghost} onClick={on.skip} disabled={busy}>
          {t.journey.end.skip}
        </button>
      ) : null}
      {canStop ? (
        <button type="button" className={styles.ghost} onClick={on.stop} disabled={busy}>
          {t.journey.end.stop}
        </button>
      ) : null}
    </div>
  );
}

const answerOf = (question: Question, value: AnswerValue, display: string): ReplyAnswer => ({
  question_id: question.id,
  value,
  prompt: question.prompt,
  display,
});

/**
 * One batch of A1's questions, asked one card at a time like the base questions. The
 * answers go to A1 together after the last one (one call per batch, not per question).
 */
function FollowupBatch({ state, visible, interacted, message }: Omit<FollowupProps, "onRestart"> & { message: string | null }) {
  const { t, locale } = useI18n();
  const session = useSession();
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<ReplyAnswer[]>([]);
  const [writing, setWriting] = useState(false);
  const questions = state.questions;
  const question = questions[index];
  if (!question) return null;
  const busy = !visible || session.pending === "followup.reply";
  const last = index === questions.length - 1;
  const send = (input: ReplyInput) => void session.reply(input);
  const next = (collected: ReplyAnswer[]) => {
    if (last) return send({ answers: collected });
    setAnswers(collected);
    setIndex(index + 1);
  };
  const say = index === 0 && message ? <YanMessage message={message} /> : t.journey.say.same[index % t.journey.say.same.length];
  const on = { skip: () => next(answers), write: () => setWriting(true), stop: () => send({ answers, stop: true }) };
  return (
    <>
      <DoneBadge index={index} total={questions.length} />
      {writing ? (
        <>
          <AssistantLine>{say}</AssistantLine>
          <OwnWords busy={busy} onSend={(text) => send({ answers, message: text })} onBack={() => setWriting(false)} />
        </>
      ) : (
        <QuestionCard
          key={question.id}
          question={question}
          say={say}
          busy={busy}
          autoFocus={visible && interacted}
          onAnswer={(value) => next([...answers, answerOf(question, value, displayAnswer(question, value, t, locale))])}
        >
          <FollowupActions canSkip={!last || answers.length > 0} canStop={state.completeness.ready} busy={busy} on={on} />
        </QuestionCard>
      )}
    </>
  );
}

/** While Yan reads the answers and prepares its questions: its words as they come. */
function Thinking({ first }: { first: boolean }) {
  const { t } = useI18n();
  const session = useSession();
  const error = session.error && session.errorAction === "followup.reply" ? session.error : null;
  return (
    <>
      <DoneBadge index={0} total={0} />
      <AssistantLine mood="think">{first ? t.journey.end.thinking : t.journey.end.thinkingNext}</AssistantLine>
      {error ? (
        <div className={styles.notice}>
          <ErrorNotice error={error} onRetry={session.retry} onDismiss={session.dismissError} />
        </div>
      ) : (
        <span className={styles.typing} role="status" aria-label={t.assistant.writing}>
          <i />
          <i />
          <i />
        </span>
      )}
    </>
  );
}

/** A1 has nothing more to ask: stop here, or go on to the dashboard. */
function NoMoreQuestions({ state }: { state: ClientState }) {
  const { t } = useI18n();
  const session = useSession();
  return (
    <>
      <DoneBadge index={0} total={0} />
      <AssistantLine>{t.journey.end.none}</AssistantLine>
      <div className={styles.next}>
        {state.completeness.ready ? (
          <button type="button" className={`${styles.cta} ${styles.ctaSmall}`} onClick={() => void session.reply({ stop: true })} disabled={Boolean(session.pending)}>
            {t.journey.end.stop}
          </button>
        ) : null}
        <Link href="/dashboard" className={styles.ghost}>
          {t.journey.end.later}
        </Link>
      </div>
    </>
  );
}

/** The profile is complete: Yan in full, and the way on to the dashboard. */
function ProfileReady({ onRestart }: { onRestart: () => void }) {
  const { t } = useI18n();
  const session = useSession();
  const signedIn = useAccount().status === "signed_in";
  return (
    <>
      <div className={styles.ready}>
        <YanFigure height={112} arrive="last" cheer />
        <div>
          <p className={styles.kicker}>
            <CircleCheck aria-hidden />
            {t.journey.end.done}
          </p>
          <h2>{t.journey.end.titleComplete}</h2>
        </div>
      </div>
      <p className={styles.lead}>
        {t.journey.end.sayComplete} {t.journey.end.leadComplete}
      </p>
      <div className={styles.next}>
        <Link href="/dashboard" className={`${styles.cta} ${styles.ctaSmall}`}>
          {t.journey.end.toDashboard}
        </Link>
        {/* An account has one profile: there is nothing to start over. */}
        {signedIn ? null : (
          <button type="button" className={styles.ghost} onClick={onRestart} disabled={Boolean(session.pending)}>
            {t.journey.end.restart}
          </button>
        )}
      </div>
    </>
  );
}

/** Yan opens the follow-ups on its own, once, when nothing has been said yet (a failure is retried from the notice). */
function useAutoStart(state: ClientState) {
  const session = useSession();
  const started = useRef(false);
  const shouldStart = state.stage === "followups" && session.conversation.length === 0 && !session.pending && !session.error;
  useEffect(() => {
    if (!shouldStart || started.current) return;
    started.current = true;
    void session.reply({});
  }, [shouldStart, session]);
}

/**
 * At the house the base questionnaire is over, and Yan (A1) takes over with questions
 * made from the answers, asked in the same cards as the base questions.
 */
export function FollowupStage({ state, visible, interacted, onRestart }: FollowupProps) {
  const session = useSession();
  useAutoStart(state);
  if (state.stage === "complete") return <ProfileReady onRestart={onRestart} />;
  const replying = session.pending === "followup.reply";
  const failed = Boolean(session.error) && session.errorAction === "followup.reply";
  if (replying || failed || session.conversation.length === 0) return <Thinking first={session.conversation.length === 0} />;
  if (state.questions.length === 0) return <NoMoreQuestions state={state} />;
  const lastAgent = session.conversation.findLast((entry) => entry.role === "agent");
  return (
    <FollowupBatch
      key={state.questions.map((question) => question.id).join("|")}
      state={state}
      visible={visible}
      interacted={interacted}
      message={lastAgent?.role === "agent" ? lastAgent.message : null}
    />
  );
}
