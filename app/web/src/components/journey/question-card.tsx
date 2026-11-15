"use client";

import { ArrowRight, Check } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import type { AnswerValue, Question } from "@/lib/contract/schemas";
import { draftToValue, emptyDraft, type Draft } from "@/lib/client/answers";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { shortcutIndex } from "@/lib/journey/path";
import { curly } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/components/ui/cn";
import s from "./journey.module.css";

/** The draft lets a picked answer show for a moment before the walker sets off. */
const PICK_DELAY_MS = 280;

interface Choice {
  key: string;
  label: string;
  value: AnswerValue;
}

/** Options answered in one click: single choice, yes / no, and scale steps. */
function choicesOf(question: Question, t: Dictionary): Choice[] | null {
  switch (question.kind) {
    case "single_choice":
      return (question.options ?? []).map((option) => ({ key: option.value, label: curly(option.label), value: option.value }));
    case "boolean":
      return [
        { key: "true", label: t.question.yes, value: true },
        { key: "false", label: t.question.no, value: false },
      ];
    case "scale": {
      const min = question.min ?? 1;
      const max = question.max ?? 10;
      const count = Math.max(0, Math.min(21, max - min + 1));
      return Array.from({ length: count }, (_, index) => {
        const step = min + index;
        return { key: String(step), label: String(step), value: step };
      });
    }
    default:
      return null;
  }
}

const isTyping = (target: EventTarget | null) =>
  target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement;

/**
 * One base question as the draft's card: the assistant's line, the question, the
 * answers (keys 1 to 9 pick them), and « Pourquoi cette question ? » from `help`.
 */
