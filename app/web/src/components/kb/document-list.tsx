"use client";

import { BookOpen, ChevronRight, FileText, Search } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { KbItem, Locale } from "@/lib/contract/schemas";
import type { ApiError } from "@/lib/client/api";
import { formatDate } from "@/lib/i18n/locale";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { useI18n } from "@/lib/i18n/provider";
import { GENERAL_FOLDERS, generalGroup } from "@/lib/okf";
import { Card, CardHeader } from "@/components/ui/card";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { SkeletonRows } from "@/components/ui/skeleton";
import { matchingItems } from "./match";

export const INDEX_KEY = "general/index.md";

const GROUP_ORDER = ["index", ...GENERAL_FOLDERS, "other"];

/** Folders of dated documents: the newest first, each with its date. The others are listed by title. */
const DATED_GROUPS: ReadonlySet<string> = new Set(["actualites", "recherches", "faits", "signaux", "depots", "donnees"]);

const timeOf = (item: KbItem) => (item.updated_at ? Date.parse(item.updated_at) || 0 : 0);

export function groupedItems(items: KbItem[], locale: Locale): Array<{ group: string; items: KbItem[] }> {
  const map = new Map<string, KbItem[]>();
  for (const item of items) {
    const group = generalGroup(item.key);
    const list = map.get(group);
    if (list) list.push(item);
    else map.set(group, [item]);
  }
  const byTitle = (a: KbItem, b: KbItem) => (a.title ?? a.key).localeCompare(b.title ?? b.key, locale);
  const byNewest = (a: KbItem, b: KbItem) => timeOf(b) - timeOf(a) || byTitle(a, b);
  return GROUP_ORDER.flatMap((group) => {
    const list = map.get(group);
    return list ? [{ group, items: list.sort(DATED_GROUPS.has(group) ? byNewest : byTitle) }] : [];
  });
}

function SearchField({ id, query, onChange }: { id: string; query: string; onChange: (query: string) => void }) {
  const { t } = useI18n();
  return (
    <div className="border-b border-ink-150 px-4 py-3">
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
      {!loaded && !error ? <SkeletonRows className="mx-2" label={t.common.loading} count={6} withLine /> : null}
      {loaded && itemCount === 0 ? <p className="px-2 text-sm text-ink-500">{t.kb.emptyGeneral}</p> : null}
      {itemCount > 0 && matchCount === 0 ? <p className="px-2 text-sm text-ink-500">{t.kb.noMatch}</p> : null}
    </>
  );
}

/** One line per document, two when the title is long: the description stays for the reader, and the tooltip. */
function DocumentButton({ item, active, dated, onSelect }: { item: KbItem; active: boolean; dated: boolean; onSelect: (key: string) => void }) {
  const { locale } = useI18n();
  return (
    <button
      type="button"
      onClick={() => onSelect(item.key)}
      aria-current={active ? "true" : undefined}
      title={item.description ?? undefined}
      className={cn(
        "flex w-full items-start gap-2 rounded-md py-1.5 pr-2 pl-3 text-left transition-colors focus-visible:outline-2 focus-visible:outline-focus",
        active ? "bg-soft ring-1 ring-line" : "hover:bg-ink-50",
      )}
    >
      <FileText aria-hidden className={cn("mt-0.5 size-3.5 shrink-0", active ? "text-navy" : "text-ink-400")} />
      <span className={cn("line-clamp-2 min-w-0 flex-1 text-sm leading-snug", active ? "font-medium text-ink-950" : "text-ink-800")}>{item.title ?? item.key}</span>
      {dated && item.updated_at ? <span className="mt-0.5 shrink-0 text-[0.7rem] text-ink-500 tabular-nums">{formatDate(item.updated_at, locale)}</span> : null}
    </button>
  );
}

interface DocumentGroupProps {
  group: string;
  items: KbItem[];
  current: string | null;
  expanded: boolean;
  onToggle: () => void;
  onSelect: (key: string) => void;
}

/** A folder: its name and count, a button that opens or closes it, and its documents. */
function DocumentGroup({ group, items, current, expanded, onToggle, onSelect }: DocumentGroupProps) {
  const { t } = useI18n();
  const listId = useId();
  const label = t.kb.groups[group] ?? group;
  return (
    <section aria-label={label}>
      <h3 className="sticky top-0 z-10 bg-surface">
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={listId}
          onClick={onToggle}
          className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-xs font-semibold tracking-wide text-ink-600 uppercase hover:bg-ink-50 focus-visible:outline-2 focus-visible:outline-focus"
        >
          <ChevronRight aria-hidden className={cn("size-3.5 shrink-0 text-ink-500 transition-transform", expanded && "rotate-90")} />
          <span className="min-w-0 flex-1 truncate">{label}</span>
          <span className="font-normal text-ink-500 tabular-nums">{items.length}</span>
        </button>
      </h3>
      <ul id={listId} hidden={!expanded} className="space-y-0.5 pb-2">
        {items.map((item) => (
          <li key={item.key}>
            <DocumentButton item={item} active={item.key === current} dated={DATED_GROUPS.has(group)} onSelect={onSelect} />
          </li>
        ))}
      </ul>
    </section>
  );
}

