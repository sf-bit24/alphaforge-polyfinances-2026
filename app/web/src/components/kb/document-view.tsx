"use client";

import { ExternalLink, FileJson } from "lucide-react";
import type { ReactNode } from "react";
import { useOperator } from "@/lib/client/account";
import { callMessages, getKbDocument } from "@/lib/client/api";
import { useAsync } from "@/lib/client/use-async";
import { formatDate } from "@/lib/i18n/locale";
import { okfTypeLabel } from "@/lib/i18n/okf-types";
import { useI18n } from "@/lib/i18n/provider";
import { parseOkf, resolveOkfLink } from "@/lib/okf";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { ErrorNotice } from "@/components/ui/error-notice";
import { JsonView } from "@/components/ui/json-view";
import { Markdown, type LinkRenderer } from "@/components/ui/markdown";
import { Spinner } from "@/components/ui/spinner";

function asList(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string");
  return typeof value === "string" ? [value] : [];
}

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;

const asText = (value: unknown): string | null => (typeof value === "string" && value ? value : null);

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[0.7rem] font-semibold tracking-wide text-ink-500 uppercase">{label}</dt>
      <dd className="mt-0.5 text-sm break-words text-ink-800">{children}</dd>
    </div>
  );
}

/** A JSON document (a client's steps): its raw content is for the team's view only. */
function JsonDocument({ content }: { content: string }) {
  const { t } = useI18n();
  const operator = useOperator();
  if (!operator) return <p className="text-sm text-ink-600">{t.documentView.unavailable}</p>;
  let parsed: unknown = content;
  try {
    parsed = JSON.parse(content);
  } catch {
    // shown as text
  }
  return (
    <div>
      <p className="mb-2 flex items-center gap-2 text-sm text-ink-600">
        <FileJson aria-hidden className="size-4 text-navy" />
        {t.documentView.rawTeam}
      </p>
      <JsonView value={parsed} maxHeight="max-h-[60vh]" />
    </div>
  );
}

/** The topics of a document, from its tags: only those with a label; the others are internal. */
function TopicsMeta({ tags }: { tags: string[] }) {
  const { t } = useI18n();
  const labels = [...new Set(tags.map((tag) => t.documentView.topicLabels[tag]).filter((label): label is string => Boolean(label)))];
  if (!labels.length) return null;
  return (
    <Meta label={t.documentView.topics}>
      <span className="flex flex-wrap gap-1">
        {labels.map((label) => (
          <Badge key={label} tone="outline">
            {label}
          </Badge>
        ))}
      </span>
    </Meta>
  );
}

/** What a reader needs: the kind of document, when it was updated, when it is due for review, its topics. */
function MetadataFields({ front }: { front: Record<string, unknown> }) {
  const { t, locale } = useI18n();
  const updated = asText(asRecord(front.generated)?.at);
  const review = asText(front.stale_after);
  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
      {front.type ? (
        <Meta label={t.documentView.type}>
          <Badge tone="brand">{okfTypeLabel(String(front.type), locale)}</Badge>
        </Meta>
      ) : null}
      {updated ? <Meta label={t.documentView.updated}>{formatDate(updated, locale)}</Meta> : null}
      {review ? <Meta label={t.documentView.staleAfter}>{formatDate(review, locale)}</Meta> : null}
      <TopicsMeta tags={asList(front.tags)} />
    </dl>
  );
}

/** The first web address in a source's reference, if any: the only part of it a reader may follow. */
function webLink(resource: unknown): string | null {
  const match = typeof resource === "string" ? /https?:\/\/[^\s),;»]+/.exec(resource) : null;
  return match ? match[0].replace(/[.:]+$/, "") : null;
}

/** A source by its title and its date, with a link when it is on the web; never its path or its key. */
function SourceItem({ source }: { source: Record<string, unknown> }) {
  const { t, locale } = useI18n();
  const title = asText(source.title);
  if (!title) return null;
  const date = asText(source.published_at) ?? asText(source.observed_at) ?? asText(source.retrieved_at);
  const url = webLink(source.resource);
  return (
    <li className="text-sm text-ink-700">
      <span className="font-medium">{title}</span>
      {date ? <span className="text-ink-500"> · {formatDate(date, locale)}</span> : null}
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer noopener"
          aria-label={`${t.documentView.openSource}, ${title}`}
          className="ml-2 inline-flex items-center gap-1 text-navy underline underline-offset-2 hover:text-ink-950"
        >
          {t.documentView.openSource}
          <ExternalLink aria-hidden className="size-3" />
        </a>
      ) : null}
    </li>
  );
}

