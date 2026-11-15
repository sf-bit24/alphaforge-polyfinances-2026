"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import type { ClientState, Locale } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { formatPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { DEMO, DEMO_CHIPS, type DemoKey } from "@/lib/sample/assistant-demo";
import { tr } from "@/lib/sample/portfolio";
import { cn } from "@/components/ui/cn";
import { PendingReply, Thread, ThreadEntries, ThreadNotices, threadView, type ThreadView } from "./assistant-thread";
import styles from "./dashboard.module.css";
import { IntroScene, SuggestionChips, type IntroChip } from "./intro-scene";
import { isDemoKey, useDemoScript, useFollowupForm, useThreadScroll, type FollowupForm } from "./use-assistant";

interface ChipOffer {
  /** A1's follow-ups can start: follow-up stage, nothing said yet, no reply pending. */
  followups: boolean;
  /** `mock` mode: the draft's demo prompts are offered, except those already played. */
  sample: boolean;
  played: DemoKey[];
  /** Stopping the follow-ups only means something once they have started. */
  stop: boolean;
}

function suggestedChips(offer: ChipOffer, t: Dictionary, locale: Locale): IntroChip[] {
  const list: IntroChip[] = [];
  if (offer.followups) list.push({ key: "followups", label: t.assistant.chipFollowups, tone: "ok" });
  if (offer.sample)
    for (const chip of DEMO_CHIPS)
      if (!offer.played.includes(chip.key)) list.push({ key: chip.key, label: tr(DEMO[chip.key].user, locale), tone: chip.trap ? "trap" : undefined });
  if (offer.stop) list.push({ key: "stop", label: t.assistant.chipStop, tone: "ok" });
  return list;
}

/** The intro asks for the missing details during the follow-ups, and opens the conversation afterwards. */
function introTexts(t: Dictionary, view: Pick<ThreadView, "followups">) {
  return {
    heading: view.followups ? t.assistant.introFollowups : t.assistant.introComplete,
    lead: view.followups ? t.assistant.leadFollowups : t.assistant.leadComplete,
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

/** The input's hint, and during the follow-ups whether they can be stopped yet. */
function ComposeHint({ followups, completeness }: { followups: boolean; completeness: ClientState["completeness"] }) {
  const { t, locale } = useI18n();
  return (
    <p className={styles.hint}>
      {t.assistant.hint}
      {followups ? ` ${completeness.ready ? t.followups.stopHintReady : t.followups.stopHintLocked(formatPercent(completeness.score, locale))}` : ""}
    </p>
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

/**
 * Yan, the assistant of the dashboard draft. Its conversation is A1's (`followup.reply`):
 * it asks the follow-ups that complete the profile, and answers within the profile's scope.
 * In `mock` mode, the draft's portfolio questions also get their example answers.
 */
export function Assistant({ state, sample }: { state: ClientState; sample: boolean }) {
  const { t, locale } = useI18n();
  const session = useSession();
  const [intro, setIntro] = useState(() => session.conversation.length === 0);
  const { demoEntries, demoTyping, playedDemos, playDemo } = useDemoScript();
  const view = threadView(state, session, demoEntries);
  const form = useFollowupForm(view.askQuestions ? state.questions : []);
  const readFromStart = view.askQuestions && !demoTyping && view.entries.at(-1) === view.lastAgent;
  const threadRef = useThreadScroll({ entryCount: view.entries.length, replying: view.replying, demoTyping, streamText: session.streamText, readFromStart });

  const act = (chip: string, text: string) => {
    if (chip === "followups") void session.reply({});
    else if (chip === "stop") void form.send({ stop: true, text: "" });
    else if (isDemoKey(chip)) playDemo(chip);
    else void form.send({ stop: false, text });
  };

  const offer = { followups: view.followups && session.conversation.length === 0 && !view.replying, sample };
  if (intro) {
    return (
      <IntroScene
        {...introTexts(t, view)}
        chips={suggestedChips({ ...offer, played: [], stop: false }, t, locale)}
        disabled={Boolean(session.pending)}
        onDone={(text, chip) => {
          setIntro(false);
          act(chip ?? "", text);
        }}
      />
    );
  }

  return (
    <section className={styles.frame} aria-label={t.assistant.conversation}>
      <Thread threadRef={threadRef} sample={sample}>
        <ThreadEntries view={view} questions={state.questions} form={form} onPlayDemo={playDemo} />
        {view.replying || demoTyping ? <PendingReply replying={view.replying} streamText={session.streamText} /> : null}
        <ThreadNotices view={view} questions={state.questions} />
      </Thread>
      <Composer
        chips={suggestedChips({ ...offer, played: playedDemos, stop: view.followups && state.completeness.ready }, t, locale)}
        chipsDisabled={Boolean(session.pending) || demoTyping}
        onChip={(chip) => act(chip.key, chip.label)}
        form={form}
        replying={view.replying}
        hint={<ComposeHint followups={view.followups} completeness={state.completeness} />}
      />
    </section>
  );
}