export function QuestionCard({
  question,
  say,
  busy,
  autoFocus,
  onAnswer,
  children,
}: {
  question: Question;
  say: string;
  busy: boolean;
  autoFocus: boolean;
  onAnswer: (value: AnswerValue) => void;
  /** Error notice of the last attempt, rendered under the answers. */
  children?: ReactNode;
}) {
  const { t, locale } = useI18n();
  const headingId = useId();
  const helpId = useId();
  const errorId = useId();
  const [draft, setDraft] = useState<Draft>(() => emptyDraft(question));
  const [picked, setPicked] = useState<string | null>(null);
  const [delaying, setDelaying] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const firstRef = useRef<HTMLElement | null>(null);
  const timer = useRef<number | null>(null);
  const locked = busy || delaying;
  const choices = useMemo(() => choicesOf(question, t), [question, t]);
  const options = useMemo(() => question.options ?? [], [question]);

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );

  useEffect(() => {
    if (autoFocus) firstRef.current?.focus({ preventScroll: true });
  }, [autoFocus]);

  const pick = (choice: Choice) => {
    if (locked) return;
    setPicked(choice.key);
    setDelaying(true);
    setProblem(null);
    timer.current = window.setTimeout(() => {
      timer.current = null;
      setDelaying(false);
      onAnswer(choice.value);
    }, PICK_DELAY_MS);
  };

  const toggle = (value: string) => {
    if (locked) return;
    setProblem(null);
    setDraft((current) => {
      const selected = Array.isArray(current) ? current : [];
      return selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value];
    });
  };

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (locked) return;
    const result = draftToValue(question, draft, t, locale);
    if (!result.ok) {
      setProblem(result.error);
      return;
    }
    setProblem(null);
    onAnswer(result.value);
  };

  // Keys 1 to 9: pick an option, or toggle one for a multiple choice.
  useEffect(() => {
    const keyed = question.kind === "multi_choice" ? options.map((option) => option.value) : (choices ?? []);
    if (keyed.length === 0) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
      const index = shortcutIndex(event.key, keyed.length);
      if (index === null) return;
      event.preventDefault();
      const target = keyed[index];
      if (target === undefined) return;
      if (typeof target === "string") toggle(target);
      else pick(target);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const describedBy = [question.help ? helpId : null, problem ? errorId : null].filter(Boolean).join(" ") || undefined;
  const setFirst = (index: number) => (node: HTMLElement | null) => {
    if (index === 0) firstRef.current = node;
  };
  const continueButton = (
    <div className={s.actions}>
      <button type="submit" className={s.primary} disabled={locked}>
        {busy ? t.journey.sending : t.journey.continue}
        <ArrowRight aria-hidden className="size-4" />
      </button>
    </div>
  );

  let body: ReactNode;
  if (choices && question.kind !== "scale") {
    body = (
      <div className={s.answers} role="group" aria-labelledby={headingId} aria-describedby={describedBy}>
        {choices.map((choice, index) => (
          <button
            key={choice.key}
            ref={setFirst(index)}
            type="button"
            className={cn(s.answer, picked === choice.key && s.picked)}
            onClick={() => pick(choice)}
            disabled={locked}
          >
            {index < 9 ? <kbd aria-hidden>{index + 1}</kbd> : null}
            {choice.label}
          </button>
        ))}
      </div>
    );
  } else if (choices) {
    const min = question.min ?? 1;
    const max = question.max ?? 10;
    const endLabel = (step: number, fallback: string) => options.find((option) => option.value === String(step))?.label ?? fallback;
    body = (
      <>
        <div className={s.scale} role="group" aria-labelledby={headingId} aria-describedby={describedBy}>
          {choices.map((choice, index) => (
            <button
              key={choice.key}
              ref={setFirst(index)}
              type="button"
              className={cn(s.answer, picked === choice.key && s.picked)}
              onClick={() => pick(choice)}
              disabled={locked}
              title={options.find((option) => option.value === choice.key)?.label}
            >
              {choice.label}
            </button>
          ))}
        </div>
        <div className={s.scaleEnds} aria-hidden>
          <span>
            {min} · {endLabel(min, t.question.scaleMin)}
          </span>
          <span>
            {endLabel(max, t.question.scaleMax)} · {max}
          </span>
        </div>
      </>
    );
  } else if (question.kind === "multi_choice") {
    const selected = Array.isArray(draft) ? draft : [];
    body = (
      <form onSubmit={submit} noValidate>
        <p className={s.hint}>{t.question.chooseMany}</p>
        <div className={s.answers} role="group" aria-labelledby={headingId} aria-describedby={describedBy}>
          {options.map((option, index) => {
            const on = selected.includes(option.value);
            return (
              <button
                key={option.value}
                ref={setFirst(index)}
                type="button"
                aria-pressed={on}
                className={s.answer}
                onClick={() => toggle(option.value)}
                disabled={locked}
              >
                {index < 9 ? <kbd aria-hidden>{index + 1}</kbd> : null}
                {curly(option.label)}
                {on ? <Check aria-hidden className={s.check} strokeWidth={2.5} /> : null}
              </button>
            );
          })}
        </div>
        {continueButton}
      </form>
    );
  } else if (question.kind === "text") {
    body = (
      <form onSubmit={submit} noValidate>
        <textarea
          ref={(node) => void (firstRef.current = node)}
          className={s.textarea}
          rows={3}
          maxLength={2000}
          value={typeof draft === "string" ? draft : ""}
          onChange={(event) => {
            setDraft(event.target.value);
            setProblem(null);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) submit();
          }}
          aria-labelledby={headingId}
          aria-describedby={describedBy}
          aria-invalid={problem ? true : undefined}
          disabled={locked}
        />
        {continueButton}
      </form>
    );
  } else {
    const unit = question.unit || (question.kind === "money" ? "$" : question.kind === "percent" ? "%" : "");
    body = (
      <form onSubmit={submit} noValidate>
        <div className={s.field}>
          <input
            ref={(node) => void (firstRef.current = node)}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={typeof draft === "string" ? draft : draft === null ? "" : String(draft)}
            onChange={(event) => {
              setDraft(event.target.value);
              setProblem(null);
            }}
            placeholder={question.kind === "money" ? (locale === "fr" ? "50 000" : "50,000") : ""}
            aria-labelledby={headingId}
            aria-describedby={describedBy}
            aria-invalid={problem ? true : undefined}
            disabled={locked}
            style={unit ? { paddingRight: `${Math.max(2.5, unit.length * 0.6 + 1.6)}rem` } : undefined}
          />
          {unit ? (
            <span aria-hidden className={s.unit}>
              {unit}
            </span>
          ) : null}
        </div>
        {continueButton}
      </form>
    );
  }

  return (
    <>
      <div className={s.say}>
        <span className={s.avatar} aria-hidden>
          A
        </span>
        <p>{say}</p>
      </div>
      <h2 id={headingId}>{curly(question.prompt)}</h2>
      {body}
      {problem ? (
        <p id={errorId} role="alert" className={s.error}>
          {problem}
        </p>
      ) : null}
      {children ? <div className={s.notice}>{children}</div> : null}
      {question.help ? (
        <p id={helpId} className={s.why}>
          <b>{t.journey.why}</b> {curly(question.help)}
        </p>
      ) : null}
    </>
  );
}
