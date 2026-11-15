"use client";

import { useEffect, useRef, useState } from "react";
import type { Locale, Question } from "@/lib/contract/schemas";
import { displayAnswer, draftToValue, emptyDraft, isDraftEmpty, type Draft } from "@/lib/client/answers";
import type { ReplyInput } from "@/lib/client/session-store";
import { useSession } from "@/lib/client/session";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { useI18n } from "@/lib/i18n/provider";
import { DEMO, type DemoKey } from "@/lib/sample/assistant-demo";

export type DemoEntry = { id: string; at: string; role: "demo-user"; key: DemoKey } | { id: string; at: string; role: "demo-reply"; key: DemoKey };

const DEMO_DELAY_MS: Partial<Record<DemoKey, number>> = { trap: 1400, sandbox: 1200 };
export const isDemoKey = (value: string): value is DemoKey => value in DEMO;

/** The draft's scripted exchanges (`mock` mode): the prompt shows at once, its answer after a short "typing" delay. */
export function useDemoScript() {
  const [demoEntries, setDemoEntries] = useState<DemoEntry[]>([]);
  const [demoTyping, setDemoTyping] = useState(false);
  const [playedDemos, setPlayedDemos] = useState<DemoKey[]>([]);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((id) => window.clearTimeout(id));
  }, []);

  const playDemo = (key: DemoKey) => {
    setPlayedDemos((current) => (current.includes(key) ? current : [...current, key]));
    setDemoEntries((current) => [...current, { id: crypto.randomUUID(), at: new Date().toISOString(), role: "demo-user", key }]);
    setDemoTyping(true);
    timers.current.push(
      window.setTimeout(() => {
        setDemoEntries((current) => [...current, { id: crypto.randomUUID(), at: new Date().toISOString(), role: "demo-reply", key }]);
        setDemoTyping(false);
      }, DEMO_DELAY_MS[key] ?? 900),
    );
  };

  return { demoEntries, demoTyping, playedDemos, playDemo };
}

/** Answers of the drafts the investor filled in, and the validation error of each invalid one. */
function collectAnswers(questions: Question[], drafts: Record<string, Draft>, t: Dictionary, locale: Locale) {
  const answers: NonNullable<ReplyInput["answers"]> = [];
  const errors: Record<string, string> = {};
  for (const question of questions) {
    const draft = drafts[question.id] ?? emptyDraft(question);
    if (isDraftEmpty(question, draft)) continue;
    const result = draftToValue(question, draft, t, locale);
    if (!result.ok) errors[question.id] = result.error;
    else answers.push({ question_id: question.id, value: result.value, prompt: question.prompt, display: displayAnswer(question, result.value, t, locale) });
  }
  return { answers, errors };
}

/**
 * What the investor sends to A1: the drafts of the questions under its last message
 * (`asked`, empty when none can be answered), the free message, and the problem shown
 * when there is nothing to send.
 */
export function useFollowupForm(asked: Question[]) {
  const { t, locale } = useI18n();
  const session = useSession();
  const [message, setMessage] = useState("");
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState<string | null>(null);

  const changeMessage = (value: string) => {
    setMessage(value);
    if (problem) setProblem(null);
  };

  const changeDraft = (questionId: string, draft: Draft) => {
    setDrafts((current) => ({ ...current, [questionId]: draft }));
    setErrors((current) => {
      if (!(questionId in current)) return current;
      const next = { ...current };
      delete next[questionId];
      return next;
    });
  };

  /** Answers to A1's questions (when filled in), the message, or the request to stop. */
  const send = async ({ stop, text }: { stop: boolean; text: string }) => {
    const { answers, errors: nextErrors } = collectAnswers(asked, drafts, t, locale);
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

  return { message, drafts, errors, problem, changeMessage, changeDraft, send };
}

export type FollowupForm = ReturnType<typeof useFollowupForm>;

interface ThreadScroll {
  entryCount: number;
  replying: boolean;
  demoTyping: boolean;
  streamText: string;
  /** Yan's last message, with open questions, ends the thread: it is read from its start. */
  readFromStart: boolean;
}

/** Keeps the end of the thread in view when an entry, a reply being written or the demo's typing shows up. */
export function useThreadScroll({ entryCount, replying, demoTyping, streamText, readFromStart }: ThreadScroll) {
  const threadRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const thread = threadRef.current;
    if (!thread) return;
    const asking = readFromStart ? thread.querySelector<HTMLElement>("[data-asks]") : null;
    thread.scrollTo({ top: asking ? asking.offsetTop - 12 : thread.scrollHeight, behavior: "smooth" });
  }, [entryCount, replying, demoTyping, streamText, readFromStart]);
  return threadRef;
}


