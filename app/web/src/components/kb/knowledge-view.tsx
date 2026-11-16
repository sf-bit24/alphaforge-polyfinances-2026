"use client";

import { BookOpen, FileText, LibraryBig, Radar, Search, Waypoints } from "lucide-react";
import { Activity, useCallback, useId, useMemo, useState } from "react";
import type { KbItem } from "@/lib/contract/schemas";
import { useOperator } from "@/lib/client/account";
import { callMessages, listKb, type ApiError } from "@/lib/client/api";
import { useAsync } from "@/lib/client/use-async";
import { useHashTab } from "@/lib/client/use-hash-tab";
import { formatDate } from "@/lib/i18n/locale";
import { okfTypeLabel } from "@/lib/i18n/okf-types";
import { useI18n } from "@/lib/i18n/provider";
import { GENERAL_FOLDERS, generalGroup } from "@/lib/okf";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Spinner } from "@/components/ui/spinner";
import { TabList, tabPanelProps, type TabItem } from "@/components/ui/tabs";
import { CollectPanel } from "./collect-panel";
import { DocumentLoader, type DocumentLinks } from "./document-view";
import { KnowledgeGraphPanel } from "./knowledge-graph";
import { matchingItems } from "./match";

const GROUP_ORDER = ["index", ...GENERAL_FOLDERS, "other"];

const INDEX_KEY = "general/index.md";

/** Sub-tabs of the page, named in the URL fragment: `/knowledge#graph`, `/knowledge#collect`. */
const TABS = ["documents", "graph", "collect"] as const;
type KnowledgeTab = (typeof TABS)[number];
/** A client never sees the collection tab: `/knowledge#collect` opens the documents. */
const CLIENT_TABS: readonly KnowledgeTab[] = ["documents", "graph"];

function groupedItems(items: KbItem[]): Array<{ group: string; items: KbItem[] }> {
  const map = new Map<string, KbItem[]>();
  for (const item of items) {
    const group = generalGroup(item.key);
    map.set(group, [...(map.get(group) ?? []), item]);
  }
  return GROUP_ORDER.filter((group) => map.has(group)).map((group) => ({ group, items: map.get(group) ?? [] }));
}

/**
 * The document to read. general/index.md is written by A6 and is absent before the first collection: fall back
 * to the first document. A selection missing from a fresh list (deleted, or list refreshed) falls back too; while
 * the list reloads (`fresh` false) it is kept.
 */
function currentKey(items: KbItem[], selected: string | null, fresh: boolean): string | null {
  const hasIndex = items.some((item) => item.key === INDEX_KEY);
  const selectionValid = selected !== null && (items.some((item) => item.key === selected) || !fresh);
  return (selectionValid ? selected : null) ?? (hasIndex ? INDEX_KEY : null) ?? items[0]?.key ?? null;
}

function KnowledgeHeading() {
  const { t } = useI18n();
  return (
    <div className="flex items-start gap-3">
      <LibraryBig aria-hidden className="mt-1 size-6 text-navy" />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink-950">{t.kb.title}</h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-600">{t.kb.intro}</p>
      </div>
    </div>
  );
}

function SearchField({ id, query, onChange }: { id: string; query: string; onChange: (query: string) => void }) {
  const { t } = useI18n();
  return (
    <div className="px-4 pt-3">
      <label htmlFor={id} className="sr-only">
        {t.kb.search}
      </label>
      <div className="relative">
        <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-400" />
        <input
          id={id}
          type="search"
          value={query}
          onChange={(event) => onChange(event.target.value)}
          placeholder={t.kb.search}
          className="block w-full rounded-lg border-0 bg-white py-2 pr-3 pl-9 text-sm ring-1 ring-ink-300 ring-inset placeholder:text-ink-400 focus:ring-2 focus:ring-navy focus:outline-none"
        />
      </div>
    </div>
  );
}

interface ListStatusProps {
  error: ApiError | null;
  loaded: boolean;
  itemCount: number;
  matchCount: number;
}

