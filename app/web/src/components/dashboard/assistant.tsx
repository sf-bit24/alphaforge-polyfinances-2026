"use client";

import { House } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import type { ClientState, Locale } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { useI18n } from "@/lib/i18n/provider";
import { DEMO, DEMO_CHIPS, type DemoKey } from "@/lib/sample/assistant-demo";
import { tr } from "@/lib/sample/portfolio";
import { cn } from "@/components/ui/cn";
import { composeHints, followupsStatus, introCopy, offersFollowups, startsFollowups, type FollowupsStatus } from "./assistant-offer";
import { PendingReply, Thread, ThreadEntries, ThreadNotices, threadView, type ThreadView } from "./assistant-thread";
import styles from "./dashboard.module.css";
import { IntroScene, SuggestionChips, type IntroChip } from "./intro-scene";
import { isDemoKey, useDemoScript, useFollowupForm, useThreadScroll, type FollowupForm } from "./use-assistant";

interface ChipOffer {
  /** The landing scene of a returning investor: back to the conversation so far. */
  resume?: boolean;
  /** « Ask me your follow-up questions » (`offersFollowups`). */
  followups: boolean;
  /** `mock` mode: the draft's demo prompts are offered, except those already played. */
  sample: boolean;
  played: DemoKey[];
  /** Stopping the follow-ups only means something once they have started. */
  stop: boolean;
}

function suggestedChips(offer: ChipOffer, t: Dictionary, locale: Locale): IntroChip[] {
  const list: IntroChip[] = [];
  if (offer.resume) list.push({ key: "resume", label: t.assistant.chipResume, tone: "ok" });
  // Resuming already reaches the follow-ups in progress: one chip, not two.
  if (offer.followups && !offer.resume) list.push({ key: "followups", label: t.assistant.chipFollowups, tone: "ok" });
  if (offer.sample)
    for (const chip of DEMO_CHIPS)
      if (!offer.played.includes(chip.key)) list.push({ key: chip.key, label: tr(DEMO[chip.key].user, locale), tone: chip.trap ? "trap" : undefined });
  if (offer.stop) list.push({ key: "stop", label: t.assistant.chipStop, tone: "ok" });
  return list;
}

/** The intro asks for the missing details during the follow-ups, and opens the conversation afterwards. */
function introTexts(t: Dictionary, view: Pick<ThreadView, "followups">, followupsOffered: boolean) {
  return {
    ...introCopy(t, view.followups, followupsOffered),
    placeholder: t.assistant.placeholder,
    sendLabel: t.assistant.send,
    hint: t.assistant.hintBirds,
  };
}

function MessageForm({ form, replying }: { form: FollowupForm; replying: boolean }) {
  const { t } = useI18n();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void form.send({ stop: false, text: form.message });
  };
  return (
    <form className={styles.form} onSubmit={submit} autoComplete="off">
      <input
        className={styles.input}
        value={form.message}
        onChange={(event) => form.changeMessage(event.target.value)}
        placeholder={t.assistant.placeholder}
        aria-label={t.assistant.inputLabel}
        maxLength={4000}
        disabled={replying}
      />
      <button className={cn(styles.btn, styles.btnPrimary)} type="submit" disabled={replying}>
        {t.assistant.send}
      </button>
    </form>
  );
}

/** The input's hint, and during the follow-ups whether they can be stopped yet: one line each. */
/** The lines under the message field, and the way back to Yan's landing scene. */
function ComposeHint({ followups, completeness, onBack }: { followups: boolean; completeness: ClientState["completeness"]; onBack: () => void }) {
  const { t, locale } = useI18n();
  return (
    <div className="flex items-start justify-between gap-3">
      <div className={styles.hints}>
        {composeHints(t, locale, followups, completeness).map((line) => (
          <p key={line} className={styles.hint}>
            {line}
          </p>
        ))}
      </div>
      <button
        type="button"
        onClick={onBack}
        className="mt-1.5 inline-flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-navy hover:bg-ink-100 focus-visible:outline-2 focus-visible:outline-focus"
      >
        <House aria-hidden className="size-3.5" />
        {t.assistant.backToScene}
      </button>
    </div>
  );
}

