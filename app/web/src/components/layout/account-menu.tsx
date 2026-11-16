"use client";

import { CircleUserRound, LogOut, ShieldCheck } from "lucide-react";
import { useAccount } from "@/lib/client/account";
import { useSession } from "@/lib/client/session";
import { useI18n } from "@/lib/i18n/provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/components/ui/cn";

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

/** The account of the top bars: its email, its group, and « Se déconnecter ». Nothing when sign-in is off. */
export function AccountMenu({ className }: { className?: string }) {
  const { t } = useI18n();
  const account = useAccount();
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
      </div>
    </details>
  );
}
