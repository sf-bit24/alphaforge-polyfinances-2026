"use client";

import { CircleAlert, MessageSquareWarning, RefreshCw, ShieldCheck, X } from "lucide-react";
import type { ApiError } from "@/lib/client/api";
import { useI18n } from "@/lib/i18n/provider";
import { Button } from "./button";
import { cn } from "./cn";
import { JsonView } from "./json-view";

type CalmNotice = { title: string; hint: string } | undefined;

function hasDetails(details: unknown): boolean {
  return details !== undefined && details !== null && !(typeof details === "object" && Object.keys(details as object).length === 0);
}

/** A shield when the guardrail intervened, a speech bubble for the other calm notices, an alert otherwise. */
const NOTICE_ICONS = { guardrail: ShieldCheck, calm: MessageSquareWarning, failure: CircleAlert } as const;

function noticeKind(code: string, calm: CalmNotice): keyof typeof NOTICE_ICONS {
  if (code === "guardrail_blocked") return "guardrail";
  return calm ? "calm" : "failure";
}

function NoticeTitle({ code, calm }: { code: string; calm: CalmNotice }) {
  const { t } = useI18n();
  return (
    <p className={cn("font-semibold", calm ? "text-warning-ink" : "text-critical-ink")}>
      {calm?.title ?? t.errors.title}
      <span
        className={cn(
          "ml-2 inline-flex items-center rounded bg-white/70 px-1.5 py-0.5 font-mono text-xs font-medium ring-1",
          calm ? "text-warning-ink ring-warning/40" : "text-critical-ink ring-critical/25",
        )}
      >
        {t.errors.code} : {code}
      </span>
    </p>
  );
}

function NoticeDetails({ details }: { details: unknown }) {
  const { t } = useI18n();
  return (
    <details className="mt-2">
      <summary className="text-xs font-medium text-ink-600 underline-offset-2 hover:underline">{t.errors.details}</summary>
      <JsonView value={details} className="mt-2 bg-white" maxHeight="max-h-48" />
    </details>
  );
}

function RetryButton({ onRetry }: { onRetry: () => void }) {
  const { t } = useI18n();
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <Button size="sm" variant="secondary" icon={<RefreshCw aria-hidden className="size-3.5" />} onClick={onRetry}>
        {t.common.retry}
      </Button>
    </div>
  );
}

function DismissButton({ onDismiss }: { onDismiss: () => void }) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      onClick={onDismiss}
      className="rounded p-1 text-ink-500 hover:bg-white/60 hover:text-ink-800 focus-visible:outline-2 focus-visible:outline-focus"
      aria-label={t.common.dismiss}
    >
      <X aria-hidden className="size-4" />
    </button>
  );
}

/**
 * An error from the gateway or a runtime: its code, its message, and the details.
 * `guardrail_blocked` (guardrail intervened) and `model_error` (content filtered, refusal, model down)
 * get a calm notice of their own: they are expected outcomes, not failures of the application.
 */
export function ErrorNotice({
  error,
  onRetry,
  onDismiss,
  className,
  compact = false,
}: {
  error: Pick<ApiError, "code" | "message" | "details">;
  onRetry?: () => void;
  onDismiss?: () => void;
  className?: string;
  compact?: boolean;
}) {
  const { t } = useI18n();
  const calm = t.errors.calm[error.code];
  const hint = calm?.hint ?? t.errors.hints[error.code];
  const guardrail = error.code === "guardrail_blocked";
  const Icon = NOTICE_ICONS[noticeKind(error.code, calm)];
  return (
    <div
      role="alert"
      className={cn(
        "animate-fade-in rounded-lg border p-4 text-sm",
        calm ? "border-warning/40 bg-warning-wash" : "border-critical/30 bg-critical-wash",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <Icon aria-hidden className={cn("mt-0.5 size-5 shrink-0", calm ? "text-warning-ink" : "text-critical")} />
        <div className="min-w-0 flex-1">
          <NoticeTitle code={error.code} calm={calm} />
          <p className="mt-1 text-ink-800">{error.message}</p>
          {hint && hint !== error.message && !compact ? <p className="mt-1 text-ink-600">{hint}</p> : null}
          {hasDetails(error.details) && !compact ? <NoticeDetails details={error.details} /> : null}
          {/* Resending a message the guardrail blocked would be blocked again: the investor rephrases instead. */}
          {onRetry && !guardrail ? <RetryButton onRetry={onRetry} /> : null}
        </div>
        {onDismiss ? <DismissButton onDismiss={onDismiss} /> : null}
      </div>
    </div>
  );
}
