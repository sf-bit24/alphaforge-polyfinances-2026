"use client";

import { Check, X } from "lucide-react";
import type { Question } from "@/lib/contract/schemas";
import { questionDomId, type Draft } from "@/lib/client/answers";
import { curly } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/components/ui/cn";

interface AnswerInputProps {
  question: Question;
  draft: Draft;
  onChange: (draft: Draft) => void;
  disabled?: boolean;
  /** Id of the element that names the question (its legend). */
  labelledBy: string;
  describedBy?: string;
  invalid?: boolean;
  autoFocus?: boolean;
}

const OPTION_CARD =
  "group relative flex cursor-pointer items-start gap-3 rounded-lg bg-white px-4 py-3 text-sm text-ink-800 ring-1 ring-inset ring-ink-200 transition " +
  "hover:ring-ink-400 has-checked:bg-soft has-checked:text-ink-950 has-checked:ring-2 has-checked:ring-navy " +
  "has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-focus has-disabled:cursor-not-allowed has-disabled:opacity-60";

const FIELD =
  "block w-full rounded-lg border-0 bg-white px-3.5 py-2.5 text-[0.95rem] text-ink-950 shadow-sm ring-1 ring-inset ring-ink-300 " +
  "placeholder:text-ink-400 focus:ring-2 focus:ring-navy focus:outline-none disabled:bg-ink-50 disabled:text-ink-500 aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-critical";

function Mark({ type }: { type: "radio" | "checkbox" }) {
  return (
    <span
      aria-hidden
      className={cn(
        "mt-0.5 flex size-4 shrink-0 items-center justify-center ring-1 ring-ink-300 transition group-has-checked:bg-navy group-has-checked:ring-navy",
        type === "radio" ? "rounded-full" : "rounded",
      )}
    >
      {type === "radio" ? (
        <span className="size-1.5 rounded-full bg-white opacity-0 group-has-checked:opacity-100" />
      ) : (
        <Check className="size-3 text-white opacity-0 group-has-checked:opacity-100" strokeWidth={3} />
      )}
    </span>
  );
}