/** Loading, error and empty states of the document list. */
function ListStatus({ error, loaded, itemCount, matchCount }: ListStatusProps) {
  const { t } = useI18n();
  return (
    <>
      {error ? <ErrorNotice className="mx-2" error={error} compact /> : null}
      {!loaded && !error ? <Spinner className="mx-2" label={t.common.loading} /> : null}
      {loaded && itemCount === 0 ? <p className="px-2 text-sm text-ink-500">{t.kb.emptyGeneral}</p> : null}
      {itemCount > 0 && matchCount === 0 ? <p className="px-2 text-sm text-ink-500">{t.kb.noMatch}</p> : null}
    </>
  );
}

function DocumentButton({ item, active, onSelect }: { item: KbItem; active: boolean; onSelect: (key: string) => void }) {
  const { t, locale } = useI18n();
  return (
    <button
      type="button"
      onClick={() => onSelect(item.key)}
      aria-current={active ? "true" : undefined}
      className={cn(
        "flex w-full items-start gap-2.5 rounded-lg px-2 py-2 text-left transition-colors focus-visible:outline-2 focus-visible:outline-focus",
        active ? "bg-soft ring-1 ring-line" : "hover:bg-ink-50",
      )}
    >
      <FileText aria-hidden className={cn("mt-0.5 size-4 shrink-0", active ? "text-navy" : "text-ink-400")} />
      <span className="min-w-0 flex-1">
        <span className="block text-sm leading-snug font-medium text-ink-900">{item.title ?? item.key}</span>
        {item.description ? <span className="mt-0.5 line-clamp-2 block text-xs leading-snug text-ink-500">{item.description}</span> : null}
        <span className="mt-1 flex flex-wrap items-center gap-1.5">
          {item.type ? <Badge tone="outline">{okfTypeLabel(item.type, locale)}</Badge> : null}
          {item.updated_at ? (
            <span className="text-[0.7rem] text-ink-400">
              {t.kb.updated} {formatDate(item.updated_at, locale)}
            </span>
          ) : null}
        </span>
      </span>
    </button>
  );
}

function DocumentGroup({ group, items, current, onSelect }: { group: string; items: KbItem[]; current: string | null; onSelect: (key: string) => void }) {
  const { t } = useI18n();
  return (
    <section className="mb-3" aria-labelledby={`group-${group}`}>
      <h2 id={`group-${group}`} className="px-2 pb-1 text-[0.7rem] font-semibold tracking-wide text-ink-500 uppercase">
        {t.kb.groups[group] ?? group}
      </h2>
      <ul className="space-y-0.5">
        {items.map((item) => (
          <li key={item.key}>
            <DocumentButton item={item} active={item.key === current} onSelect={onSelect} />
          </li>
        ))}
      </ul>
    </section>
  );
}

interface CurrentDocumentProps {
  current: string | null;
  item: KbItem | undefined;
  version: number;
  empty: boolean;
  links: DocumentLinks;
}

/** The document being read; reloaded when the list is refreshed (`version`). Its links to the base open in place. */
function CurrentDocument({ current, item, version, empty, links }: CurrentDocumentProps) {
  const { t } = useI18n();
  if (current) {
    return (
      <>
        <CardHeader title={item?.title ?? t.kb.documents} />
        <div className="px-6 py-5">
          <DocumentLoader key={`${current}|${version}`} documentKey={current} clientId={null} links={links} />
        </div>
      </>
    );
  }
  if (empty) {
    return (
      <div className="px-6 py-10 text-center">
        <p className="text-sm font-medium text-ink-800">{t.kb.emptyGeneral}</p>
        <p className="mx-auto mt-1 max-w-lg text-sm text-ink-500">{t.kb.emptyGeneralHelp}</p>
      </div>
    );
  }
  return <p className="px-6 py-10 text-center text-sm text-ink-500">{t.kb.select}</p>;
}

interface DocumentsTabProps {
  items: KbItem[];
  error: ApiError | null;
  loaded: boolean;
  version: number;
  current: string | null;
  onSelect: (key: string) => void;
  onOpen: (key: string) => void;
}