function Composer({
  chips,
  chipsDisabled,
  onChip,
  form,
  replying,
  hint,
}: {
  chips: IntroChip[];
  chipsDisabled: boolean;
  onChip: (chip: IntroChip) => void;
  form: FollowupForm;
  replying: boolean;
  hint: ReactNode;
}) {
  return (
    <div className={styles.compose}>
      <div className={styles.composeIn}>
        <SuggestionChips className={styles.chips} chips={chips} disabled={chipsDisabled} onPick={onChip} />
        <MessageForm form={form} replying={replying} />
        {form.problem ? (
          <p role="alert" className={cn(styles.hint, styles.bad)}>
            {form.problem}
          </p>
        ) : null}
        {hint}
      </div>
    </div>
  );
}

/** The landing scene, until the investor writes or picks a chip. */
function AssistantIntro({ view, status, sample, onDone }: { view: ThreadView; status: FollowupsStatus; sample: boolean; onDone: (text: string, chip: string | null) => void }) {
  const { t, locale } = useI18n();
  const session = useSession();
  const followups = offersFollowups("intro", status);
  return (
    <IntroScene
      {...introTexts(t, view, followups)}
      chips={suggestedChips({ resume: session.conversation.length > 0, followups, sample, played: [], stop: false }, t, locale)}
      disabled={Boolean(session.pending)}
      onDone={onDone}
    />
  );
}

/**
 * Yan, the assistant of the dashboard draft. Its conversation is A1's (`followup.reply`):
 * it asks the follow-ups that complete the profile, and answers within the profile's scope.
 * In `mock` mode, the draft's portfolio questions also get their example answers.
 */
export function Assistant({ state, sample }: { state: ClientState; sample: boolean }) {
  const { t, locale } = useI18n();
  const session = useSession();
  // Yan's landing scene opens every visit; a returning investor goes back to the conversation in one click.
  const [intro, setIntro] = useState(true);
  const { demoEntries, demoTyping, playedDemos, playDemo } = useDemoScript();
  const view = threadView(state, session, demoEntries);
  const form = useFollowupForm(view.askQuestions ? state.questions : []);
  const readFromStart = view.askQuestions && !demoTyping && view.entries.at(-1) === view.lastAgent;
  const threadRef = useThreadScroll({ entryCount: view.entries.length, replying: view.replying, demoTyping, streamText: session.streamText, readFromStart });
  const status = followupsStatus(view, session.conversation.length, state.questions.length);

  const act = (chip: string, text: string) => {
    if (chip === "resume") return;
    if (chip === "followups") {
      if (startsFollowups(status)) void session.reply({});
    } else if (chip === "stop") void form.send({ stop: true, text: "" });
    else if (isDemoKey(chip)) playDemo(chip);
    else void form.send({ stop: false, text });
  };

  if (intro) {
    return (
      <AssistantIntro
        view={view}
        status={status}
        sample={sample}
        onDone={(text, chip) => {
          setIntro(false);
          act(chip ?? "", text);
        }}
      />
    );
  }

  const threadOffer = { followups: offersFollowups("thread", status), sample, played: playedDemos, stop: view.followups && state.completeness.ready };
  return (
    <section className={styles.frame} aria-label={t.assistant.conversation}>
      <Thread threadRef={threadRef} sample={sample}>
        <ThreadEntries view={view} questions={state.questions} form={form} onPlayDemo={playDemo} />
        {view.replying || demoTyping ? <PendingReply replying={view.replying} streamText={session.streamText} /> : null}
        <ThreadNotices view={view} questions={state.questions} />
      </Thread>
      <Composer
        chips={suggestedChips(threadOffer, t, locale)}
        chipsDisabled={Boolean(session.pending) || demoTyping}
        onChip={(chip) => act(chip.key, chip.label)}
        form={form}
        replying={view.replying}
        hint={<ComposeHint followups={view.followups} completeness={state.completeness} onBack={() => setIntro(true)} />}
      />
    </section>
  );
}
