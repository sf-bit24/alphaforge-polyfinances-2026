"use client";

import { BookOpen, FileText, LibraryBig, Search } from "lucide-react";
import { useCallback, useId, useMemo, useState } from "react";
import type { KbItem } from "@/lib/contract/schemas";
import { listKb } from "@/lib/client/api";
import { useAsync } from "@/lib/client/use-async";
import { formatDate } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { generalGroup } from "@/lib/okf";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Spinner } from "@/components/ui/spinner";
import { CollectPanel } from "./collect-panel";
import { DocumentLoader } from "./document-view";

const GROUP_ORDER = ["index", "methodologie", "societes", "actualites", "donnees", "other"];

/** The general base: list `general/` documents, read one, feed the base. */
export function KnowledgeView() {
  const { t, locale } = useI18n();
  const searchId = useId();
  const [version, setVersion] = useState(0);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const { data, error, previous } = useAsync(`general/|${version}|${locale}`, (signal) =>
    listKb("general/", null, {
      locale,
      signal,
      messages: { network: t.errors.network, invalidResponse: t.errors.invalidResponse, noResult: t.errors.noResult },
    }),
  );
  const items = useMemo(() => (data ?? previous)?.items ?? [], [data, previous]);
  const refresh = useCallback(() => setVersion((value) => value + 1), []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((item) =>
      [item.key, item.title ?? "", item.description ?? "", item.type ?? ""].some((field) => field.toLowerCase().includes(needle)),
    );
  }, [items, query]);

  const groups = useMemo(() => {
    const map = new Map<string, KbItem[]>();
    for (const item of filtered) {
      const group = generalGroup(item.key);
      map.set(group, [...(map.get(group) ?? []), item]);
    }
    return GROUP_ORDER.filter((group) => map.has(group)).map((group) => ({ group, items: map.get(group) ?? [] }));
  }, [filtered]);

  // general/index.md is written by A6 and is absent before the first collection: fall back to the first document.
  // A selection missing from a fresh list (deleted, or list refreshed) falls back too; while reloading it is kept.
  const loaded = Boolean(data || previous);
  const hasIndex = items.some((item) => item.key === "general/index.md");
  const selectionValid = selected !== null && (items.some((item) => item.key === selected) || !data);
  const current = (selectionValid ? selected : null) ?? (hasIndex ? "general/index.md" : null) ?? items[0]?.key ?? null;
  const currentItem = items.find((item) => item.key === current);

  return (
    <div className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6">
      <div className="flex items-start gap-3">
        <LibraryBig aria-hidden className="mt-1 size-6 text-brand-600" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink-950">{t.kb.title}</h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-600">{t.kb.intro}</p>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <Card className="self-start lg:sticky lg:top-[4.5rem] lg:max-h-[calc(100dvh-5.5rem)] lg:overflow-y-auto">
          <CardHeader title={t.kb.documents} subtitle={t.kb.count(items.length)} icon={<BookOpen aria-hidden className="size-4" />} />
          <div className="px-4 pt-3">
            <label htmlFor={searchId} className="sr-only">
              {t.kb.search}
            </label>
            <div className="relative">
              <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-400" />
              <input
                id={searchId}
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t.kb.search}
                className="block w-full rounded-lg border-0 bg-white py-2 pr-3 pl-9 text-sm ring-1 ring-ink-300 ring-inset placeholder:text-ink-400 focus:ring-2 focus:ring-brand-500 focus:outline-none"
              />
            </div>
          </div>
          <div className="px-2 py-3">
            {error ? <ErrorNotice className="mx-2" error={error} compact /> : null}
            {!data && !previous && !error ? <Spinner className="mx-2" label={t.common.loading} /> : null}
            {loaded && items.length === 0 ? <p className="px-2 text-sm text-ink-500">{t.kb.emptyGeneral}</p> : null}
            {loaded && items.length > 0 && !hasIndex && !query ? <p className="px-2 pb-2 text-xs text-ink-500">{t.kb.noIndex}</p> : null}
            {items.length > 0 && filtered.length === 0 ? <p className="px-2 text-sm text-ink-500">{t.kb.noMatch}</p> : null}
            {groups.map(({ group, items: groupItems }) => (
              <section key={group} className="mb-3" aria-labelledby={`group-${group}`}>
                <h2 id={`group-${group}`} className="px-2 pb-1 text-[0.7rem] font-semibold tracking-wide text-ink-500 uppercase">
                  {t.kb.groups[group] ?? group}
                </h2>
                <ul className="space-y-0.5">
                  {groupItems.map((item) => {
                    const active = item.key === current;
                    return (
                      <li key={item.key}>
                        <button
                          type="button"
                          onClick={() => setSelected(item.key)}
                          aria-current={active ? "true" : undefined}
                          className={cn(
                            "flex w-full items-start gap-2.5 rounded-lg px-2 py-2 text-left transition-colors focus-visible:outline-2 focus-visible:outline-brand-500",
                            active ? "bg-brand-50 ring-1 ring-brand-100" : "hover:bg-ink-50",
                          )}
                        >
                          <FileText aria-hidden className={cn("mt-0.5 size-4 shrink-0", active ? "text-brand-600" : "text-ink-400")} />
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
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
          </div>
        </Card>

        <div className="min-w-0 space-y-6">
          <Card>
            {current ? (
              <>
                <CardHeader title={currentItem?.title ?? current} subtitle={<span className="font-mono text-xs">{current}</span>} />
                <div className="px-6 py-5">
                  <DocumentLoader key={`${current}|${version}`} documentKey={current} clientId={null} />
                </div>
              </>
            ) : loaded && items.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <p className="text-sm font-medium text-ink-800">{t.kb.emptyGeneral}</p>
                <p className="mx-auto mt-1 max-w-lg text-sm text-ink-500">{t.kb.emptyGeneralHelp}</p>
              </div>
            ) : (
              <p className="px-6 py-10 text-center text-sm text-ink-500">{t.kb.select}</p>
            )}
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
