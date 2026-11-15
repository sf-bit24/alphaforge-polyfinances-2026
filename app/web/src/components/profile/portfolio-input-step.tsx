"use client";

import { FileUp, Paperclip, Sparkles, Upload, X } from "lucide-react";
import { useId, useRef, useState, type DragEvent } from "react";
import { UPLOAD_LIMITS, type UploadFile } from "@/lib/contract/requests";
import type { Locale } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import { formatNumber } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Markdown } from "@/components/ui/markdown";
import { Spinner } from "@/components/ui/spinner";

const EXAMPLE = {
  fr: "100 RY.TO CELI\n40 TD.TO CELI\n25 AAPL REER\n15 NVDA REER\n200 XIU.TO non enregistré\n0,05 BTC\nfonds maison XYZ",
  en: "100 RY.TO TFSA\n40 TD.TO TFSA\n25 AAPL RRSP\n15 NVDA RRSP\n200 XIU.TO non-registered\n0.05 BTC\nhouse fund XYZ",
};

const EXTENSION_TYPES: Record<string, string> = {
  csv: "text/csv",
  tsv: "text/tab-separated-values",
  txt: "text/plain",
  md: "text/markdown",
  json: "application/json",
  pdf: "application/pdf",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  xls: "application/vnd.ms-excel",
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
};

function mediaTypeOf(file: File): string {
  if (file.type) return file.type;
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  return EXTENSION_TYPES[extension] ?? "application/octet-stream";
}

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.onerror = () => reject(reader.error ?? new Error("read failed"));
    reader.readAsDataURL(file);
  });
}

function sizeLabel(bytes: number, locale: Locale, units: { bytes: string; kilobytes: string; megabytes: string }): string {
  if (bytes < 1024) return `${bytes} ${units.bytes}`;
  if (bytes < 1024 * 1024) return `${formatNumber(bytes / 1024, locale, 0)} ${units.kilobytes}`;
  return `${formatNumber(bytes / (1024 * 1024), locale, 1)} ${units.megabytes}`;
}

