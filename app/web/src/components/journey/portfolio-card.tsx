"use client";

import { Paperclip, Upload, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type DragEvent, type RefObject } from "react";
import { UPLOAD_LIMITS, type UploadFile } from "@/lib/contract/requests";
import { useSession } from "@/lib/client/session";
import { EXAMPLE_PORTFOLIO, mediaTypeOf, readAsBase64, sizeLabel } from "@/lib/client/uploads";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Markdown } from "@/components/ui/markdown";
import { AssistantLine } from "./assistant-line";
import styles from "./journey.module.css";

/** Why the files cannot be added (one is too large, or too many in all), or null. */
function refusalOf(added: File[], all: File[], t: Dictionary): string | null {
  const tooLarge = added.find((file) => file.size > UPLOAD_LIMITS.maxFileBytes);
  if (tooLarge) return t.portfolioInput.tooLarge(tooLarge.name);
  if (all.length > UPLOAD_LIMITS.maxFiles) return t.portfolioInput.tooMany;
  return null;
}

function toUploads(files: File[]): Promise<UploadFile[]> {
  return Promise.all(files.map(async (file) => ({ name: file.name, media_type: mediaTypeOf(file), data_base64: await readAsBase64(file) })));
}

/** What the investor shares with A2 (pasted text, files), and how it is checked, read and sent. */
function usePortfolioUpload() {
  const { t } = useI18n();
  const session = useSession();
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [reading, setReading] = useState(false);
  const analyzing = session.pending === "portfolio.submit";
  const busy = Boolean(session.pending) || reading;

  const addFiles = (incoming: FileList | File[]) => {
    const list = Array.from(incoming);
    const merged = [...files, ...list];
    const refusal = refusalOf(list, merged, t);
    setProblem(refusal);
    if (!refusal) setFiles(merged);
  };

  const removeFile = (index: number) => setFiles(files.filter((_, position) => position !== index));

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (!busy && event.dataTransfer.files.length) addFiles(event.dataTransfer.files);
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
      uploads = await toUploads(files);
    } catch (failure) {
      setProblem(String(failure));
      setReading(false);
      return;
    }
    setReading(false);
    await session.submitPortfolio({ text, files: uploads });
  };

  return { text, setText, files, problem, dragging, setDragging, reading, analyzing, busy, addFiles, removeFile, onDrop, submit };
}

type PortfolioUpload = ReturnType<typeof usePortfolioUpload>;

function PasteField({ id, textRef, upload }: { id: string; textRef: RefObject<HTMLTextAreaElement | null>; upload: PortfolioUpload }) {
  const { t, locale } = useI18n();
  return (
    <>
      <div className={styles.labelRow}>
        <label htmlFor={id}>{t.portfolioInput.textLabel}</label>
        <button type="button" className={styles.ghost} onClick={() => upload.setText(EXAMPLE_PORTFOLIO[locale])} disabled={upload.busy}>
          {t.portfolioInput.example}
        </button>
      </div>
      <textarea
        ref={textRef}
        id={id}
        className={cn(styles.textarea, styles.paste)}
        rows={5}
        value={upload.text}
        onChange={(event) => upload.setText(event.target.value)}
        placeholder={t.portfolioInput.textPlaceholder}
        disabled={upload.busy}
      />
    </>
  );
}