function SourceList({ sources }: { sources: Array<Record<string, unknown>> }) {
  const { t } = useI18n();
  return (
    <div className="mt-4">
      <p className="text-[0.7rem] font-semibold tracking-wide text-ink-500 uppercase">{t.documentView.sources}</p>
      <ul className="mt-1 space-y-1">
        {sources.map((source, index) => (
          <SourceItem key={`${String(source.id)}-${index}`} source={source} />
        ))}
      </ul>
    </div>
  );
}

function Frontmatter({ front }: { front: Record<string, unknown> }) {
  const { t } = useI18n();
  const sources = Array.isArray(front.sources)
    ? (front.sources as unknown[]).map(asRecord).filter((source): source is Record<string, unknown> => Boolean(source && asText(source.title)))
    : [];
  return (
    <section aria-label={t.documentView.metadata} className="rounded-xl bg-ink-50 p-4 ring-1 ring-ink-150">
      <MetadataFields front={front} />
      {front.description ? <p className="mt-3 text-sm text-ink-600">{String(front.description)}</p> : null}
      {sources.length ? <SourceList sources={sources} /> : null}
    </section>
  );
}

/** The documents a reader can open from links: the keys of its base, and how to open one. */
export interface DocumentLinks {
  known: ReadonlySet<string>;
  open: (key: string) => void;
}

const RELATIVE_LINK = /^(?![a-z][a-z0-9+.-]*:|[#/])/i;

/** Links to another document of the base open it in place; a link to a missing document stays plain text. */
function useLinkRenderer(documentKey: string, links: DocumentLinks | undefined): LinkRenderer | undefined {
  const { t } = useI18n();
  if (!links) return undefined;
  return function renderOkfLink(href, label) {
    if (!href || !RELATIVE_LINK.test(href)) return undefined;
    const key = resolveOkfLink(documentKey, href, links.known);
    if (!key) {
      return (
        <span className="text-ink-500" title={t.kb.linkMissing}>
          {label}
        </span>
      );
    }
    return (
      <button type="button" onClick={() => links.open(key)} className="text-navy underline underline-offset-2 hover:text-ink-950 focus-visible:outline-2 focus-visible:outline-focus">
        {label}
      </button>
    );
  };
}

/** An OKF document: what a reader needs to know about it, then its text; a JSON document only in the team's view. */
export function DocumentContent({ content, documentKey, links }: { content: string; documentKey: string; links?: DocumentLinks }) {
  const { t } = useI18n();
  const renderLink = useLinkRenderer(documentKey, links);

  if (documentKey.endsWith(".json")) return <JsonDocument content={content} />;

  const doc = parseOkf(content);
  return (
    <div className="space-y-5">
      {doc.error ? <p className="text-sm text-warning-ink">{t.documentView.invalidFrontmatter}</p> : null}
      {doc.frontmatter ? <Frontmatter front={doc.frontmatter} /> : null}
      <Markdown renderLink={renderLink}>{doc.body}</Markdown>
    </div>
  );
}

/** Load a document with `kb.get` (with the client_id for a clients/ key) and show it. */
export function DocumentLoader({ documentKey, clientId, links }: { documentKey: string; clientId: string | null; links?: DocumentLinks }) {
  const { t, locale } = useI18n();
  const { data, error, loading } = useAsync(`${documentKey}|${locale}`, (signal) =>
    getKbDocument(documentKey, clientId, { locale, signal, messages: callMessages(t) }),
  );
  if (loading) return <Spinner label={t.documentView.loading} />;
  if (error) return <ErrorNotice error={error} />;
  if (!data) return null;
  return <DocumentContent content={data.content} documentKey={data.key} links={links} />;
}

export function DocumentDialog({
  documentKey,
  title,
  clientId,
  onClose,
}: {
  documentKey: string | null;
  title: string;
  clientId: string | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={documentKey !== null} onClose={onClose} title={title}>
      {documentKey ? <DocumentLoader key={documentKey} documentKey={documentKey} clientId={clientId} /> : null}
    </Dialog>
  );
}
