"use client";

import { ArrowRight, Check } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import type { AnswerValue, Question, QuestionKind } from "@/lib/contract/schemas";
import { draftToValue, emptyDraft, type Draft } from "@/lib/client/answers";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { shortcutIndex } from "@/lib/journey/path";
import { curly } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { fieldText, MONEY_PLACEHOLDER } from "@/components/profile/answer-input";
import { cn } from "@/components/ui/cn";
import { AssistantLine } from "./assistant-line";
import styles from "./journey.module.css";

/** The draft lets a picked answer show for a moment before the walker sets off. */
const PICK_DELAY_MS = 280;

/** Unit shown in a numeric field when the question has none. */
const KIND_UNITS: Partial<Record<QuestionKind, string>> = { money: "$", percent: "%" };

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

/** The multiple-choice draft with `value` added, or removed when it was there. */
function toggled(current: Draft, value: string): string[] {
  const selected = Array.isArray(current) ? current : [];
  return selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value];
}

/** The answer being prepared: the draft, the picked option, the problem to show, and how to edit or send it. */
function useAnswerDraft(question: Question, busy: boolean, onAnswer: (value: AnswerValue) => void) {
  const { t, locale } = useI18n();
  const [draft, setDraft] = useState<Draft>(() => emptyDraft(question));
  const [picked, setPicked] = useState<string | null>(null);
  const [delaying, setDelaying] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const locked = busy || delaying;

  const toggle = (value: string) => {
    if (locked) return;
    setProblem(null);
    setDraft((current) => toggled(current, value));
  };

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (locked) return;
    const result = draftToValue(question, draft, t, locale);
    setProblem(result.ok ? null : result.error);
    if (result.ok) onAnswer(result.value);
  };

  const edit = (text: string) => {
    setDraft(text);
    setProblem(null);
  };

  return { draft, picked, setPicked, setDelaying, problem, setProblem, locked, toggle, submit, edit };
}

type AnswerDraft = ReturnType<typeof useAnswerDraft>;

/** The answer buttons: one-click choices (picked, then sent after a pause) and the one focused on arrival. */
function useAnswerOptions(question: Question, draft: AnswerDraft, autoFocus: boolean, onAnswer: (value: AnswerValue) => void) {
  const { t } = useI18n();
  const { locked, setPicked, setDelaying, setProblem } = draft;
  const firstRef = useRef<HTMLElement | null>(null);
  const timer = useRef<number | null>(null);
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

  const setFirst = (index: number) => (node: HTMLElement | null) => {
    if (index === 0) firstRef.current = node;
  };

  return { choices, options, pick, setFirst };
}

