"use client";

import { Code, Eye, FileJson } from "lucide-react";
import { useState, type ReactNode } from "react";
import { getKbDocument } from "@/lib/client/api";
import { useAsync } from "@/lib/client/use-async";
import { formatDateTime } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { parseOkf } from "@/lib/okf";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorNotice } from "@/components/ui/error-notice";
import { JsonView } from "@/components/ui/json-view";
import { Markdown } from "@/components/ui/markdown";
import { Spinner } from "@/components/ui/spinner";

const asList = (value: unknown): string[] =>
  Array.isArray(value) ? value.map((item) => (typeof item === "string" ? item : JSON.stringify(item))) : typeof value === "string" ? [value] : [];

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

/** An OKF document: frontmatter as metadata, then the Markdown body; JSON traces as JSON. */
export function DocumentContent({ content, documentKey }: { content: string; documentKey: string }) {
  const { t, locale } = useI18n();
  const [raw, setRaw] = useState(false);

  if (documentKey.endsWith(".json")) {
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

  const doc = parseOkf(content);
  const front = doc.frontmatter;
  const generated = asRecord(front?.generated);
  const sources = Array.isArray(front?.sources) ? (front.sources as unknown[]).map(asRecord).filter(Boolean) : [];
  const data = front?.data;
  const hasData = data !== undefined && data !== null && !(typeof data === "object" && Object.keys(data as object).length === 0);

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
          {front ? (
            <section aria-label={t.documentView.metadata} className="rounded-xl bg-ink-50 p-4 ring-1 ring-ink-150">
              <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
                {front.type ? (
                  <Meta label={t.documentView.type}>
                    <Badge tone="brand">{String(front.type)}</Badge>
                  </Meta>
                ) : null}
                {front.status ? <Meta label={t.documentView.status}>{String(front.status)}</Meta> : null}
                {front.sensitivity ? <Meta label={t.documentView.sensitivity}>{String(front.sensitivity)}</Meta> : null}
                {generated ? (
                  <Meta label={t.documentView.generated}>
                    <span className="font-mono text-xs">{String(generated.by ?? "—")}</span>
                    {generated.at ? (
                      <span className="text-ink-500">
                        {" "}
                        {t.documentView.generatedAt} {formatDateTime(String(generated.at), locale)}
                      </span>
                    ) : null}
                  </Meta>
                ) : null}
                {front.stale_after ? <Meta label={t.documentView.staleAfter}>{formatDateTime(String(front.stale_after), locale)}</Meta> : null}
                {asList(front.owners).length ? <Meta label={t.documentView.owners}>{asList(front.owners).join(", ")}</Meta> : null}
                {asList(front.tags).length ? (
                  <Meta label={t.documentView.tags}>
                    <span className="flex flex-wrap gap-1">
                      {asList(front.tags).map((tag) => (
                        <Badge key={tag} tone="outline">
                          {tag}
                        </Badge>
                      ))}
                    </span>
                  </Meta>
                ) : null}
              </dl>
              {front.description ? <p className="mt-3 text-sm text-ink-600">{String(front.description)}</p> : null}
              {sources.length ? (
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
              ) : null}
              {hasData ? (
                <details className="mt-4">
                  <summary className="text-sm font-medium text-navy hover:underline">{t.documentView.data}</summary>
                  <JsonView value={data} className="mt-2 bg-white" />
                </details>
              ) : null}
            </section>
          ) : null}
          <Markdown>{doc.body}</Markdown>
        </>
      )}
    </div>
  );
}

/** Load a document with `kb.get` (with the client_id for a clients/ key) and show it. */
export function DocumentLoader({ documentKey, clientId }: { documentKey: string; clientId: string | null }) {
  const { t, locale } = useI18n();
  const { data, error, loading } = useAsync(`${documentKey}|${locale}`, (signal) =>
    getKbDocument(documentKey, clientId, {
      locale,
      signal,
      messages: { network: t.errors.network, invalidResponse: t.errors.invalidResponse, noResult: t.errors.noResult },
    }),
  );
  if (loading) return <Spinner label={t.documentView.loading} />;
  if (error) return <ErrorNotice error={error} />;
  if (!data) return null;
  return <DocumentContent content={data.content} documentKey={data.key} />;
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