/** `existing_portfolio`: any data, pasted or dropped, sent to A2; or skip. */
export function PortfolioInputStep() {
  const { t, locale } = useI18n();
  const session = useSession();
  const textId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [reading, setReading] = useState(false);
  const analyzing = session.pending === "portfolio.submit";
  const busy = Boolean(session.pending) || reading;

  const addFiles = (incoming: FileList | File[]) => {
    const list = Array.from(incoming);
    const tooLarge = list.find((file) => file.size > UPLOAD_LIMITS.maxFileBytes);
    if (tooLarge) {
      setProblem(t.portfolioInput.tooLarge(tooLarge.name));
      return;
    }
    const merged = [...files, ...list];
    if (merged.length > UPLOAD_LIMITS.maxFiles) {
      setProblem(t.portfolioInput.tooMany);
      return;
    }
    setProblem(null);
    setFiles(merged);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (busy) return;
    if (event.dataTransfer.files.length) addFiles(event.dataTransfer.files);
  };

  const submit = async () => {
    if (!text.trim() && files.length === 0) {
      setProblem(t.portfolioInput.empty);
      return;
    }
    setProblem(null);
    setReading(true);
    let uploads: UploadFile[] = [];
    try {
      uploads = await Promise.all(
        files.map(async (file) => ({ name: file.name, media_type: mediaTypeOf(file), data_base64: await readAsBase64(file) })),
      );
    } catch (error) {
      setProblem(String(error));
      setReading(false);
      return;
    }
    setReading(false);
    await session.submitPortfolio({ text, files: uploads });
  };

  return (
    <Card className="animate-fade-in">
      <div className="px-6 pt-6 pb-2">
        <h2 className="text-xl font-semibold tracking-tight text-ink-950 sm:text-[1.4rem]">{t.portfolioInput.title}</h2>
        <p className="mt-2 max-w-2xl text-sm text-ink-600">{t.portfolioInput.intro}</p>
      </div>
      <div className="space-y-5 px-6 py-4">
        <div>
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <label htmlFor={textId} className="text-sm font-medium text-ink-900">
              {t.portfolioInput.textLabel}
            </label>
            <Button
              size="sm"
              variant="ghost"
              icon={<Sparkles aria-hidden className="size-3.5" />}
              onClick={() => setText(EXAMPLE[locale])}
              disabled={busy}
            >
              {t.portfolioInput.example}
            </Button>
          </div>
          <textarea
            id={textId}
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={7}
            disabled={busy}
            placeholder={t.portfolioInput.textPlaceholder}
            className="block w-full rounded-lg border-0 bg-white px-3.5 py-3 font-mono text-sm text-ink-950 shadow-sm ring-1 ring-ink-300 ring-inset placeholder:text-ink-400 focus:ring-2 focus:ring-brand-500 focus:outline-none disabled:bg-ink-50"
          />
        </div>

        <div
          onDragEnter={(event) => {
            event.preventDefault();
            if (!busy) setDragging(true);
          }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={(event) => {
            if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
            setDragging(false);
          }}
          onDrop={onDrop}
          className={cn(
            "flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-7 text-center transition-colors",
            dragging ? "border-brand-500 bg-brand-50" : "border-ink-200 bg-ink-50/60",
          )}
        >
          <FileUp aria-hidden className={cn("size-7", dragging ? "text-brand-600" : "text-ink-400")} />
          <p className="mt-2 text-sm font-medium text-ink-900">
            {t.portfolioInput.dropTitle}{" "}
            <span className="font-normal text-ink-500">{t.portfolioInput.dropOr}</span>{" "}
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={busy}
              className="rounded font-semibold text-brand-700 underline underline-offset-2 hover:text-brand-800 focus-visible:outline-2 focus-visible:outline-brand-500"
            >
              {t.portfolioInput.browse}
            </button>
          </p>
          <p className="mt-1 text-xs text-ink-500">{t.portfolioInput.limits}</p>
          <input
            ref={inputRef}
            type="file"
            multiple
            className="sr-only"
            tabIndex={-1}
            aria-hidden
            onChange={(event) => {
              if (event.target.files) addFiles(event.target.files);
              event.target.value = "";
            }}
          />
        </div>

        {files.length > 0 ? (
          <ul className="divide-y divide-ink-150 rounded-lg ring-1 ring-ink-200">
            {files.map((file, index) => (
              <li key={`${file.name}-${index}`} className="flex items-center gap-3 px-3 py-2 text-sm">
                <Paperclip aria-hidden className="size-4 shrink-0 text-ink-400" />
                <span className="min-w-0 flex-1 truncate font-medium text-ink-900">{file.name}</span>
                <span className="shrink-0 text-xs text-ink-500">
                  {mediaTypeOf(file)} · {sizeLabel(file.size, locale, t.portfolioInput.units)}
                </span>
                <button
                  type="button"
                  onClick={() => setFiles(files.filter((_, position) => position !== index))}
                  disabled={busy}
                  aria-label={t.portfolioInput.remove(file.name)}
                  className="rounded p-1 text-ink-400 hover:bg-ink-100 hover:text-ink-800 focus-visible:outline-2 focus-visible:outline-brand-500"
                >
                  <X aria-hidden className="size-4" />
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        <p className="text-xs text-ink-500">{t.portfolioInput.privacy}</p>
        {problem ? (
          <p role="alert" className="text-sm font-medium text-critical-ink">
            {problem}
          </p>
        ) : null}
        {session.error && session.errorAction === "portfolio.submit" ? (
          <ErrorNotice error={session.error} onRetry={session.retry} onDismiss={session.dismissError} />
        ) : null}
        {session.error && session.errorAction === "portfolio.skip" ? (
          <ErrorNotice error={session.error} onRetry={session.retry} onDismiss={session.dismissError} />
        ) : null}

        {analyzing ? (
          <div aria-live="polite" className="rounded-xl bg-brand-50/60 p-4 ring-1 ring-brand-100">
            <Spinner label={t.portfolioInput.analyzing} />
            {session.streamText ? <Markdown className="mt-3">{session.streamText}</Markdown> : null}
          </div>
        ) : null}
      </div>
      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-ink-150 px-6 py-4">
        <Button variant="ghost" onClick={() => void session.skipPortfolio()} disabled={busy} loading={session.pending === "portfolio.skip"}>
          {t.portfolioInput.skip}
        </Button>
        <Button
          size="lg"
          onClick={() => void submit()}
          loading={analyzing || reading}
          disabled={busy && !analyzing}
          icon={<Upload aria-hidden className="size-4" />}
        >
          {reading ? t.portfolioInput.reading : analyzing ? t.portfolioInput.analyzing : t.portfolioInput.analyze}
        </Button>
      </footer>
    </Card>
  );
}
