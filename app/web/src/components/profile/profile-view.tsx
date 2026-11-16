"use client";

import { FolderOpen, ListChecks, MessageCircle, RotateCcw, Route, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import type { ClientState } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import { useI18n } from "@/lib/i18n/provider";
import { itemForStage } from "@/lib/journey/path";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { cn } from "@/components/ui/cn";
import { SkeletonCard } from "@/components/ui/skeleton";
import { ClientDocuments, DimensionList, FactsList, MissingList, ProfileSummary } from "./profile-panel";

const LINK_BUTTON = {
  base: "inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium whitespace-nowrap no-underline transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
  primary: "bg-brand-600 text-white shadow-sm hover:bg-brand-700 active:bg-brand-800",
  secondary: "bg-white text-ink-800 shadow-sm ring-1 ring-ink-300 ring-inset hover:bg-ink-50 hover:ring-ink-400",
};

function LinkButton({ href, primary, icon, children }: { href: string; primary?: boolean; icon: ReactNode; children: ReactNode }) {
  return (
    <Link href={href} className={cn(LINK_BUTTON.base, primary ? LINK_BUTTON.primary : LINK_BUTTON.secondary)}>
      {icon}
      {children}
    </Link>
  );
}

function Heading({ actions }: { actions?: ReactNode }) {
  const { t } = useI18n();
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        <UserRound aria-hidden className="mt-1 size-6 text-navy" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink-950">{t.profilePage.title}</h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-600">{t.profilePage.lead}</p>
        </div>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/** No profile on this device or account yet: the way to the questionnaire. */
function NoProfile() {
  const { t } = useI18n();
  return (
    <Card className="mt-8 px-6 py-10 text-center">
      <h2 className="text-lg font-semibold text-ink-950">{t.profilePage.noneTitle}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-ink-600">{t.profilePage.noneText}</p>
      <div className="mt-5 flex justify-center">
        <LinkButton href="/" primary icon={<Route aria-hidden className="size-4" />}>
          {t.profilePage.noneCta}
        </LinkButton>
      </div>
    </Card>
  );
}

/** Update with Yan once the base questions are done; until then, back to the questionnaire. Start over, after a confirmation. */
function ProfileActions({ baseDone }: { baseDone: boolean }) {
  const { t } = useI18n();
  const session = useSession();
  const router = useRouter();
  const restart = () => {
    if (!window.confirm(t.journey.end.restartConfirm)) return;
    void session.restart().then((ok) => {
      if (ok) router.push("/");
    });
  };
  return (
    <>
      {baseDone ? (
        <LinkButton href="/dashboard" primary icon={<MessageCircle aria-hidden className="size-4" />}>
          {t.profilePage.update}
        </LinkButton>
      ) : (
        <LinkButton href="/" primary icon={<Route aria-hidden className="size-4" />}>
          {t.profilePage.resume}
        </LinkButton>
      )}
      <Button variant="ghost" icon={<RotateCcw aria-hidden className="size-4" />} onClick={restart} loading={session.pending !== null}>
        {t.profilePage.restart}
      </Button>
    </>
  );
}

function ProfileCards({ state }: { state: ClientState }) {
  const { t } = useI18n();
  const { profile, completeness } = state;
  return (
    <div className="mt-8 grid items-start gap-6 lg:grid-cols-2">
      <div className="space-y-6">
        <Card>
          <CardHeader title={t.profilePage.glance} />
          <div className="px-5 py-5">
            <ProfileSummary state={state} />
          </div>
        </Card>
        <Card>
          <CardHeader title={t.panel.dimensions} />
          <div className="px-5 py-2">
            <DimensionList profile={profile} />
          </div>
        </Card>
        <Card>
          <CardHeader title={t.panel.missing} icon={<ListChecks aria-hidden className="size-4" />} />
          <div className="px-5 py-4">
            <MissingList missing={completeness.missing} />
          </div>
        </Card>
      </div>
      <div className="space-y-6">
        <Card>
          <CardHeader title={t.panel.facts(profile.facts.length)} />
          <div className="max-h-[32rem] overflow-y-auto px-5 py-4">
            <FactsList facts={profile.facts} />
          </div>
        </Card>
        <Card>
          <CardHeader title={t.panel.documentsTitle} icon={<FolderOpen aria-hidden className="size-4" />} />
          <div className="px-5 py-4">
            <ClientDocuments state={state} />
          </div>
        </Card>
      </div>
    </div>
  );
}

/** « Mon profil »: what we know about the investor, in full page, and the ways to change it. */
export function ProfileView() {
  const { t } = useI18n();
  const session = useSession();
  const state = session.state;
  const loading = !session.hydrated || (session.resuming && !state);
  const baseDone = state ? itemForStage(state.stage) === "house" : false;
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
      <Heading actions={state ? <ProfileActions baseDone={baseDone} /> : undefined} />
      {loading ? (
        <div role="status" aria-label={t.session.loading} className="mt-8 grid items-start gap-6 lg:grid-cols-2">
          <div className="space-y-6">
            <SkeletonCard lines={4} />
            <SkeletonCard lines={6} />
          </div>
          <div className="space-y-6">
            <SkeletonCard lines={5} />
            <SkeletonCard lines={2} />
          </div>
        </div>
      ) : null}
      {!loading && !state ? <NoProfile /> : null}
      {!loading && state ? (
        <>
          {baseDone ? null : <p className="mt-6 rounded-lg bg-soft px-4 py-3 text-sm text-navy ring-1 ring-line">{t.profilePage.inProgress}</p>}
          <ProfileCards state={state} />
        </>
      ) : null}
    </div>
  );
}
