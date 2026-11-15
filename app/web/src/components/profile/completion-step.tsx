"use client";

import { ArrowRight, Bot, CircleCheck, FileText, MessageSquare, RotateCcw, Send } from "lucide-react";
import { useId, useState } from "react";
import type { ClientState } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import { formatPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { DocumentDialog } from "@/components/kb/document-view";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Markdown } from "@/components/ui/markdown";
import { ConversationHistory } from "./conversation";
import { KnowledgeMeter, RiskMeter } from "./meters";
import { DimensionList, riskCaption } from "./profile-panel";

/** `complete`: the profile is saved; the investor can refine it or start over. */
export function CompletionStep({ state }: { state: ClientState }) {
  const { t, locale } = useI18n();
  const session = useSession();
  const refineId = useId();
  const [refining, setRefining] = useState(false);
  const [text, setText] = useState("");
  const [showProfile, setShowProfile] = useState(false);
  const sending = session.pending === "followup.reply";

  const refine = async () => {
    if (!text.trim()) return;
    const ok = await session.reply({ message: text });
    if (ok) setText("");
  };

  return (
    <div className="animate-fade-in space-y-5">
      <Card className="overflow-hidden">
        <div className="bg-linear-to-br from-brand-700 to-brand-800 px-6 py-7 text-white">
          <CircleCheck aria-hidden className="size-9 text-brand-200" />
          <h2 className="mt-3 text-2xl font-semibold tracking-tight">{t.completion.title}</h2>
          <p className="mt-1 max-w-xl text-brand-100">{t.completion.lead}</p>
          <p className="mt-4 text-sm font-medium text-white">{t.completion.displayed(formatPercent(state.completeness.displayed, locale))}</p>
          <p className="text-xs text-brand-200">{t.completion.capNote}</p>
        </div>
        {state.message ? (
          <div className="flex gap-3 px-6 py-5">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-kind-agent text-white">
              <Bot aria-hidden className="size-4" />
            </span>
            <Markdown className="min-w-0">{state.message}</Markdown>
          </div>
        ) : null}
      </Card>

      <Card>
        <CardHeader title={t.completion.summary} />
        <div className="grid gap-6 px-5 py-4 md:grid-cols-[1fr_14rem]">
          <DimensionList profile={state.profile} />
          <div className="space-y-5">
            <KnowledgeMeter level={state.profile.knowledge_level} />
            <div>
              <RiskMeter level={state.profile.effective_risk} />
              <p className="mt-2 text-xs text-ink-500">{riskCaption(state.profile, t)}</p>
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <div className="flex flex-wrap gap-2 px-5 py-4">
          <Button variant="primary" onClick={() => setRefining((value) => !value)} aria-expanded={refining} icon={<MessageSquare aria-hidden className="size-4" />}>
            {t.completion.refine}
          </Button>
          <Button variant="secondary" onClick={() => setShowProfile(true)} icon={<FileText aria-hidden className="size-4" />}>
            {t.completion.documents}
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              if (window.confirm(t.home.restartConfirm)) void session.restart();
            }}
            icon={<RotateCcw aria-hidden className="size-4" />}
          >
            {t.completion.restart}
          </Button>
        </div>
        {refining ? (
          <div className="border-t border-ink-150 px-5 py-4">
            <label htmlFor={refineId} className="text-sm font-medium text-ink-900">
              {t.completion.refineLabel}
            </label>
            <textarea
              id={refineId}
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={3}
              maxLength={4000}
              disabled={sending}
              placeholder={t.followups.messagePlaceholder}
              className="mt-1.5 block w-full resize-y rounded-lg border-0 bg-white px-3.5 py-2.5 text-[0.95rem] text-ink-950 shadow-sm ring-1 ring-ink-300 ring-inset placeholder:text-ink-400 focus:ring-2 focus:ring-brand-500 focus:outline-none"
            />
            <div className="mt-3 flex justify-end">
              <Button onClick={() => void refine()} loading={sending} disabled={!text.trim()} icon={<Send aria-hidden className="size-4" />}>
                {t.completion.refineSend}
              </Button>
            </div>
          </div>
        ) : null}
        {session.error && session.errorAction === "followup.reply" ? (
          <div className="px-5 pb-4">
            <ErrorNotice error={session.error} onRetry={session.retry} onDismiss={session.dismissError} />
          </div>
        ) : null}
      </Card>

      {session.conversation.length > 0 ? (
        <Card>
          <details>
            <summary className="flex items-center gap-2 px-5 py-4 text-sm font-semibold text-ink-900 focus-visible:outline-2 focus-visible:outline-brand-500">
              <MessageSquare aria-hidden className="size-4 text-ink-500" />
              {t.followups.title}
            </summary>
            <div className="border-t border-ink-150 bg-ink-50/50 px-5 py-5">
              <ConversationHistory entries={session.conversation} />
            </div>
          </details>
        </Card>
      ) : null}

      <p className="flex items-center gap-2 text-sm text-ink-600">
        <ArrowRight aria-hidden className="size-4 text-brand-500" />
        {t.completion.next}
      </p>

      <DocumentDialog
        documentKey={showProfile ? `clients/${state.client_id}/profil.md` : null}
        title={t.panel.title}
        clientId={state.client_id}
        onClose={() => setShowProfile(false)}
      />
    </div>
  );
}
