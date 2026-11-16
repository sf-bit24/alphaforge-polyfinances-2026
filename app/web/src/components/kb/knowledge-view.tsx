"use client";

import { BookOpen, LibraryBig, Radar, Waypoints } from "lucide-react";
import { Activity, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import type { KbItem } from "@/lib/contract/schemas";
import { useOperator } from "@/lib/client/account";
import { callMessages, listKb, type ApiError } from "@/lib/client/api";
import { useAsync } from "@/lib/client/use-async";
import { useHashTab } from "@/lib/client/use-hash-tab";
import { useI18n } from "@/lib/i18n/provider";
import { Card, CardHeader } from "@/components/ui/card";
import { TabList, tabPanelProps, type TabItem } from "@/components/ui/tabs";
import { CollectPanel } from "./collect-panel";
import { DocumentList, INDEX_KEY } from "./document-list";
import { DocumentSkeleton } from "@/components/ui/skeleton";
import { DocumentLoader, type DocumentLinks } from "./document-view";
import { KnowledgeGraphPanel } from "./knowledge-graph";

/** Sub-tabs of the page, named in the URL fragment: `/knowledge#graph`, `/knowledge#collect`. */
const TABS = ["documents", "graph", "collect"] as const;
type KnowledgeTab = (typeof TABS)[number];
/** A client never sees the collection tab: `/knowledge#collect` opens the documents. */
const CLIENT_TABS: readonly KnowledgeTab[] = ["documents", "graph"];

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

interface CurrentDocumentProps {
  current: string | null;
  item: KbItem | undefined;
  version: number;
  empty: boolean;
  /** The list is still on its way: the reader shows its outline, not « choose a document ». */
  loading: boolean;
  links: DocumentLinks;
}

/** The document being read; reloaded when the list is refreshed (`version`). Its links to the base open in place. */
function CurrentDocument({ current, item, version, empty, loading, links }: CurrentDocumentProps) {
  const { t } = useI18n();
  if (!current && loading) {
    return (
      <div className="px-6 py-5">
        <DocumentSkeleton label={t.documentView.loading} />
      </div>
    );
  }
  if (current) {
    return (
      <>
        <CardHeader className="rounded-t-xl bg-surface lg:sticky lg:top-0 lg:z-10" title={item?.title ?? t.kb.documents} />
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

/** Wide screens show the list and the reader side by side; a narrow one stacks them, and opening a document scrolls down to it. */
const NARROW = "(max-width: 63.99rem)";

/** The documents tab: the list of `general/` and the reader, each in a pane that scrolls on its own on a wide screen. */
function DocumentsTab({ items, error, loaded, version, current, onSelect, onOpen }: DocumentsTabProps) {
  const links = useMemo(() => ({ known: new Set(items.map((item) => item.key)), open: onOpen }), [items, onOpen]);
  const reader = useRef<HTMLElement>(null);
  // Every document starts at its top, however it was opened: from the list, a link, the graph or a collection.
  useEffect(() => {
    reader.current?.scrollTo({ top: 0 });
  }, [current]);
  const select = (key: string) => {
    onSelect(key);
    if (window.matchMedia(NARROW).matches) reader.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  return (
    <div className="grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
      <DocumentList items={items} error={error} loaded={loaded} current={current} onSelect={select} />
      <Card ref={reader} className="min-w-0 scroll-mt-28 self-start lg:sticky lg:top-[4.5rem] lg:max-h-[calc(100dvh-5.5rem)] lg:overflow-y-auto">
        <CurrentDocument current={current} item={items.find((item) => item.key === current)} version={version} empty={loaded && items.length === 0} loading={!loaded && !error} links={links} />
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