/** Keys 1 to 9: pick an option, or toggle one for a multiple choice. */
function useShortcutKeys(keyed: Array<Choice | string>, toggle: (value: string) => void, pick: (choice: Choice) => void) {
  useEffect(() => {
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
}

type Answer = AnswerDraft & ReturnType<typeof useAnswerOptions>;

interface BodyProps {
  question: Question;
  answer: Answer;
  /** Ids naming and describing the answers. */
  aria: { labelledBy: string; describedBy: string | undefined };
  busy: boolean;
}

function ChoiceButtons({ answer, aria, choices }: BodyProps & { choices: Choice[] }) {
  return (
    <div className={styles.answers} role="group" aria-labelledby={aria.labelledBy} aria-describedby={aria.describedBy}>
      {choices.map((choice, index) => (
        <button
          key={choice.key}
          ref={answer.setFirst(index)}
          type="button"
          className={cn(styles.answer, answer.picked === choice.key && styles.picked)}
          onClick={() => answer.pick(choice)}
          disabled={answer.locked}
        >
          {index < 9 ? <kbd aria-hidden>{index + 1}</kbd> : null}
          {choice.label}
        </button>
      ))}
    </div>
  );
}

function ScaleButtons({ question, answer, aria, choices }: BodyProps & { choices: Choice[] }) {
  const { t } = useI18n();
  const { options } = answer;
  const min = question.min ?? 1;
  const max = question.max ?? 10;
  const endLabel = (step: number, fallback: string) => options.find((option) => option.value === String(step))?.label ?? fallback;
  return (
    <>
      <div className={styles.scale} role="group" aria-labelledby={aria.labelledBy} aria-describedby={aria.describedBy}>
        {choices.map((choice, index) => (
          <button
            key={choice.key}
            ref={answer.setFirst(index)}
            type="button"
            className={cn(styles.answer, answer.picked === choice.key && styles.picked)}
            onClick={() => answer.pick(choice)}
            disabled={answer.locked}
            title={options.find((option) => option.value === choice.key)?.label}
          >
            {choice.label}
          </button>
        ))}
      </div>
      <div className={styles.scaleEnds} aria-hidden>
        <span>
          {min} · {endLabel(min, t.question.scaleMin)}
        </span>
        <span>
          {endLabel(max, t.question.scaleMax)} · {max}
        </span>
      </div>
    </>
  );
}

/** The answers typed or ticked before « Continuer ». */
function AnswerForm({ answer, busy, children }: { answer: Answer; busy: boolean; children: ReactNode }) {
  const { t } = useI18n();
  return (
    <form onSubmit={answer.submit} noValidate>
      {children}
      <div className={styles.actions}>
        <button type="submit" className={styles.primary} disabled={answer.locked}>
          {busy ? t.journey.sending : t.journey.continue}
          <ArrowRight aria-hidden className="size-4" />
        </button>
      </div>
    </form>
  );
}

function MultiChoiceForm({ answer, aria, busy }: BodyProps) {
  const { t } = useI18n();
  const selected = Array.isArray(answer.draft) ? answer.draft : [];
  return (
    <AnswerForm answer={answer} busy={busy}>
      <p className={styles.hint}>{t.question.chooseMany}</p>
      <div className={styles.answers} role="group" aria-labelledby={aria.labelledBy} aria-describedby={aria.describedBy}>
        {answer.options.map((option, index) => {
          const isSelected = selected.includes(option.value);
          return (
            <button
              key={option.value}
              ref={answer.setFirst(index)}
              type="button"
              aria-pressed={isSelected}
              className={styles.answer}
              onClick={() => answer.toggle(option.value)}
              disabled={answer.locked}
            >
              {index < 9 ? <kbd aria-hidden>{index + 1}</kbd> : null}
              {curly(option.label)}
              {isSelected ? <Check aria-hidden className={styles.check} strokeWidth={2.5} /> : null}
            </button>
          );
        })}
      </div>
    </AnswerForm>
  );
}

function TextForm({ answer, aria, busy }: BodyProps) {
  return (
    <AnswerForm answer={answer} busy={busy}>
      <textarea
        ref={answer.setFirst(0)}
        className={styles.textarea}
        rows={3}
        maxLength={2000}
        value={typeof answer.draft === "string" ? answer.draft : ""}
        onChange={(event) => answer.edit(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) answer.submit();
        }}
        aria-labelledby={aria.labelledBy}
        aria-describedby={aria.describedBy}
        aria-invalid={answer.problem ? true : undefined}
        disabled={answer.locked}
      />
    </AnswerForm>
  );
}

function NumberForm({ question, answer, aria, busy }: BodyProps) {
  const { locale } = useI18n();
  const unit = question.unit || (KIND_UNITS[question.kind] ?? "");
  return (
    <AnswerForm answer={answer} busy={busy}>
      <div className={styles.field}>
        <input
          ref={answer.setFirst(0)}
          type="text"
          inputMode="decimal"
          autoComplete="off"
          value={fieldText(answer.draft)}
          onChange={(event) => answer.edit(event.target.value)}
          placeholder={question.kind === "money" ? MONEY_PLACEHOLDER[locale] : ""}
          aria-labelledby={aria.labelledBy}
          aria-describedby={aria.describedBy}
          aria-invalid={answer.problem ? true : undefined}
          disabled={answer.locked}
          style={unit ? { paddingRight: `${Math.max(2.5, unit.length * 0.6 + 1.6)}rem` } : undefined}
        />
        {unit ? (
          <span aria-hidden className={styles.unit}>
            {unit}
          </span>
        ) : null}
      </div>
    </AnswerForm>
  );
}

/** The answers of the question's kind. */
function AnswerBody(props: BodyProps) {
  const { question, answer } = props;
  if (answer.choices && question.kind !== "scale") return <ChoiceButtons {...props} choices={answer.choices} />;
  if (answer.choices) return <ScaleButtons {...props} choices={answer.choices} />;
  if (question.kind === "multi_choice") return <MultiChoiceForm {...props} />;
  if (question.kind === "text") return <TextForm {...props} />;
  return <NumberForm {...props} />;
}

interface QuestionCardProps {
  question: Question;
  say: string;
  busy: boolean;
  autoFocus: boolean;
  onAnswer: (value: AnswerValue) => void;
  /** Error notice of the last attempt, rendered under the answers. */
  children?: ReactNode;
}

/**
 * One base question as the draft's card: the assistant's line, the question, the
 * answers (keys 1 to 9 pick them), and « Pourquoi cette question ? » from `help`.
 */
export function QuestionCard({ question, say, busy, autoFocus, onAnswer, children }: QuestionCardProps) {
  const { t } = useI18n();
  const headingId = useId();
  const helpId = useId();
  const errorId = useId();
  const draft = useAnswerDraft(question, busy, onAnswer);
  const answerOptions = useAnswerOptions(question, draft, autoFocus, onAnswer);
  const keyed = question.kind === "multi_choice" ? answerOptions.options.map((option) => option.value) : (answerOptions.choices ?? []);
  useShortcutKeys(keyed, draft.toggle, answerOptions.pick);
  const answer: Answer = { ...draft, ...answerOptions };
  const describedBy = [question.help ? helpId : null, answer.problem ? errorId : null].filter(Boolean).join(" ") || undefined;

  return (
    <>
      <AssistantLine>{say}</AssistantLine>
      <h2 id={headingId}>{curly(question.prompt)}</h2>
      <AnswerBody question={question} answer={answer} aria={{ labelledBy: headingId, describedBy }} busy={busy} />
      {answer.problem ? (
        <p id={errorId} role="alert" className={styles.error}>
          {answer.problem}
        </p>
      ) : null}
      {children ? <div className={styles.notice}>{children}</div> : null}
      {question.help ? (
        <p id={helpId} className={styles.why}>
          <b>{t.journey.why}</b> {curly(question.help)}
        </p>
      ) : null}
    </>
  );
}
