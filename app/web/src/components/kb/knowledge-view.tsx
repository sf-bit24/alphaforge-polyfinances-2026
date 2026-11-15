"use client";

import { BookOpen, FileText, LibraryBig, Search } from "lucide-react";
import { useCallback, useId, useMemo, useState } from "react";
import type { KbItem } from "@/lib/contract/schemas";
import { callMessages, listKb, type ApiError } from "@/lib/client/api";
import { useAsync } from "@/lib/client/use-async";
import { formatDate } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { GENERAL_FOLDERS, generalGroup } from "@/lib/okf";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Spinner } from "@/components/ui/spinner";
import { CollectPanel } from "./collect-panel";
import { DocumentLoader } from "./document-view";

const GROUP_ORDER = ["index", ...GENERAL_FOLDERS, "other"];

const INDEX_KEY = "general/index.md";

function matchingItems(items: KbItem[], query: string): KbItem[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return items;
  return items.filter((item) =>
    [item.key, item.title ?? "", item.description ?? "", item.type ?? ""].some((field) => field.toLowerCase().includes(needle)),
  );
}

function groupedItems(items: KbItem[]): Array<{ group: string; items: KbItem[] }> {
  const map = new Map<string, KbItem[]>();
  for (const item of items) {
    const group = generalGroup(item.key);
    map.set(group, [...(map.get(group) ?? []), item]);
  }
  return GROUP_ORDER.filter((group) => map.has(group)).map((group) => ({ group, items: map.get(group) ?? [] }));
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
  hasIndex: boolean;
  query: string;
}

/** Loading, error and empty states of the document list. */
function ListStatus({ error, loaded, itemCount, matchCount, hasIndex, query }: ListStatusProps) {
  const { t } = useI18n();
  return (
    <>
      {error ? <ErrorNotice className="mx-2" error={error} compact /> : null}
      {!loaded && !error ? <Spinner className="mx-2" label={t.common.loading} /> : null}
      {loaded && itemCount === 0 ? <p className="px-2 text-sm text-ink-500">{t.kb.emptyGeneral}</p> : null}
      {loaded && itemCount > 0 && !hasIndex && !query ? <p className="px-2 pb-2 text-xs text-ink-500">{t.kb.noIndex}</p> : null}
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
          {item.type ? <Badge tone="outline">{item.type}</Badge> : null}
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

/** The document being read; reloaded when the list is refreshed (`version`). */
function CurrentDocument({ current, item, version, empty }: { current: string | null; item: KbItem | undefined; version: number; empty: boolean }) {
  const { t } = useI18n();
  if (current) {
    return (
      <>
        <CardHeader title={item?.title ?? current} subtitle={<span className="font-mono text-xs">{current}</span>} />
        <div className="px-6 py-5">
          <DocumentLoader key={`${current}|${version}`} documentKey={current} clientId={null} />
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

/** The general base: list `general/` documents, read one, feed the base. */
export function KnowledgeView() {
  const { t, locale } = useI18n();
  const searchId = useId();
  const [version, setVersion] = useState(0);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const { data, error, previous } = useAsync(`general/|${version}|${locale}`, (signal) =>
    listKb("general/", null, { locale, signal, messages: callMessages(t) }),
  );
  const items = useMemo(() => (data ?? previous)?.items ?? [], [data, previous]);
  const refresh = useCallback(() => setVersion((value) => value + 1), []);
  const filtered = useMemo(() => matchingItems(items, query), [items, query]);
  const groups = useMemo(() => groupedItems(filtered), [filtered]);

  // general/index.md is written by A6 and is absent before the first collection: fall back to the first document.
  // A selection missing from a fresh list (deleted, or list refreshed) falls back too; while reloading it is kept.
  const loaded = Boolean(data || previous);
  const hasIndex = items.some((item) => item.key === INDEX_KEY);
  const selectionValid = selected !== null && (items.some((item) => item.key === selected) || !data);
  const current = (selectionValid ? selected : null) ?? (hasIndex ? INDEX_KEY : null) ?? items[0]?.key ?? null;

  return (
    <div className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6">
      <KnowledgeHeading />

      <div className="mt-6 grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <Card className="self-start lg:sticky lg:top-[4.5rem] lg:max-h-[calc(100dvh-5.5rem)] lg:overflow-y-auto">
          <CardHeader title={t.kb.documents} subtitle={t.kb.count(items.length)} icon={<BookOpen aria-hidden className="size-4" />} />
          <SearchField id={searchId} query={query} onChange={setQuery} />
          <div className="px-2 py-3">
            <ListStatus error={error} loaded={loaded} itemCount={items.length} matchCount={filtered.length} hasIndex={hasIndex} query={query} />
            {groups.map(({ group, items: groupItems }) => (
              <DocumentGroup key={group} group={group} items={groupItems} current={current} onSelect={setSelected} />
            ))}
          </div>
        </Card>

        <div className="min-w-0 space-y-6">
          <Card>
            <CurrentDocument current={current} item={items.find((item) => item.key === current)} version={version} empty={loaded && items.length === 0} />
          </Card>
          <CollectPanel
            onWritten={refresh}
            onOpenDoc={(key) => {
              refresh();
              setSelected(key);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          />
        </div>
      </div>
    </div>
  );
}
