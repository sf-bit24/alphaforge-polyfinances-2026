"use client";

import { ChevronDown, Circle, CircleCheck, CircleDashed, FileJson, FileText, FolderOpen, UserRound } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { ClientState, DimensionStatus, DimensionView, Fact, KbItem, RiskLevel } from "@/lib/contract/schemas";
import { PROFILE_DIMENSIONS } from "@/lib/contract/schemas";
import { listKb } from "@/lib/client/api";
import { useSession } from "@/lib/client/session";
import { useAsync } from "@/lib/client/use-async";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { formatDateTime, formatTime } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { DocumentDialog } from "@/components/kb/document-view";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Spinner } from "@/components/ui/spinner";
import { ClientKbStatusCard } from "./client-kb-status";
import { CompletenessMeter, KnowledgeMeter, RiskMeter } from "./meters";

export function provenanceLabel(provenance: string, t: Dictionary): string {
  const [kind, ref = ""] = provenance.split(":");
  if (kind === "base") return t.provenance.base(ref);
  if (kind === "a1") return t.provenance.a1(ref);
  if (kind === "a2") return t.provenance.a2(ref);
  if (kind === "settings") return t.provenance.settings;
  return provenance;
}

const STATUS_ICON: Record<DimensionStatus, ReactNode> = {
  known: <CircleCheck aria-hidden className="size-4 text-good" />,
  partial: <CircleDashed aria-hidden className="size-4 text-serious" />,
  missing: <Circle aria-hidden className="size-4 text-ink-300" />,
};

const STATUS_TEXT: Record<DimensionStatus, string> = {
  known: "text-good-ink",
  partial: "text-serious-ink",
  missing: "text-ink-500",
};

function DimensionRow({ label, view }: { label: string; view: DimensionView }) {
  const { t } = useI18n();
  return (
    <li className="flex items-start gap-2.5 py-2.5">
      <span className="mt-0.5">{STATUS_ICON[view.status]}</span>
      <div className="min-w-0 flex-1">
        <p className="flex items-baseline justify-between gap-2 text-sm">
          <span className="font-medium text-ink-900">{label}</span>
          <span className={cn("text-[0.7rem] font-medium", STATUS_TEXT[view.status])}>{t.dimensionStatus[view.status]}</span>
        </p>
        <p className="mt-0.5 text-[0.8rem] leading-snug text-ink-600">{view.summary ?? "—"}</p>
      </div>
    </li>
  );
}

/** The five dimensions, then `context` (existing portfolio) when the runtime sends it. */
export function DimensionList({ profile }: { profile: ClientState["profile"] }) {
  const { t } = useI18n();
  const context = profile.dimensions.context;
  return (
    <ul className="divide-y divide-ink-150">
      {PROFILE_DIMENSIONS.map((key) => (
        <DimensionRow key={key} label={t.dimensions[key]} view={profile.dimensions[key]} />
      ))}
      {context ? <DimensionRow label={t.dimensions.context} view={context} /> : null}
    </ul>
  );
}

/** Caption of the risk meter: tolerance and capacity when `ProfileView.risk` is present. */
export function riskCaption(profile: ClientState["profile"], t: Dictionary): string {
  const risk = profile.risk;
  if (!risk || (!risk.tolerance && !risk.capacity)) return t.panel.riskCaption;
  const level = (value: RiskLevel | null) => (value ? t.riskLevels[value] : t.panel.toDetermine).toLowerCase();
  return t.panel.riskDetail(level(risk.tolerance), level(risk.capacity));
}

function shortValue(value: unknown): string {
  if (typeof value === "string") return value;
  const text = JSON.stringify(value);
  return text.length > 60 ? `${text.slice(0, 57)}…` : text;
}

function FactsList({ facts }: { facts: Fact[] }) {
  const { t, locale } = useI18n();
  if (facts.length === 0) return <p className="text-sm text-ink-500">{t.panel.noFacts}</p>;
  return (
    <ul className="space-y-2">
      {[...facts].reverse().map((fact) => (
        <li key={`${fact.field}-${fact.at}`} className="rounded-lg bg-ink-50 px-3 py-2 ring-1 ring-ink-150">
          <p className="flex items-center justify-between gap-2">
            <span className="truncate font-mono text-[0.7rem] text-ink-600">{fact.field}</span>
            <time dateTime={fact.at} className="shrink-0 text-[0.7rem] text-ink-400" title={formatDateTime(fact.at, locale)}>
              {formatTime(fact.at, locale)}
            </time>
          </p>
          <p className="mt-0.5 text-sm font-medium break-words text-ink-900">{shortValue(fact.value)}</p>
          <Badge tone="outline" className="mt-1 font-mono">
            {provenanceLabel(fact.provenance, t)}
          </Badge>
        </li>
      ))}
    </ul>
  );
}

