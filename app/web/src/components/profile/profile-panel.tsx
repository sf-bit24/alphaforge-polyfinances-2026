"use client";

import { ChevronDown, Circle, CircleCheck, CircleDashed, FileText, FolderOpen, UserRound } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { ClientState, Dimension, DimensionStatus, DimensionView, Fact, KbItem, RiskLevel } from "@/lib/contract/schemas";
import { DIMENSIONS, PROFILE_DIMENSIONS } from "@/lib/contract/schemas";
import { useOperator } from "@/lib/client/account";
import { listKb } from "@/lib/client/api";
import { useSession } from "@/lib/client/session";
import { useAsync } from "@/lib/client/use-async";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { factValueText } from "@/lib/fact-value";
import { formatDateTime, formatTime } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { DocumentDialog } from "@/components/kb/document-view";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { SkeletonRows } from "@/components/ui/skeleton";
import { ClientKbStatusCard } from "./client-kb-status";
import { CompletenessMeter, KnowledgeMeter, RiskMeter } from "./meters";

/** Where a fact comes from, in the investor's words; null for an origin the investor has no name for. */
export function provenanceLabel(provenance: string, t: Dictionary): string | null {
  const [kind] = provenance.split(":");
  if (kind === "base") return t.provenance.base;
  if (kind === "a1") return t.provenance.a1;
  if (kind === "a2") return t.provenance.a2;
  if (kind === "settings") return t.provenance.settings;
  return null;
}

/** The dimension a fact belongs to (`objective.goal` → « Objectif »), never the field's own key. */
function factDimension(field: string, t: Dictionary): string | null {
  const dimension = field.split(".")[0] as Dimension;
  return (DIMENSIONS as readonly string[]).includes(dimension) ? t.dimensions[dimension] : null;
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

/** What the investor told us, newest first, each with its dimension and its origin. */
export function FactsList({ facts }: { facts: Fact[] }) {
  const { t, locale } = useI18n();
  if (facts.length === 0) return <p className="text-sm text-ink-500">{t.panel.noFacts}</p>;
  return (
    <ul className="space-y-2">
      {[...facts].reverse().map((fact) => {
        const origin = provenanceLabel(fact.provenance, t);
        return (
          <li key={`${fact.field}-${fact.at}`} className="rounded-lg bg-ink-50 px-3 py-2 ring-1 ring-ink-150">
            <p className="flex items-center justify-between gap-2">
              <span className="truncate text-[0.7rem] font-medium text-ink-600">{factDimension(fact.field, t)}</span>
              <time dateTime={fact.at} className="shrink-0 text-[0.7rem] text-ink-400" title={formatDateTime(fact.at, locale)}>
                {formatTime(fact.at, locale)}
              </time>
            </p>
            <p className="mt-0.5 text-sm font-medium break-words text-ink-900">{factValueText(fact)}</p>
            {origin ? (
              <Badge tone="outline" className="mt-1">
                {origin}
              </Badge>
            ) : null}
          </li>
        );
      })}
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

/** A document of the investor, by its title: never its key or its file name. */
function DocumentRow({ item, onOpen }: { item: KbItem; onOpen: (item: KbItem) => void }) {
  const { t } = useI18n();
  const title = item.title ?? t.panel.untitled;
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(item)}
        aria-label={t.panel.open(title)}
        className="flex w-full items-start gap-2.5 rounded-lg px-2 py-2 text-left hover:bg-ink-50 focus-visible:outline-2 focus-visible:outline-focus"
      >
        <FileText aria-hidden className="mt-0.5 size-4 shrink-0 text-navy" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-ink-900">{title}</span>
        </span>
      </button>
    </li>
  );
}

/**
 * The client's documents, reloaded after every request (`revision`) and on a change of language. The steps
 * of each request (`traces/`) and the table of contents (`index.md`) are left out: the investor reads the
 * steps in « Les étapes suivies », and the documents themselves here.
 */
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
    docs: items.filter((item) => !item.key.includes("/traces/") && !item.key.endsWith("/index.md")),
  };
}