const withEntry = (map: ReadonlyMap<string, boolean>, key: string, value: boolean) => new Map(map).set(key, value);

/**
 * Which folders are open. While browsing: the folder of the document being read (also when it is opened from
 * the graph or a link), and those the reader opens. While searching: every folder with a match, unless closed;
 * a new query opens them all again.
 */
function useGroupExpansion(currentGroup: string | null, searching: boolean) {
  const [browse, setBrowse] = useState<ReadonlyMap<string, boolean>>(new Map());
  const [search, setSearch] = useState<ReadonlyMap<string, boolean>>(new Map());
  const [shownGroup, setShownGroup] = useState(currentGroup);
  if (currentGroup !== shownGroup) {
    setShownGroup(currentGroup);
    if (currentGroup) setBrowse((map) => withEntry(map, currentGroup, true));
  }
  const expanded = (group: string) => (searching ? (search.get(group) ?? true) : (browse.get(group) ?? group === currentGroup));
  return {
    expanded,
    toggle: (group: string) => (searching ? setSearch : setBrowse)((map) => withEntry(map, group, !expanded(group))),
    resetSearch: () => setSearch(new Map()),
  };
}

/** Keeps the document being read in sight in the list, when the list scrolls on its own (wide screens). */
function useActiveItemInView(current: string | null) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const list = ref.current;
    const item = list?.querySelector<HTMLElement>('[aria-current="true"]');
    if (!list || !item || list.scrollHeight <= list.clientHeight) return;
    const listBox = list.getBoundingClientRect();
    const itemBox = item.getBoundingClientRect();
    // 40 px: the sticky folder name above the item.
    if (itemBox.top < listBox.top + 40 || itemBox.bottom > listBox.bottom) list.scrollTop += itemBox.top - listBox.top - listBox.height / 3;
  }, [current]);
  return ref;
}

interface DocumentListProps {
  items: KbItem[];
  error: ApiError | null;
  loaded: boolean;
  current: string | null;
  onSelect: (key: string) => void;
}

/** « 7 documents », « 2 matches », or « Chargement… » while the list is on its way (never « 0 document »). */
function listSubtitle(t: Dictionary, list: { loaded: boolean; searching: boolean; matches: number; count: number }): string {
  if (!list.loaded) return t.common.loading;
  return list.searching ? t.kb.matches(list.matches) : t.kb.count(list.count);
}

/** The documents of `general/`, by folder, with a filter; on a wide screen, a pane that scrolls on its own. */
export function DocumentList({ items, error, loaded, current, onSelect }: DocumentListProps) {
  const { t, locale } = useI18n();
  const searchId = useId();
  const [query, setQuery] = useState("");
  const searching = query.trim() !== "";
  const filtered = useMemo(() => matchingItems(items, query, locale), [items, query, locale]);
  const groups = useMemo(() => groupedItems(filtered, locale), [filtered, locale]);
  const expansion = useGroupExpansion(current ? generalGroup(current) : null, searching);
  const listRef = useActiveItemInView(current);
  const changeQuery = (value: string) => {
    setQuery(value);
    expansion.resetSearch();
  };
  return (
    <Card className="flex flex-col self-start lg:sticky lg:top-[4.5rem] lg:max-h-[calc(100dvh-5.5rem)]">
      <CardHeader title={t.kb.documents} subtitle={listSubtitle(t, { loaded, searching, matches: filtered.length, count: items.length })} icon={<BookOpen aria-hidden className="size-4" />} />
      <SearchField id={searchId} query={query} onChange={changeQuery} />
      <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        <ListStatus error={error} loaded={loaded} itemCount={items.length} matchCount={filtered.length} />
        {groups.map(({ group, items: groupItems }) => (
          <DocumentGroup
            key={group}
            group={group}
            items={groupItems}
            current={current}
            expanded={expansion.expanded(group)}
            onToggle={() => expansion.toggle(group)}
            onSelect={onSelect}
          />
        ))}
      </div>
    </Card>
  );
}