/** The documents tab: the filterable list of `general/`, and the document being read. */
function DocumentsTab({ items, error, loaded, version, current, onSelect, onOpen }: DocumentsTabProps) {
  const { t, locale } = useI18n();
  const searchId = useId();
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => matchingItems(items, query, locale), [items, query, locale]);
  const groups = useMemo(() => groupedItems(filtered), [filtered]);
  const links = useMemo(() => ({ known: new Set(items.map((item) => item.key)), open: onOpen }), [items, onOpen]);
  return (
    <div className="grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
      <Card className="self-start lg:sticky lg:top-[4.5rem] lg:max-h-[calc(100dvh-5.5rem)] lg:overflow-y-auto">
        <CardHeader title={t.kb.documents} subtitle={t.kb.count(items.length)} icon={<BookOpen aria-hidden className="size-4" />} />
        <SearchField id={searchId} query={query} onChange={setQuery} />
        <div className="px-2 py-3">
          <ListStatus error={error} loaded={loaded} itemCount={items.length} matchCount={filtered.length} />
          {groups.map(({ group, items: groupItems }) => (
            <DocumentGroup key={group} group={group} items={groupItems} current={current} onSelect={onSelect} />
          ))}
        </div>
      </Card>
      <Card className="min-w-0 self-start">
        <CurrentDocument current={current} item={items.find((item) => item.key === current)} version={version} empty={loaded && items.length === 0} links={links} />
      </Card>
    </div>
  );
}

function useKnowledgeTabs(operator: boolean): Array<TabItem<KnowledgeTab>> {
  const { t } = useI18n();
  return [
    { id: "documents", label: t.kb.tabs.documents, icon: <BookOpen aria-hidden className="size-4" /> },
    { id: "graph", label: t.kb.tabs.graph, icon: <Waypoints aria-hidden className="size-4" /> },
    ...(operator ? [{ id: "collect" as const, label: t.kb.tabs.collect, icon: <Radar aria-hidden className="size-4" /> }] : []),
  ];
}

/** The general base in tabs: read its documents, see how they link; the team's view can also feed it. */
export function KnowledgeView() {
  const { t, locale } = useI18n();
  const idPrefix = useId();
  const operator = useOperator();
  const tabs = useKnowledgeTabs(operator);
  const [tab, setTab] = useHashTab(operator ? TABS : CLIENT_TABS, "documents");
  const [version, setVersion] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const { data, error, previous } = useAsync(`general/|${version}|${locale}`, (signal) =>
    listKb("general/", null, { locale, signal, messages: callMessages(t) }),
  );
  const items = useMemo(() => (data ?? previous)?.items ?? [], [data, previous]);
  const loaded = Boolean(data || previous);
  const refresh = useCallback(() => setVersion((value) => value + 1), []);
  const openDocument = useCallback(
    (key: string) => {
      setSelected(key);
      setTab("documents");
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    [setTab],
  );

  return (
    <div className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6">
      <KnowledgeHeading />
      <TabList tabs={tabs} value={tab} onChange={setTab} idPrefix={idPrefix} label={t.kb.tabs.label} className="mt-6" />
      <div {...tabPanelProps(idPrefix, "documents", tab === "documents")} className="pt-6">
        <DocumentsTab items={items} error={error} loaded={loaded} version={version} current={currentKey(items, selected, Boolean(data))} onSelect={setSelected} onOpen={openDocument} />
      </div>
      <div {...tabPanelProps(idPrefix, "graph", tab === "graph")} className="pt-6">
        {/* Hidden, the graph keeps its filters, selection and zoom; its layout is computed in the background. */}
        <Activity mode={tab === "graph" ? "visible" : "hidden"}>
          <KnowledgeGraphPanel items={items} loaded={loaded} stale={!data && Boolean(previous)} error={error} onOpenDoc={openDocument} />
        </Activity>
      </div>
      {/* The team's view only. Hidden but mounted: a run in progress keeps being polled, and the list refreshes when it ends. */}
      {operator ? (
        <div {...tabPanelProps(idPrefix, "collect", tab === "collect")} className="pt-6">
          <CollectPanel
            onWritten={refresh}
            onOpenDoc={(key) => {
              refresh();
              openDocument(key);
            }}
          />
        </div>
      ) : null}
    </div>
  );
}
