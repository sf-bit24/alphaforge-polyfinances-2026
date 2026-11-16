"use client";

import { CircleCheck, LogIn } from "lucide-react";
import { useEffect } from "react";
import { Brand } from "@/components/layout/brand";
import { LanguageToggle } from "@/components/layout/language-toggle";
import { useI18n } from "@/lib/i18n/provider";

/** The notice cookie of `/login` (session.ts, `NOTICE_COOKIE`), cleared once shown. */
function clearNotice(): void {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `af_notice=; Path=/login; Max-Age=0; SameSite=Lax${secure}`;
}

/** The sign-in screen: one way in, to Cognito's managed login, in the interface language. */
export function LoginView({ next, error, deleted = false }: { next: string; error: string | null; deleted?: boolean }) {
  const { t } = useI18n();
  const failure = error ? (t.auth.failed[error] ?? t.auth.failed.token) : null;
  useEffect(() => {
    if (deleted) clearNotice();
  }, [deleted]);
  return (
    <main id="main" tabIndex={-1} className="flex min-h-dvh flex-col bg-white focus:outline-none">
      <header className="flex h-16 items-center justify-between border-b border-line px-4 sm:px-8">
        <Brand />
        <LanguageToggle />
      </header>
      <section className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-5 px-6 py-12">
        <h1 className="text-2xl font-semibold tracking-tight text-ink-950">{t.auth.heading}</h1>
        <p className="text-ink-700">{t.auth.lead}</p>
        {deleted ? (
          <p role="status" className="flex items-start gap-2 rounded-lg border border-line bg-soft px-4 py-3 text-sm text-ink-800">
            <CircleCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-navy" />
            {t.auth.deleted}
          </p>
        ) : null}
        {failure ? (
          <p role="alert" className="rounded-lg border border-critical/30 bg-critical-wash px-4 py-3 text-sm text-critical-ink">
            {failure}
          </p>
        ) : null}
        <a
          href={`/api/auth/login?next=${encodeURIComponent(next)}`}
          className="inline-flex items-center justify-center gap-2 self-start rounded-lg bg-navy px-5 py-3 font-medium text-white no-underline transition-colors hover:bg-navy/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          <LogIn aria-hidden className="size-4" />
          {t.auth.button}
        </a>
        <p className="text-sm text-ink-500">{t.auth.note}</p>
      </section>
    </main>
  );
}
