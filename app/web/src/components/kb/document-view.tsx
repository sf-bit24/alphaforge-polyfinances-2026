"use client";

import { Code, Eye, FileJson } from "lucide-react";
import { useState, type ReactNode } from "react";
import { callMessages, getKbDocument } from "@/lib/client/api";
import { useAsync } from "@/lib/client/use-async";
import { formatDateTime } from "@/lib/i18n/locale";
import { okfTypeLabel } from "@/lib/i18n/okf-types";
import { useI18n } from "@/lib/i18n/provider";
import { parseOkf, resolveOkfLink } from "@/lib/okf";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorNotice } from "@/components/ui/error-notice";
import { JsonView } from "@/components/ui/json-view";
import { Markdown, type LinkRenderer } from "@/components/ui/markdown";
import { Spinner } from "@/components/ui/spinner";

function asList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => (typeof item === "string" ? item : JSON.stringify(item)));
  return typeof value === "string" ? [value] : [];
}

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[0.7rem] font-semibold tracking-wide text-ink-500 uppercase">{label}</dt>
      <dd className="mt-0.5 text-sm break-words text-ink-800">{children}</dd>
    </div>
  );
}

/** A JSON document (traces, data), pretty-printed; shown as text if it does not parse. */
function JsonDocument({ content }: { content: string }) {
  const { t } = useI18n();
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
        {t.documentView.json}
      </p>
      <JsonView value={parsed} maxHeight="max-h-[60vh]" />
    </div>
  );
}

function GeneratedMeta({ generated }: { generated: Record<string, unknown> }) {
  const { t, locale } = useI18n();
  return (
    <Meta label={t.documentView.generated}>
      <span className="font-mono text-xs">{String(generated.by ?? "—")}</span>
      {generated.at ? (
        <span className="text-ink-500">
          {" "}
          {t.documentView.generatedAt} {formatDateTime(String(generated.at), locale)}
        </span>
      ) : null}
    </Meta>
  );
}

function TagsMeta({ tags }: { tags: string[] }) {
  const { t } = useI18n();
  return (
    <Meta label={t.documentView.tags}>
      <span className="flex flex-wrap gap-1">
        {tags.map((tag) => (
          <Badge key={tag} tone="outline">
            {tag}
          </Badge>
        ))}
      </span>
    </Meta>
  );
}

function MetadataFields({ front }: { front: Record<string, unknown> }) {
  const { t, locale } = useI18n();
  const generated = asRecord(front.generated);
  const owners = asList(front.owners);
  const tags = asList(front.tags);
  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
      {front.type ? (
        <Meta label={t.documentView.type}>
          <Badge tone="brand">{okfTypeLabel(String(front.type), locale)}</Badge>
        </Meta>
      ) : null}
      {front.status ? <Meta label={t.documentView.status}>{String(front.status)}</Meta> : null}
      {front.sensitivity ? <Meta label={t.documentView.sensitivity}>{String(front.sensitivity)}</Meta> : null}
      {generated ? <GeneratedMeta generated={generated} /> : null}
      {front.stale_after ? <Meta label={t.documentView.staleAfter}>{formatDateTime(String(front.stale_after), locale)}</Meta> : null}
      {owners.length ? <Meta label={t.documentView.owners}>{owners.join(", ")}</Meta> : null}
      {tags.length ? <TagsMeta tags={tags} /> : null}
    </dl>
  );
}

function SourceList({ sources }: { sources: Array<Record<string, unknown> | null> }) {
  const { t } = useI18n();
  return (
    <div className="mt-4">
      <p className="text-[0.7rem] font-semibold tracking-wide text-ink-500 uppercase">{t.documentView.sources}</p>
      <ul className="mt-1 space-y-1">
        {sources.map((source, index) => (
          <li key={`${String(source?.id)}-${index}`} className="text-sm text-ink-700">
            <span className="font-medium">{String(source?.title ?? source?.id ?? "")}</span>
            {source?.resource ? <span className="ml-2 font-mono text-xs text-ink-500">{String(source.resource)}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Frontmatter({ front }: { front: Record<string, unknown> }) {
  const { t } = useI18n();
  const sources = Array.isArray(front.sources) ? (front.sources as unknown[]).map(asRecord).filter(Boolean) : [];
  const data = front.data;
  const hasData = data !== undefined && data !== null && !(typeof data === "object" && Object.keys(data as object).length === 0);
  return (
    <section aria-label={t.documentView.metadata} className="rounded-xl bg-ink-50 p-4 ring-1 ring-ink-150">
      <MetadataFields front={front} />
      {front.description ? <p className="mt-3 text-sm text-ink-600">{String(front.description)}</p> : null}
      {sources.length ? <SourceList sources={sources} /> : null}
      {hasData ? (
        <details className="mt-4">
          <summary className="text-sm font-medium text-navy hover:underline">{t.documentView.data}</summary>
          <JsonView value={data} className="mt-2 bg-white" />
        </details>
      ) : null}
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
      <button type="button" title={key} onClick={() => links.open(key)} className="text-navy underline underline-offset-2 hover:text-ink-950 focus-visible:outline-2 focus-visible:outline-focus">
        {label}
      </button>
    );
  };
}

/** An OKF document: frontmatter as metadata, then the Markdown body; JSON traces as JSON. */
export function DocumentContent({ content, documentKey, links }: { content: string; documentKey: string; links?: DocumentLinks }) {
  const { t } = useI18n();
  const [raw, setRaw] = useState(false);
  const renderLink = useLinkRenderer(documentKey, links);

  if (documentKey.endsWith(".json")) return <JsonDocument content={content} />;

  const doc = parseOkf(content);
  return (
    <div className="space-y-5">
      <div className="flex justify-end">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setRaw((value) => !value)}
          icon={raw ? <Eye aria-hidden className="size-4" /> : <Code aria-hidden className="size-4" />}
          aria-pressed={raw}
        >
          {raw ? t.documentView.rendered : t.documentView.raw}
        </Button>
      </div>
      {raw ? (
        <JsonView value={content} className="whitespace-pre-wrap" maxHeight="max-h-[65vh]" />
      ) : (
        <>
          {doc.error ? <p className="text-sm text-warning-ink">{t.documentView.invalidFrontmatter}</p> : null}
          {doc.frontmatter ? <Frontmatter front={doc.frontmatter} /> : null}
          <Markdown renderLink={renderLink}>{doc.body}</Markdown>
        </>
      )}
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
    <Dialog open={documentKey !== null} onClose={onClose} title={title} subtitle={documentKey ?? undefined}>
      {documentKey ? <DocumentLoader key={documentKey} documentKey={documentKey} clientId={clientId} /> : null}
    </Dialog>
  );
}
