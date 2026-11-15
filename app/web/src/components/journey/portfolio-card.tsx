"use client";

import { Paperclip, Upload, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type DragEvent } from "react";
import { UPLOAD_LIMITS, type UploadFile } from "@/lib/contract/requests";
import { useSession } from "@/lib/client/session";
import { EXAMPLE_PORTFOLIO, mediaTypeOf, readAsBase64, sizeLabel } from "@/lib/client/uploads";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Markdown } from "@/components/ui/markdown";
import s from "./journey.module.css";

/** `existing_portfolio` at the briefcase sign: pasted text or files go to A2, or the investor skips. */
export function PortfolioCard({ say, autoFocus, onSkip }: { say: string; autoFocus: boolean; onSkip: () => void }) {
  const { t, locale } = useI18n();
  const session = useSession();
  const textId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [reading, setReading] = useState(false);
  const analyzing = session.pending === "portfolio.submit";
  const busy = Boolean(session.pending) || reading;
  const error = session.error && (session.errorAction === "portfolio.submit" || session.errorAction === "portfolio.skip") ? session.error : null;

  useEffect(() => {
    if (autoFocus) textRef.current?.focus({ preventScroll: true });
  }, [autoFocus]);

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
      uploads = await Promise.all(files.map(async (file) => ({ name: file.name, media_type: mediaTypeOf(file), data_base64: await readAsBase64(file) })));
    } catch (failure) {
      setProblem(String(failure));
      setReading(false);
      return;
    }
    setReading(false);
    await session.submitPortfolio({ text, files: uploads });
  };

  return (
    <>
      <div className={s.say}>
        <span className={s.avatar} aria-hidden>
          Y
        </span>
        <p>{say}</p>
      </div>
      <h2>{t.journey.portfolio.title}</h2>
      <p className={s.hint}>{t.portfolioInput.intro}</p>

      <div className={s.labelRow}>
        <label htmlFor={textId}>{t.portfolioInput.textLabel}</label>
        <button type="button" className={s.ghost} onClick={() => setText(EXAMPLE_PORTFOLIO[locale])} disabled={busy}>
          {t.portfolioInput.example}
        </button>
      </div>
      <textarea
        ref={textRef}
        id={textId}
        className={cn(s.textarea, s.paste)}
        rows={5}
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={t.portfolioInput.textPlaceholder}
        disabled={busy}
      />

      <div
        className={cn(s.drop, dragging && s.dropOn)}
        onDragEnter={(event) => {
          event.preventDefault();
          if (!busy) setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
        }}
        onDrop={onDrop}
      >
        {t.portfolioInput.dropTitle} {t.portfolioInput.dropOr}{" "}
        <button type="button" className={s.ghost} onClick={() => inputRef.current?.click()} disabled={busy}>
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
            if (event.target.files) addFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

      {files.length > 0 ? (
        <ul className={s.files}>
          {files.map((file, index) => (
            <li key={`${file.name}-${index}`}>
              <Paperclip aria-hidden className="size-4 shrink-0 text-ink-400" />
              <span>{file.name}</span>
              <small>{sizeLabel(file.size, locale, t.portfolioInput.units)}</small>
              <button
                type="button"
                className={s.iconButton}
                onClick={() => setFiles(files.filter((_, position) => position !== index))}
                disabled={busy}
                aria-label={t.portfolioInput.remove(file.name)}
              >
                <X aria-hidden className="size-4" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <p className={s.hint}>{t.portfolioInput.privacy}</p>
      {problem ? (
        <p role="alert" className={s.error}>
          {problem}
        </p>
      ) : null}
      {error ? (
        <div className={s.notice}>
          <ErrorNotice error={error} onRetry={session.retry} onDismiss={session.dismissError} />
        </div>
      ) : null}

      {analyzing ? (
        <div className={s.stream} aria-live="polite">
          <span className={s.typing} aria-label={t.portfolioInput.analyzing}>
            <i />
            <i />
            <i />
          </span>
          {session.streamText ? <Markdown>{session.streamText}</Markdown> : <p className={s.hint}>{t.portfolioInput.analyzing}</p>}
        </div>
      ) : null}

      <div className={s.actions}>
        <button type="button" className={s.primary} onClick={() => void submit()} disabled={busy}>
          <Upload aria-hidden className="size-4" />
          {reading ? t.portfolioInput.reading : analyzing ? t.portfolioInput.analyzing : t.portfolioInput.analyze}
        </button>
        <button type="button" className={s.ghost} onClick={onSkip} disabled={busy}>
          {t.portfolioInput.skip}
        </button>
      </div>
    </>
  );
}