function DocumentsSection({ clientId, revision }: { clientId: string; revision: number }) {
  const { t } = useI18n();
  const [open, setOpen] = useState<KbItem | null>(null);
  const { error, loading, empty, docs } = useClientDocuments(clientId, revision);
  return (
    <>
      {error ? <ErrorNotice error={error} compact /> : null}
      {loading ? <SkeletonRows label={t.common.loading} count={2} /> : null}
      {empty ? <p className="text-sm text-ink-500">{t.panel.noDocuments}</p> : null}
      <ul className="-mx-2 space-y-0.5">
        {docs.map((item) => (
          <DocumentRow key={item.key} item={item} onOpen={setOpen} />
        ))}
      </ul>
      <DocumentDialog
        documentKey={open?.key ?? null}
        title={open ? (open.title ?? t.panel.untitled) : ""}
        clientId={clientId}
        onClose={() => setOpen(null)}
      />
    </>
  );
}

/** Completeness, knowledge level and effective risk: the profile at a glance. */
export function ProfileSummary({ state }: { state: ClientState }) {
  const { t } = useI18n();
  const { profile, completeness } = state;
  return (
    <>
      <CompletenessMeter completeness={completeness} />
      <div className="mt-5 grid grid-cols-2 gap-4">
        <KnowledgeMeter level={profile.knowledge_level} />
        <RiskMeter level={profile.effective_risk} />
      </div>
      <p className="mt-2 text-xs text-ink-500">{riskCaption(profile, t)}</p>
    </>
  );
}

/** The information the profile still lacks, or a line saying nothing is missing. */
export function MissingList({ missing }: { missing: ClientState["completeness"]["missing"] }) {
  const { t } = useI18n();
  if (missing.length === 0) return <p className="text-sm text-good-ink">{t.panel.missingNone}</p>;
  return (
    <ul className="flex flex-wrap gap-1.5">
      {missing.map((item) => (
        <li key={`${item.dimension}.${item.field}`}>
          <Badge tone="outline" title={t.dimensions[item.dimension]}>
            {item.label}
          </Badge>
        </li>
      ))}
    </ul>
  );
}

/** The investor's own documents; the team's view also sees the state of their search. */
export function ClientDocuments({ state }: { state: ClientState }) {
  const session = useSession();
  const operator = useOperator();
  return (
    <>
      {/* Absent when the runtime has no client knowledge base; "disabled" came from the first runtime version. The team's view only. */}
      {operator && state.client_kb && state.client_kb.status !== "disabled" ? <ClientKbStatusCard kb={state.client_kb} /> : null}
      <DocumentsSection clientId={state.client_id} revision={session.revision} />
    </>
  );
}

/** The profile in the journey's side panel: completeness, level, risk, dimensions, facts, documents. */
export function ProfilePanel({ state }: { state: ClientState }) {
  const { t } = useI18n();
  const { profile, completeness } = state;
  return (
    <div className="overflow-hidden rounded-xl bg-surface shadow-card ring-1 ring-ink-200/80">
      <header className="flex items-center gap-2 px-5 pt-4">
        <UserRound aria-hidden className="size-4 text-navy" />
        <h2 className="flex-1 text-[0.95rem] font-semibold tracking-tight text-ink-950">{t.panel.title}</h2>
      </header>
      <div className="px-5 pt-4 pb-5">
        <ProfileSummary state={state} />
      </div>
      <Section title={t.panel.dimensions} defaultOpen>
        <DimensionList profile={profile} />
      </Section>
      <Section title={t.panel.missing} defaultOpen={completeness.missing.length > 0}>
        <MissingList missing={completeness.missing} />
      </Section>
      <Section title={t.panel.facts(profile.facts.length)}>
        <FactsList facts={profile.facts} />
      </Section>
      <Section title={t.panel.documentsTitle} icon={<FolderOpen aria-hidden className="size-4 text-ink-500" />} defaultOpen>
        <ClientDocuments state={state} />
      </Section>
    </div>
  );
}
