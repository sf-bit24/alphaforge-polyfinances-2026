"use client";

import { Check, Copy, Languages, Server, SlidersHorizontal, UserRound } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import type { ClientState, GatewayHealth, KnowledgeLevel, Locale } from "@/lib/contract/schemas";
import { KNOWLEDGE_LEVELS } from "@/lib/contract/schemas";
import { useAccount, useOperator } from "@/lib/client/account";
import type { AccountUser } from "@/lib/contract/auth";
import { useHealth } from "@/lib/client/health";
import { useSession } from "@/lib/client/session";
import { useI18n } from "@/lib/i18n/provider";
import { SignOutForm } from "@/components/layout/account-menu";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";

const RADIO_CARD =
  "group flex cursor-pointer items-start gap-3 rounded-lg bg-white px-4 py-3 ring-1 ring-ink-200 ring-inset transition hover:ring-ink-400 " +
  "has-checked:bg-soft has-checked:ring-2 has-checked:ring-navy has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-focus " +
  "has-disabled:cursor-not-allowed has-disabled:opacity-60";

function Dot() {
  return (
    <span aria-hidden className="mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full ring-1 ring-ink-300 group-has-checked:bg-navy group-has-checked:ring-navy">
      <span className="size-1.5 rounded-full bg-white opacity-0 group-has-checked:opacity-100" />
    </span>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 py-2.5 sm:grid-cols-[14rem_minmax(0,1fr)]">
      <dt className="text-sm text-ink-500">{label}</dt>
      <dd className="text-sm break-all text-ink-900">{children}</dd>
    </div>
  );
}

function SavedNote() {
  const { t } = useI18n();
  return (
    <span role="status" className="inline-flex items-center gap-1 text-xs font-medium text-good-ink">
      <Check aria-hidden className="size-3.5" />
      {t.settings.saved}
    </span>
  );
}

function LanguageCard({ saved, busy, onSelect }: { saved: boolean; busy: boolean; onSelect: (locale: Locale) => Promise<void> }) {
  const { t, locale } = useI18n();
  return (
    <Card>
      <CardHeader title={t.settings.language} subtitle={t.settings.languageHelp} icon={<Languages aria-hidden className="size-4" />} actions={saved ? <SavedNote /> : null} />
      <div role="radiogroup" aria-label={t.settings.language} className="grid gap-2 px-5 py-4 sm:grid-cols-2">
        {(["fr", "en"] as const).map((option) => (
          <label key={option} className={RADIO_CARD}>
            <input type="radio" name="locale" className="sr-only" checked={locale === option} onChange={() => void onSelect(option)} disabled={busy} />
            <Dot />
            <span>
              <span className="block text-sm font-semibold text-ink-950">{option === "fr" ? "Français" : "English"}</span>
              <span className="block text-xs text-ink-500 uppercase">{option}</span>
            </span>
          </label>
        ))}
      </div>
    </Card>
  );
}

function KnowledgeLevels({ current, busy, onSelect }: { current: KnowledgeLevel | null; busy: boolean; onSelect: (level: KnowledgeLevel) => Promise<void> }) {
  const { t } = useI18n();
  return (
    <div role="radiogroup" aria-label={t.settings.knowledge} className="grid gap-2 px-5 py-4">
      {KNOWLEDGE_LEVELS.map((level) => (
        <label key={level} className={RADIO_CARD}>
          <input
            type="radio"
            name="knowledge"
            className="sr-only"
            checked={current === level}
            onChange={() => void onSelect(level)}
            disabled={busy}
          />
          <Dot />
          <span>
            <span className="block text-sm font-semibold text-ink-950">{t.knowledgeLevels[level]}</span>
            <span className="block text-xs text-ink-600">{t.knowledgeDescriptions[level]}</span>
          </span>
        </label>
      ))}
    </div>
  );
}

/** Three grey rows where the levels will be, while the profile loads. */
function LevelsSkeleton() {
  const { t } = useI18n();
  return (
    <div role="status" aria-label={t.common.loading} className="space-y-2 px-5 py-4">
      <Skeleton className="h-12 w-full rounded-lg" />
      <Skeleton className="h-12 w-full rounded-lg" />
      <Skeleton className="h-12 w-full rounded-lg" />
    </div>
  );
}

/** The level is part of the profile: it needs a session. */
function KnowledgeCard({ state, loading, saved, busy, onSelect }: { state: ClientState | null; loading: boolean; saved: boolean; busy: boolean; onSelect: (level: KnowledgeLevel) => Promise<void> }) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader
        title={t.settings.knowledge}
        subtitle={t.settings.knowledgeHelp}
        icon={<SlidersHorizontal aria-hidden className="size-4" />}
        actions={saved ? <SavedNote /> : null}
      />
      {loading ? <LevelsSkeleton /> : null}
      {!loading && state ? (
        <KnowledgeLevels current={state.profile.knowledge_level} busy={busy} onSelect={onSelect} />
      ) : null}
      {!loading && !state ? (
        <p className="px-5 py-4 text-sm text-ink-600">
          {t.settings.knowledgeNeedsSession}{" "}
          <Link href="/" className="font-medium text-navy underline underline-offset-2">
            {t.home.start}
          </Link>
        </p>
      ) : null}
    </Card>
  );
}

