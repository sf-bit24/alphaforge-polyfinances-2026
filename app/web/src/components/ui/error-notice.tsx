"use client";

import { CircleAlert, LogIn, MessageSquareWarning, RefreshCw, ShieldCheck, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useOperator } from "@/lib/client/account";
import type { ApiError } from "@/lib/client/api";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { useI18n } from "@/lib/i18n/provider";
import { Button } from "./button";
import { cn } from "./cn";
import { JsonView } from "./json-view";

type CalmNotice = { title: string; hint: string } | undefined;

/** `details.reason` of a runtime error, when it gives one (`personal_data`: the guardrail refused personal data). */
function reasonOf(details: unknown): string | undefined {
  if (typeof details !== "object" || details === null) return undefined;
  const { reason } = details as { reason?: unknown };
  return typeof reason === "string" ? reason : undefined;
}

/** The calm notice of an error: the one of its `details.reason` when the dictionary has it, else the one of its code. */
export function calmNoticeOf(t: Dictionary, error: Pick<ApiError, "code" | "details">): CalmNotice {
  const calm = t.errors.calm[error.code];
  const reason = reasonOf(error.details);
  return (reason && calm?.reasons?.[reason]) || calm;
}

/**
 * Codes whose message is written for the investor (what to fix in what they sent, or why the
 * responsible framework held a message back). Any other message may name a runtime, a service
 * or a cause: the client gets the dictionary's text instead, the team's view gets the message too.
 */
const CLIENT_MESSAGE_CODES = new Set(["invalid_answer", "bad_request", "guardrail_blocked"]);

/** What the investor reads: the message when it is written for them, else the text of its code. */
function clientText(t: Dictionary, error: Pick<ApiError, "code" | "message">, calm: CalmNotice): string {
  if (CLIENT_MESSAGE_CODES.has(error.code) && error.message) return error.message;
  return calm?.hint ?? t.errors.hints[error.code] ?? t.errors.hints.internal ?? "";
}

function hasDetails(details: unknown): boolean {
  return details !== undefined && details !== null && !(typeof details === "object" && Object.keys(details as object).length === 0);
}

/** A shield when the guardrail intervened, a speech bubble for the other calm notices, an alert otherwise. */
const NOTICE_ICONS = { guardrail: ShieldCheck, calm: MessageSquareWarning, failure: CircleAlert } as const;

function noticeKind(code: string, calm: CalmNotice): keyof typeof NOTICE_ICONS {
  if (code === "guardrail_blocked") return "guardrail";
  return calm ? "calm" : "failure";
}

/** The title; the team's view adds the error code. */
function NoticeTitle({ code, calm, operator }: { code: string; calm: CalmNotice; operator: boolean }) {
  const { t } = useI18n();
  return (
    <p className={cn("font-semibold", calm ? "text-warning-ink" : "text-critical-ink")}>
      {calm?.title ?? t.errors.title}
      {operator ? (
        <span
          className={cn(
            "ml-2 inline-flex items-center rounded bg-white/70 px-1.5 py-0.5 font-mono text-xs font-medium ring-1",
            calm ? "text-warning-ink ring-warning/40" : "text-critical-ink ring-critical/25",
          )}
        >
          {t.errors.code(code)}
        </span>
      ) : null}
    </p>
  );
}

/** Team's view only, compact or not: the raw message (when the client did not read it) and the details, folded. */
function NoticeDetails({ message, details }: { message: string | null; details: unknown }) {
  const { t } = useI18n();
  return (
    <details className="mt-2">
      <summary className="text-xs font-medium text-ink-600 underline-offset-2 hover:underline">{t.errors.details}</summary>
      {message ? <p className="mt-2 font-mono text-xs break-words text-ink-700">{message}</p> : null}
      {hasDetails(details) ? <JsonView value={details} className="mt-2 bg-white" maxHeight="max-h-48" /> : null}
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

/** The session expired (`unauthorized`, CONTRACTS.md 7.1): sign in again, then come back to this page. */
function SignInLink() {
  const { t } = useI18n();
  const pathname = usePathname();
  return (
    <a
      href={`/login?next=${encodeURIComponent(pathname || "/")}`}
      className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-navy px-3 py-1.5 text-sm font-medium text-white no-underline hover:bg-navy/90"
    >
      <LogIn aria-hidden className="size-3.5" />
      {t.auth.signIn}
    </a>
  );
}

/** Retry, or sign in again when the session expired. */
function NoticeAction({ code, onRetry }: { code: string; onRetry?: () => void }) {
  if (code === "unauthorized") return <SignInLink />;
  // Resending a message the guardrail blocked would be blocked again: the investor rephrases instead.
  if (!onRetry || code === "guardrail_blocked") return null;
  return <RetryButton onRetry={onRetry} />;
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
 * An error from the gateway or a runtime, in the investor's words (LANGAGE.md): a title, what happened
 * and what to do; never a code, a runtime or a raw message. The team's view (`useOperator`) adds the
 * code, the raw message and the details, folded.
 * `guardrail_blocked` (guardrail intervened) and `model_error` (content filtered, refusal, model down)
 * get a calm notice of their own: they are expected outcomes, not failures of the application.
 * A refused personal detail (`details.reason` = `personal_data`) gets its own notice, which says nothing of orders or advice.
 * `text` replaces the code's text when the screen knows better what happened (the deletion stopped, say).
 */
export function ErrorNotice({
  error,
  onRetry,
  onDismiss,
  className,
  compact = false,
  text,
}: {
  error: Pick<ApiError, "code" | "message" | "details">;
  onRetry?: () => void;
  onDismiss?: () => void;
  className?: string;
  compact?: boolean;
  text?: string;
}) {
  const { t } = useI18n();
  const operator = useOperator();
  const calm = calmNoticeOf(t, error);
  const shown = text ?? clientText(t, error, calm);
  const hint = calm?.hint ?? t.errors.hints[error.code];
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
          <NoticeTitle code={error.code} calm={calm} operator={operator} />
          <p className="mt-1 text-ink-800">{shown}</p>
          {hint && hint !== shown && !compact ? <p className="mt-1 text-ink-600">{hint}</p> : null}
          {operator ? <NoticeDetails message={shown === error.message ? null : error.message} details={error.details} /> : null}
          <NoticeAction code={error.code} onRetry={onRetry} />
        </div>
        {onDismiss ? <DismissButton onDismiss={onDismiss} /> : null}
      </div>
    </div>
  );
}