/** One input per `Question.kind` (CONTRACTS.md 3.3). */
export function AnswerInput({ question, draft, onChange, disabled, labelledBy, describedBy, invalid, autoFocus }: AnswerInputProps) {
  const { t, locale } = useI18n();
  const name = `q-${questionDomId(question.id)}`;
  const options = question.options ?? [];

  switch (question.kind) {
    case "single_choice":
      return (
        <div role="radiogroup" aria-labelledby={labelledBy} aria-describedby={describedBy} className="grid gap-2 sm:grid-cols-2">
          {options.map((option, index) => (
            <label key={option.value} className={OPTION_CARD}>
              <input
                type="radio"
                name={name}
                value={option.value}
                checked={draft === option.value}
                onChange={() => onChange(option.value)}
                disabled={disabled}
                autoFocus={autoFocus && (draft === option.value || (draft === null && index === 0))}
                className="sr-only"
              />
              <Mark type="radio" />
              <span>{curly(option.label)}</span>
            </label>
          ))}
        </div>
      );
    case "multi_choice": {
      const selected = Array.isArray(draft) ? draft : [];
      return (
        <div role="group" aria-labelledby={labelledBy} aria-describedby={describedBy}>
          <p className="mb-2 text-xs text-ink-500">{t.question.chooseMany}</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {options.map((option, index) => (
              <label key={option.value} className={OPTION_CARD}>
                <input
                  type="checkbox"
                  name={name}
                  value={option.value}
                  checked={selected.includes(option.value)}
                  onChange={(event) =>
                    onChange(event.target.checked ? [...selected, option.value] : selected.filter((item) => item !== option.value))
                  }
                  disabled={disabled}
                  autoFocus={autoFocus && index === 0}
                  className="sr-only"
                />
                <Mark type="checkbox" />
                <span>{curly(option.label)}</span>
              </label>
            ))}
          </div>
        </div>
      );
    }
    case "boolean":
      return (
        <div role="radiogroup" aria-labelledby={labelledBy} aria-describedby={describedBy} className="grid max-w-md grid-cols-2 gap-2">
          {[
            { value: true, label: t.question.yes, icon: <Check aria-hidden className="size-4" /> },
            { value: false, label: t.question.no, icon: <X aria-hidden className="size-4" /> },
          ].map((option, index) => (
            <label key={String(option.value)} className={cn(OPTION_CARD, "items-center justify-center font-medium")}>
              <input
                type="radio"
                name={name}
                checked={draft === option.value}
                onChange={() => onChange(option.value)}
                disabled={disabled}
                autoFocus={autoFocus && index === 0}
                className="sr-only"
              />
              <span className="text-ink-500 group-has-checked:text-navy">{option.icon}</span>
              {curly(option.label)}
            </label>
          ))}
        </div>
      );
    case "scale": {
      const min = question.min ?? 1;
      const max = question.max ?? 10;
      const steps = Array.from({ length: Math.max(0, Math.min(21, max - min + 1)) }, (_, index) => min + index);
      const optionLabel = (step: number) => question.options?.find((option) => option.value === String(step))?.label;
      return (
        <div role="radiogroup" aria-labelledby={labelledBy} aria-describedby={describedBy}>
          <div className="flex flex-wrap gap-1.5">
            {steps.map((step, index) => (
              <label
                key={step}
                title={optionLabel(step)}
                className={cn(
                  "relative flex size-11 cursor-pointer items-center justify-center rounded-lg bg-white text-sm font-semibold text-ink-700 ring-1 ring-inset ring-ink-200 transition",
                  "hover:ring-ink-400 has-checked:bg-navy has-checked:text-white has-checked:ring-navy",
                  "has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-focus has-disabled:opacity-60",
                )}
              >
                <input
                  type="radio"
                  name={name}
                  checked={draft === step}
                  onChange={() => onChange(step)}
                  disabled={disabled}
                  autoFocus={autoFocus && (draft === step || (draft === null && index === 0))}
                  className="sr-only"
                />
                {step}
              </label>
            ))}
          </div>
          <div className="mt-2 flex max-w-[34rem] justify-between text-xs text-ink-500">
            <span>
              {t.question.scaleMin} · {min}
            </span>
            <span>
              {max} · {t.question.scaleMax}
            </span>
          </div>
        </div>
      );
    }
    case "percent": {
      const text = typeof draft === "string" ? draft : draft === null ? "" : String(draft);
      const numeric = Number(text.replace(",", "."));
      return (
        <div className="flex max-w-xl flex-col gap-3 sm:flex-row sm:items-center">
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={Number.isFinite(numeric) && text !== "" ? Math.min(100, Math.max(0, numeric)) : 0}
            onChange={(event) => onChange(event.target.value)}
            disabled={disabled}
            aria-labelledby={labelledBy}
            aria-valuetext={`${text || 0} %`}
            className="h-2 w-full flex-1 cursor-pointer accent-navy"
          />
          <div className="relative w-32">
            <input
              type="text"
              inputMode="decimal"
              value={text}
              onChange={(event) => onChange(event.target.value)}
              disabled={disabled}
              aria-labelledby={labelledBy}
              aria-describedby={describedBy}
              aria-invalid={invalid || undefined}
              autoFocus={autoFocus}
              className={cn(FIELD, "pr-8 text-right tabular-nums")}
            />
            <span aria-hidden className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-ink-500">
              %
            </span>
          </div>
        </div>
      );
    }
    case "number":
    case "money": {
      const text = typeof draft === "string" ? draft : draft === null ? "" : String(draft);
      const unit = question.unit || (question.kind === "money" ? "CAD" : "");
      return (
        <div className="relative max-w-xs">
          <input
            type="text"
            inputMode="decimal"
            value={text}
            onChange={(event) => onChange(event.target.value)}
            disabled={disabled}
            aria-labelledby={labelledBy}
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            autoFocus={autoFocus}
            placeholder={question.kind === "money" ? (locale === "fr" ? "50 000" : "50,000") : ""}
            className={cn(FIELD, "tabular-nums", unit ? "pr-20" : "")}
          />
          {unit ? (
            <span aria-hidden className="pointer-events-none absolute inset-y-0 right-3.5 flex items-center text-sm text-ink-500">
              {unit}
            </span>
          ) : null}
        </div>
      );
    }
    case "text": {
      const text = typeof draft === "string" ? draft : "";
      return (
        <div>
          <textarea
            value={text}
            onChange={(event) => onChange(event.target.value)}
            disabled={disabled}
            rows={3}
            maxLength={2000}
            aria-labelledby={labelledBy}
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            autoFocus={autoFocus}
            className={cn(FIELD, "resize-y")}
          />
          <p className="mt-1 text-right text-xs text-ink-500 tabular-nums">{t.question.chars(text.length)}</p>
        </div>
      );
    }
  }
}
