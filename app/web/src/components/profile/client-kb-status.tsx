"use client";

import { DatabaseZap } from "lucide-react";
import type { ClientKb, ClientKbStatus } from "@/lib/contract/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";

const STATUS_TONE: Record<ClientKbStatus, "neutral" | "brand" | "good" | "warning" | "critical"> = {
  disabled: "neutral",
  creating: "brand",
  active: "good",
  failed: "critical",
  quota: "warning",
};

/** The client's own knowledge base (`client_kb`): a search index built from the OKF documents listed below it. The team's view only (ProfilePanel). */
export function ClientKbStatusCard({ kb }: { kb: ClientKb }) {
  const { t } = useI18n();
  const text = t.panel.clientKb;
  return (
    <div className="mb-3 rounded-lg bg-ink-50 px-3 py-2.5 ring-1 ring-ink-150" aria-live="polite">
      <p className="flex items-center gap-2">
        <DatabaseZap aria-hidden className="size-4 shrink-0 text-navy" />
        <span className="flex-1 text-sm font-medium text-ink-900">{text.title}</span>
        <Badge tone={STATUS_TONE[kb.status]}>{text.status[kb.status]}</Badge>
      </p>
      <p className="mt-1 text-xs leading-snug text-ink-600">{text.detail[kb.status]}</p>
      {kb.status !== "disabled" ? (
        <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.7rem] text-ink-500">
          <span>{text.documents(kb.documents)}</span>
          {kb.pending > 0 ? <span>{text.pending(kb.pending)}</span> : null}
          {kb.knowledge_base_id ? (
            <span className="font-mono" title={kb.knowledge_base_id}>
              {text.id} {kb.knowledge_base_id}
            </span>
          ) : null}
        </p>
      ) : null}
      <p className="mt-1.5 text-[0.7rem] leading-snug text-ink-400">{text.caption}</p>
    </div>
  );
}