/** Without sign-in: the profile kept in this browser, and « Oublier mon profil sur cet appareil ». */
function SessionCard({ present, onForget }: { present: boolean; onForget: () => void }) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader title={t.settings.session} subtitle={present ? t.settings.sessionHelp : undefined} icon={<UserRound aria-hidden className="size-4" />} />
      <div className="px-5 py-4">
        {present ? (
          <Button size="sm" variant="danger" onClick={onForget}>
            {t.settings.forget}
          </Button>
        ) : (
          <p className="text-sm text-ink-500">{t.settings.sessionNone}</p>
        )}
      </div>
    </Card>
  );
}

/** With sign-in on: the account's email and « Se déconnecter ». */
function AccountCard({ user }: { user: AccountUser }) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader title={t.auth.accountCard} subtitle={t.auth.accountHelp} icon={<UserRound aria-hidden className="size-4" />} />
      <div className="flex flex-wrap items-center gap-3 px-5 py-4">
        <p className="text-sm font-medium text-navy">{user.email ?? t.auth.noEmail}</p>
        <SignOutForm />
      </div>
    </Card>
  );
}

/** Team's view: the client_id this browser works with (the account's when signed in), to copy. */
function ClientIdRow({ clientId, copied, onCopy }: { clientId: string | null; copied: boolean; onCopy: () => void }) {
  const { t } = useI18n();
  if (!clientId) return null;
  return (
    <Row label={t.mode.clientId}>
      <span className="inline-flex flex-wrap items-center gap-2">
        <code className="font-mono text-xs">{clientId}</code>
        <Button size="sm" variant="secondary" onClick={onCopy} icon={copied ? <Check aria-hidden className="size-4" /> : <Copy aria-hidden className="size-4" />}>
          {copied ? t.common.copied : t.common.copy}
        </Button>
      </span>
    </Row>
  );
}

function ModeRow({ health }: { health: GatewayHealth | null }) {
  const { t } = useI18n();
  return (
    <Row label={t.mode.mode}>
      {health ? (
        <span className="inline-flex items-center gap-2">
          <span aria-hidden className={cn("size-2 rounded-full", health.ok ? "bg-good" : "bg-critical")} />
          {t.mode[health.mode]} <code className="font-mono text-xs text-ink-500">AGENT_MODE={health.mode}</code>
        </span>
      ) : (
        t.mode.checking
      )}
    </Row>
  );
}

/** Team's view only (`useOperator`): mode, runtime, release and the client_id. A client never sees it. */
function EnvironmentCard({ health, clientIdRow }: { health: GatewayHealth | null; clientIdRow: ReactNode }) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader title={t.mode.environment} icon={<Server aria-hidden className="size-4" />} />
      <dl className="divide-y divide-ink-150 px-5 py-2">
        <ModeRow health={health} />
        {clientIdRow}
        {health?.agent ? (
          <>
            <Row label={t.mode.runtimeRelease}>
              <code className="font-mono">{health.agent.release}</code>
            </Row>
            <Row label={t.mode.env}>
              <code className="font-mono">
                {health.agent.env} · {health.agent.role}
              </code>
            </Row>
          </>
        ) : null}
        {health?.runtime ? (
          <Row label={t.mode.runtime}>
            <code className="font-mono text-xs">{health.runtime.arn ?? health.runtime.name}</code>
            {health.runtime.status ? <span className="ml-2 text-xs text-ink-500">{health.runtime.status}</span> : null}
          </Row>
        ) : null}
        {health?.error ? (
          <div className="py-3">
            <ErrorNotice error={health.error} compact />
          </div>
        ) : null}
      </dl>
    </Card>
  );
}

export function SettingsView() {
  const { t, locale, setLocale } = useI18n();
  const session = useSession();
  const account = useAccount();
  const operator = useOperator();
  const { health } = useHealth(locale);
  const [saved, setSaved] = useState<"locale" | "knowledge" | null>(null);
  const [copied, setCopied] = useState(false);
  const state = session.state;
  const busy = session.pending === "settings.update";

  const changeLocale = async (next: Locale) => {
    setLocale(next);
    setSaved(null);
    if (state && (await session.updateSettings({ locale: next }))) setSaved("locale");
  };

  const changeLevel = async (level: KnowledgeLevel) => {
    setSaved(null);
    if (await session.updateSettings({ knowledge_level: level })) setSaved("knowledge");
  };

  const copyId = async () => {
    if (!session.clientId) return;
    try {
      await navigator.clipboard.writeText(session.clientId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  const forget = () => {
    if (window.confirm(t.settings.forgetConfirm)) session.forget();
  };

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight text-ink-950">{t.settings.title}</h1>
      {session.error && session.errorAction === "settings.update" ? (
        <ErrorNotice error={session.error} onRetry={session.retry} onDismiss={session.dismissError} />
      ) : null}

      <LanguageCard saved={saved === "locale"} busy={busy} onSelect={changeLocale} />
      <KnowledgeCard state={state} loading={!session.hydrated || (session.resuming && !state)} saved={saved === "knowledge"} busy={busy} onSelect={changeLevel} />
      {account.status === "signed_in" ? (
        <AccountCard user={account.user} />
      ) : (
        <SessionCard present={Boolean(session.clientId)} onForget={forget} />
      )}
      {operator ? <EnvironmentCard health={health} clientIdRow={<ClientIdRow clientId={session.clientId} copied={copied} onCopy={() => void copyId()} />} /> : null}
    </div>
  );
}
