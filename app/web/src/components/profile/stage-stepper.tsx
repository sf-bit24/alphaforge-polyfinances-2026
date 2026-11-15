"use client";

import { Check } from "lucide-react";
import type { ClientState } from "@/lib/contract/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/components/ui/cn";

type StepStatus = "done" | "current" | "upcoming" | "skipped";

/** The stage machine of CONTRACTS.md 3.1, as four steps. */
export function StageStepper({ state }: { state: ClientState }) {
  const { t } = useI18n();
  const stage = state.stage;
  const confirmed = state.portfolio?.status === "confirmed";
  const after = stage === "followups" || stage === "complete";
  const steps: Array<{ label: string; status: StepStatus }> = [
    { label: t.stepper.base, status: stage === "base_questions" ? "current" : "done" },
    {
      label: t.stepper.portfolio,
      status:
        stage === "existing_portfolio" || stage === "portfolio_review"
          ? "current"
          : after
            ? confirmed
              ? "done"
              : "skipped"
            : "upcoming",
    },
    { label: t.stepper.followups, status: stage === "followups" ? "current" : stage === "complete" ? "done" : "upcoming" },
    { label: t.stepper.complete, status: stage === "complete" ? "current" : "upcoming" },
  ];
  return (
    <nav aria-label={t.stepper.label}>
      <ol className="flex items-center gap-2">
        {steps.map((step, index) => (
          <li
            key={step.label}
            className={cn("flex items-center gap-2 sm:min-w-0 sm:flex-1", step.status === "current" && "min-w-0 flex-1")}
            aria-current={step.status === "current" ? "step" : undefined}
          >
            <span
              className={cn(
                "flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                step.status === "done" && "bg-brand-600 text-white",
                step.status === "current" && "bg-white text-brand-700 ring-2 ring-brand-500",
                step.status === "upcoming" && "bg-white text-ink-500 ring-1 ring-ink-300",
                step.status === "skipped" && "bg-ink-100 text-ink-500 ring-1 ring-ink-200",
              )}
            >
              {step.status === "done" ? <Check aria-hidden className="size-4" strokeWidth={3} /> : index + 1}
            </span>
            {/* Below sm only the current step keeps a visible label; the others stay readable by screen readers. */}
            <span className={cn("min-w-0", step.status !== "current" && "sr-only sm:not-sr-only")}>
              <span
                className={cn(
                  "block truncate text-sm font-medium",
                  step.status === "current" ? "text-ink-950" : step.status === "done" ? "text-ink-800" : "text-ink-500",
                )}
              >
                {step.label}
              </span>
              <span className="block text-[0.7rem] text-ink-500">
                {step.status === "current" ? t.stepper.current : step.status === "done" ? t.stepper.done : step.status === "skipped" ? t.stepper.skipped : ""}
              </span>
            </span>
            {index < steps.length - 1 ? <span aria-hidden className="hidden h-px min-w-4 flex-1 bg-ink-200 sm:block" /> : null}
          </li>
        ))}
      </ol>
    </nav>
  );
}