function Section({
  title,
  children,
  defaultOpen = false,
  icon,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  icon?: ReactNode;
}) {
  return (
    <details open={defaultOpen} className="group border-t border-ink-150 px-5 py-3">
      <summary className="flex items-center gap-2 rounded text-sm font-semibold text-ink-900 focus-visible:outline-2 focus-visible:outline-focus">
        {icon}
        <span className="flex-1">{title}</span>
        <ChevronDown aria-hidden className="size-4 text-ink-400 transition-transform group-open:rotate-180" />
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}

interface DocumentRowProps {
  item: KbItem;
  /** The client's folder, left out of the key shown under the title. */
  prefix: string;
  json?: boolean;
  onOpen: (item: KbItem) => void;
}

function DocumentRow({ item, prefix, json = false, onOpen }: DocumentRowProps) {
  const { t } = useI18n();
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(item)}
        aria-label={t.panel.open(item.title ?? item.key)}
        className="flex w-full items-start gap-2.5 rounded-lg px-2 py-2 text-left hover:bg-ink-50 focus-visible:outline-2 focus-visible:outline-focus"
      >
        {json ? (
          <FileJson aria-hidden className="mt-0.5 size-4 shrink-0 text-ink-400" />
        ) : (
          <FileText aria-hidden className="mt-0.5 size-4 shrink-0 text-navy" />
        )}
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-ink-900">{item.title ?? item.key.split("/").pop()}</span>
          <span className="block truncate font-mono text-[0.7rem] text-ink-500">{item.key.replace(prefix, "")}</span>
        </span>
        {item.type && !json ? (
          <Badge tone="outline" className="mt-0.5">
            {item.type}
          </Badge>
        ) : null}
      </button>
    </li>
  );
}

function TracesList({ traces, prefix, onOpen }: { traces: KbItem[]; prefix: string; onOpen: (item: KbItem) => void }) {
  const { t } = useI18n();
  return (
    <details className="mt-2">
      <summary className="text-xs font-medium text-ink-600 hover:text-ink-900">{t.panel.traces(traces.length)}</summary>
      <ul className="-mx-2 mt-1 max-h-56 space-y-0.5 overflow-y-auto">
        {traces.map((item) => (
          <DocumentRow key={item.key} item={item} prefix={prefix} json onOpen={onOpen} />
        ))}
      </ul>
    </details>
  );
}

/** The client's documents and traces, reloaded after every request (`revision`) and on a change of language. */
function useClientDocuments(clientId: string, revision: number) {
  const { t, locale } = useI18n();
  const prefix = `clients/${clientId}/`;
  const { data, error, previous } = useAsync(`${prefix}|${revision}|${locale}`, (signal) =>
    listKb(prefix, clientId, {
      locale,
      signal,
      messages: { network: t.errors.network, invalidResponse: t.errors.invalidResponse, noResult: t.errors.noResult },
    }),
  );
  const items = (data ?? previous)?.items ?? [];
  return {
    prefix,
    error,
    loading: !data && !previous && !error,
    empty: items.length === 0 && Boolean(data || previous),
    docs: items.filter((item) => !item.key.includes("/traces/")),
    traces: items.filter((item) => item.key.includes("/traces/")).reverse(),
  };
}

function DocumentsSection({ clientId, revision }: { clientId: string; revision: number }) {
  const { t } = useI18n();
  const [open, setOpen] = useState<KbItem | null>(null);
  const { prefix, error, loading, empty, docs, traces } = useClientDocuments(clientId, revision);
  return (
    <>
      {error ? <ErrorNotice error={error} compact /> : null}
      {loading ? <Spinner label={t.common.loading} /> : null}
      {empty ? <p className="text-sm text-ink-500">{t.panel.noDocuments}</p> : null}
      <ul className="-mx-2 space-y-0.5">
        {docs.map((item) => (
          <DocumentRow key={item.key} item={item} prefix={prefix} onOpen={setOpen} />
        ))}
      </ul>
      {traces.length > 0 ? <TracesList traces={traces} prefix={prefix} onOpen={setOpen} /> : null}
      <DocumentDialog
        documentKey={open?.key ?? null}
        title={open?.title ?? open?.key ?? ""}
        clientId={clientId}
        onClose={() => setOpen(null)}
      />
    </>
  );
}

/** The always-visible profile: completeness, level, risk, dimensions, facts, documents. */
export function ProfilePanel({ state }: { state: ClientState }) {
  const { t } = useI18n();
  const session = useSession();
  const { profile, completeness } = state;
  return (
    <div className="overflow-hidden rounded-xl bg-surface shadow-card ring-1 ring-ink-200/80">
      <header className="flex items-center gap-2 px-5 pt-4">
        <UserRound aria-hidden className="size-4 text-navy" />
        <h2 className="flex-1 text-[0.95rem] font-semibold tracking-tight text-ink-950">{t.panel.title}</h2>
        <span className="font-mono text-[0.7rem] text-ink-400" title={state.client_id}>
          {t.session.id} {state.client_id.slice(0, 8)}
        </span>
      </header>
      <div className="px-5 pt-4 pb-5">
        <CompletenessMeter completeness={completeness} />
        <div className="mt-5 grid grid-cols-2 gap-4">
          <KnowledgeMeter level={profile.knowledge_level} />
          <RiskMeter level={profile.effective_risk} />
        </div>
        <p className="mt-2 text-xs text-ink-500">{riskCaption(profile, t)}</p>
      </div>
      <Section title={t.panel.dimensions} defaultOpen>
        <DimensionList profile={profile} />
      </Section>
      <Section title={t.panel.missing} defaultOpen={completeness.missing.length > 0}>
        {completeness.missing.length === 0 ? (
          <p className="text-sm text-good-ink">{t.panel.missingNone}</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {completeness.missing.map((item) => (
              <li key={`${item.dimension}.${item.field}`}>
                <Badge tone="outline" title={`${t.dimensions[item.dimension]} · ${item.field}`}>
                  {item.label}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title={t.panel.facts(profile.facts.length)}>
        <FactsList facts={profile.facts} />
      </Section>
      <Section title={t.panel.documentsTitle} icon={<FolderOpen aria-hidden className="size-4 text-ink-500" />} defaultOpen>
        {state.client_kb ? <ClientKbStatusCard kb={state.client_kb} /> : null}
        <DocumentsSection clientId={state.client_id} revision={session.revision} />
      </Section>
    </div>
  );
}