function DropZone({ inputRef, upload }: { inputRef: RefObject<HTMLInputElement | null>; upload: PortfolioUpload }) {
  const { t } = useI18n();
  const { busy, setDragging } = upload;
  return (
    <div
      className={cn(styles.drop, upload.dragging && styles.dropOn)}
      onDragEnter={(event) => {
        event.preventDefault();
        if (!busy) setDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={upload.onDrop}
    >
      {t.portfolioInput.dropTitle} {t.portfolioInput.dropOr}{" "}
      <button type="button" className={styles.ghost} onClick={() => inputRef.current?.click()} disabled={busy}>
        {t.portfolioInput.browse}
      </button>
      <small>{t.portfolioInput.limits}</small>
      <input
        ref={inputRef}
        type="file"
        multiple
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(event) => {
          if (event.target.files) upload.addFiles(event.target.files);
          event.target.value = "";
        }}
      />
    </div>
  );
}

function FileList({ upload }: { upload: PortfolioUpload }) {
  const { t, locale } = useI18n();
  return (
    <ul className={styles.files}>
      {upload.files.map((file, index) => (
        <li key={`${file.name}-${index}`}>
          <Paperclip aria-hidden className="size-4 shrink-0 text-ink-400" />
          <span>{file.name}</span>
          <small>{sizeLabel(file.size, locale, t.portfolioInput.units)}</small>
          <button
            type="button"
            className={styles.iconButton}
            onClick={() => upload.removeFile(index)}
            disabled={upload.busy}
            aria-label={t.portfolioInput.remove(file.name)}
          >
            <X aria-hidden className="size-4" />
          </button>
        </li>
      ))}
    </ul>
  );
}

function SubmitError() {
  const session = useSession();
  const error = session.error && (session.errorAction === "portfolio.submit" || session.errorAction === "portfolio.skip") ? session.error : null;
  if (!error) return null;
  return (
    <div className={styles.notice}>
      <ErrorNotice error={error} onRetry={session.retry} onDismiss={session.dismissError} />
    </div>
  );
}

/** A2's message as it streams in. */
function AnalysisStream() {
  const { t } = useI18n();
  const session = useSession();
  return (
    <div className={styles.stream} aria-live="polite">
      <span className={styles.typing} aria-label={t.portfolioInput.analyzing}>
        <i />
        <i />
        <i />
      </span>
      {session.streamText ? <Markdown>{session.streamText}</Markdown> : <p className={styles.hint}>{t.portfolioInput.analyzing}</p>}
    </div>
  );
}

function analyzeLabel(t: Dictionary, { reading, analyzing }: { reading: boolean; analyzing: boolean }): string {
  if (reading) return t.portfolioInput.reading;
  return analyzing ? t.portfolioInput.analyzing : t.portfolioInput.analyze;
}

function UploadActions({ upload, onSkip }: { upload: PortfolioUpload; onSkip: () => void }) {
  const { t } = useI18n();
  return (
    <div className={styles.actions}>
      <button type="button" className={styles.primary} onClick={() => void upload.submit()} disabled={upload.busy}>
        <Upload aria-hidden className="size-4" />
        {analyzeLabel(t, upload)}
      </button>
      <button type="button" className={styles.ghost} onClick={onSkip} disabled={upload.busy}>
        {t.portfolioInput.skip}
      </button>
    </div>
  );
}

/** `existing_portfolio` at the briefcase sign: pasted text or files go to A2, or the investor skips. */
export function PortfolioCard({ say, autoFocus, onSkip }: { say: string; autoFocus: boolean; onSkip: () => void }) {
  const { t } = useI18n();
  const textId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const upload = usePortfolioUpload();

  useEffect(() => {
    if (autoFocus) textRef.current?.focus({ preventScroll: true });
  }, [autoFocus]);

  return (
    <>
      <AssistantLine>{say}</AssistantLine>
      <h2>{t.journey.portfolio.title}</h2>
      <p className={styles.hint}>{t.portfolioInput.intro}</p>
      <PasteField id={textId} textRef={textRef} upload={upload} />
      <DropZone inputRef={inputRef} upload={upload} />
      {upload.files.length > 0 ? <FileList upload={upload} /> : null}
      <p className={styles.hint}>{t.portfolioInput.privacy}</p>
      {upload.problem ? (
        <p role="alert" className={styles.error}>
          {upload.problem}
        </p>
      ) : null}
      <SubmitError />
      {upload.analyzing ? <AnalysisStream /> : null}
      <UploadActions upload={upload} onSkip={onSkip} />
    </>
  );
}
