"use client";

import { CircleUserRound, LogOut, ShieldCheck, Trash2 } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { isDeleteConfirmation } from "@/lib/contract/auth";
import { useAccount } from "@/lib/client/account";
import { callMessages, deleteAccount, toApiError, type ApiError } from "@/lib/client/api";
import { useSession } from "@/lib/client/session";
import { useI18n } from "@/lib/i18n/provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/components/ui/cn";
import { Dialog } from "@/components/ui/dialog";
import { ErrorNotice } from "@/components/ui/error-notice";

/**
 * Sign out of this browser: the local session of this client (client_id, traces, conversation) is
 * forgotten first, then the server clears its cookie and sends the browser to Cognito's `/logout`.
 */
export function SignOutForm({ className }: { className?: string }) {
  const { t } = useI18n();
  const session = useSession();
  return (
    <form method="post" action="/api/auth/logout" onSubmit={() => session.forget()} className={className}>
      <Button type="submit" size="sm" variant="secondary" icon={<LogOut aria-hidden className="size-4" />}>
        {t.auth.signOut}
      </Button>
    </form>
  );
}

/** What « Supprimer mon compte » deletes, what stays, and that it is final. */
function DeletionSummary({ id }: { id: string }) {
  const { t } = useI18n();
  const copy = t.auth.deleteAccount;
  return (
    <div id={id} className="space-y-3">
      <p className="text-ink-800">{copy.lead}</p>
      <ul className="list-disc space-y-1 pl-5 text-ink-800">
        {copy.items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <p className="text-ink-600">{copy.kept}</p>
      <p className="font-semibold text-critical-ink">{copy.irreversible}</p>
    </div>
  );
}

/** The deletion call: on success, this client's local session is forgotten and the browser goes to Cognito's `/logout`. */
function useAccountDeletion() {
  const { t, locale } = useI18n();
  const session = useSession();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const run = async (confirmation: string) => {
    setPending(true);
    setError(null);
    try {
      const done = await deleteAccount(confirmation, { locale, messages: callMessages(t) });
      session.forget();
      window.location.assign(done.logout_url);
    } catch (failure) {
      setError(toApiError(failure));
      setPending(false);
    }
  };
  return { pending, error, run, reset: () => setError(null) };
}

const FIELD =
  "mt-1.5 block h-10 w-full rounded-lg border border-line bg-white px-3 font-mono text-ink-950 focus-visible:outline-2 focus-visible:outline-focus disabled:bg-ink-50";

/** « Annuler » and « Supprimer définitivement », the second one only once the word is typed. */
function DialogActions({ pending, ready, onCancel }: { pending: boolean; ready: boolean; onCancel: () => void }) {
  const { t } = useI18n();
  const copy = t.auth.deleteAccount;
  return (
    <div className="flex flex-wrap justify-end gap-2 pt-1">
      <Button variant="secondary" onClick={onCancel} disabled={pending}>
        {copy.cancel}
      </Button>
      <Button
        type="submit"
        variant="danger"
        className="ring-1 ring-critical/40 ring-inset"
        loading={pending}
        disabled={!ready}
        icon={<Trash2 aria-hidden className="size-4" />}
      >
        {pending ? copy.deleting : copy.confirm}
      </Button>
    </div>
  );
}

/** The confirmation: the summary, the word to type, « Annuler » and « Supprimer définitivement ». */
function DeleteAccountDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const copy = t.auth.deleteAccount;
  const [word, setWord] = useState("");
  const deletion = useAccountDeletion();
  const input = useRef<HTMLInputElement>(null);
  const summaryId = useId();
  const ready = isDeleteConfirmation(word);

  // After showModal (the Dialog's own effect runs first): the field to type in, not the close button.
  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  // While a deletion runs, Escape and the backdrop do nothing (Dialog `busy`); if the browser closes it anyway,
  // the state follows, and the menu's button opens it again on the same run.
  const close = () => {
    if (!deletion.pending) {
      setWord("");
      deletion.reset();
    }
    onClose();
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (ready && !deletion.pending) void deletion.run(word);
  };

  return (
    <Dialog open={open} onClose={close} title={copy.title} size="md" busy={deletion.pending}>
      <form onSubmit={submit} className="space-y-4 text-sm" aria-describedby={summaryId}>
        <DeletionSummary id={summaryId} />
        <label className="block font-medium text-ink-900">
          {copy.confirmLabel(copy.word)}
          <input
            ref={input}
            value={word}
            onChange={(event) => setWord(event.target.value)}
            disabled={deletion.pending}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            className={FIELD}
          />
        </label>
        {deletion.error ? <ErrorNotice error={deletion.error} compact /> : null}
        <DialogActions pending={deletion.pending} ready={ready} onCancel={close} />
      </form>
    </Dialog>
  );
}

/**
 * The account of the top bars: its email, its group, « Se déconnecter » and, discreet, « Supprimer mon compte ».
 * Nothing when sign-in is off.
 */
export function AccountMenu({ className }: { className?: string }) {
  const { t } = useI18n();
  const account = useAccount();
  const [deleting, setDeleting] = useState(false);
  if (account.status !== "signed_in") return null;
  const { email, admin } = account.user;
  return (
    <details className={cn("group relative", className)}>
      <summary
        aria-label={t.auth.account}
        title={email ?? t.auth.account}
        className="grid size-8 cursor-pointer list-none place-items-center rounded-md border border-line text-ink-600 transition-colors hover:border-navy hover:text-navy group-open:border-navy group-open:text-navy [&::-webkit-details-marker]:hidden"
      >
        <CircleUserRound aria-hidden className="size-4" />
      </summary>
      <div className="absolute top-10 right-0 z-40 w-72 rounded-lg border border-line bg-white p-4 text-left text-sm shadow-lift">
        <p className="text-xs text-ink-500">{t.auth.signedInAs}</p>
        <p className="mt-0.5 truncate font-medium text-navy" title={email ?? undefined}>
          {email ?? t.auth.noEmail}
        </p>
        {admin ? (
          <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-ink-600">
            <ShieldCheck aria-hidden className="size-3.5" />
            {t.auth.admin}
          </p>
        ) : null}
        <SignOutForm className="mt-3" />
        <div className="mt-3 border-t border-ink-150 pt-2">
          <Button
            size="sm"
            variant="danger"
            className="-ml-2.5"
            aria-haspopup="dialog"
            icon={<Trash2 aria-hidden className="size-4" />}
            onClick={() => setDeleting(true)}
          >
            {t.auth.deleteAccount.open}
          </Button>
        </div>
      </div>
      <DeleteAccountDialog open={deleting} onClose={() => setDeleting(false)} />
    </details>
  );
}
