"use client";

import { AlertTriangle, BookOpen, CircleHelp, Clapperboard, Info, LoaderCircle, ThumbsUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/components/ui/cn";
import { type FeedbackResult, type VideoCard } from "@/lib/tldoole/types";
import type { TldooleText } from "@/lib/tldoole/text";

type Panel = "why" | "sources" | "quiz" | null;

const ACTIVE = new Set(["queued", "scripting", "rendering"]);

function RailButton({ label, icon, onClick, active, disabled }: { label: string; icon: React.ReactNode; onClick: () => void; active?: boolean; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={cn(
        "flex w-16 flex-col items-center gap-1 text-[0.7rem] font-medium text-ink-700 disabled:opacity-40",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
      )}
    >
      <span className={cn("flex size-11 items-center justify-center rounded-full bg-ink-900 text-white shadow-sm", active && "bg-brand-600")}>
        {icon}
      </span>
      <span className="text-center leading-tight">{label}</span>
    </button>
  );
}

function WhyList({ video, t }: { video: VideoCard; t: TldooleText }) {
  return (
    <ul className="space-y-2 text-sm text-ink-700">
      {video.why.map((item, index) => (
        <li key={index} className="rounded-lg bg-ink-50 px-3 py-2">
          {item.kind === "message" && item.quote ? (
            <>
              <span className="text-ink-500">{t.youWrote} : </span>« {item.quote} »
            </>
          ) : item.kind === "answer" ? (
            <>
              <span className="text-ink-500">{t.yourAnswer} : </span>
              <code className="text-xs">{item.field}</code> = <code className="text-xs">{JSON.stringify(item.value)}</code>
            </>
          ) : item.kind === "request" ? (
            t.youAsked
          ) : item.kind === "feedback" ? (
            t.afterFeedback
          ) : (
            t.portfolio
          )}
          {item.provenance ? <span className="ml-1 text-xs text-ink-400">({item.provenance})</span> : null}
        </li>
      ))}
    </ul>
  );
}

export function VideoSlide({
  video,
  t,
  onFeedback,
}: {
  video: VideoCard;
  t: TldooleText;
  onFeedback: (video: VideoCard, input: { verdict?: "understood" | "unclear"; quiz_answer?: number }) => Promise<FeedbackResult | null>;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  const [panel, setPanel] = useState<Panel>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<FeedbackResult | null>(null);
  const ready = video.status === "ready";

  // Façon vidéo courte : lecture (muette) quand la diapositive est visible, pause sinon.
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry) return;
        if (entry.intersectionRatio > 0.6) void element.play().catch(() => undefined);
        else element.pause();
      },
      { threshold: [0, 0.6, 1] },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [video.video_url]);

  const send = async (input: { verdict?: "understood" | "unclear"; quiz_answer?: number }) => {
    setBusy(true);
    try {
      const outcome = await onFeedback(video, input);
      if (outcome) setResult(outcome);
    } finally {
      setBusy(false);
    }
  };

  const toggle = (next: Panel) => setPanel((current) => (current === next ? null : next));
  const verdict = result?.video.feedback?.verdict ?? video.feedback?.verdict ?? null;

  return (
    <article className="snap-start snap-always py-3" aria-label={video.title ?? video.label ?? video.concept_id}>
      <div className="flex items-end gap-2">
        <div className="relative aspect-[9/16] max-h-[76dvh] min-w-0 flex-1 overflow-hidden rounded-2xl bg-ink-950 shadow-card">
          {ready && video.video_url ? (
            <video
              ref={ref}
              src={video.video_url}
              poster={video.poster_url ?? undefined}
              className="h-full w-full object-cover"
              playsInline
              muted
              loop={false}
              controls
              preload="metadata"
              onEnded={() => video.quiz && setPanel("quiz")}
            >
              {video.captions_url ? <track kind="captions" src={video.captions_url} srcLang={video.locale ?? "fr"} label="Sous-titres" /> : null}
            </video>
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-4 bg-gradient-to-b from-ink-950 to-navy px-6 text-center text-white">
              {video.poster_url ? (
                // eslint-disable-next-line @next/next/no-img-element -- URL S3 signée, hors de l'optimiseur d'images
                <img src={video.poster_url} alt="" className="absolute inset-0 h-full w-full object-cover opacity-40" />
              ) : null}
              <span className="relative flex size-16 items-center justify-center rounded-full bg-white/10 ring-1 ring-white/20">
                {video.status === "failed" ? (
                  <AlertTriangle aria-hidden className="size-8 text-warning" />
                ) : ACTIVE.has(video.status) ? (
                  <LoaderCircle aria-hidden className="size-8 animate-spin" />
                ) : (
                  <Clapperboard aria-hidden className="size-8" />
                )}
              </span>
              <p className="relative text-lg font-semibold">{video.title}</p>
              <p className="relative text-sm text-ink-200" role="status">
                {ready ? t.noFile : t.status[video.status]}
              </p>
              {video.error ? <p className="relative text-xs text-ink-300">{video.error.message}</p> : null}
            </div>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-center gap-3 pb-4">
          <RailButton label={t.understood} icon={<ThumbsUp aria-hidden className="size-5" />} active={verdict === "understood"} disabled={!ready || busy} onClick={() => void send({ verdict: "understood" })} />
          <RailButton label={t.unclear} icon={<CircleHelp aria-hidden className="size-5" />} active={verdict === "unclear"} disabled={!ready || busy} onClick={() => void send({ verdict: "unclear" })} />
          <RailButton label={t.whyShort} icon={<Info aria-hidden className="size-5" />} active={panel === "why"} onClick={() => toggle("why")} />
          <RailButton label={t.sources} icon={<BookOpen aria-hidden className="size-5" />} active={panel === "sources"} onClick={() => toggle("sources")} />
        </div>
      </div>

      <div className="mx-auto mt-3 w-full space-y-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="brand">{video.label}</Badge>
          {video.reason ? <Badge tone="outline">{t.reason[video.reason] ?? video.reason}</Badge> : null}
          {video.level ? <Badge tone="neutral">{t.level[video.level] ?? video.level}</Badge> : null}
          {video.duration_ms && ready ? <Badge tone="neutral">{t.minutes(video.duration_ms)}</Badge> : null}
          {!ready ? <Badge tone={video.status === "failed" ? "critical" : "warning"}>{t.status[video.status]}</Badge> : null}
        </div>
        <p className="font-semibold text-ink-950">{video.title}</p>
        {ready && video.quiz ? (
          <button type="button" onClick={() => toggle("quiz")} className="text-sm font-medium text-navy hover:underline">
            {t.quiz}
          </button>
        ) : null}

        {panel === "quiz" && video.quiz ? (
          <div className="rounded-xl bg-surface p-4 shadow-card ring-1 ring-ink-200/80">
            <p className="text-sm font-semibold text-ink-950">{video.quiz.question}</p>
            <div className="mt-3 grid gap-2">
              {video.quiz.options.map((option, index) => (
                <button
                  key={index}
                  type="button"
                  disabled={busy || result?.quiz != null}
                  onClick={() => void send({ quiz_answer: index })}
                  className={cn(
                    "rounded-lg px-3 py-2 text-left text-sm ring-1 ring-inset ring-ink-200 hover:bg-ink-50 disabled:cursor-default",
                    result?.quiz?.answer === index && "bg-good-wash ring-good",
                  )}
                >
                  {option}
                </button>
              ))}
            </div>
            {result?.quiz ? (
              <p className="mt-3 text-sm text-ink-700" role="status">
                <strong>{result.quiz.correct ? t.quizRight : t.quizWrong}</strong> {result.quiz.explanation}
              </p>
            ) : null}
          </div>
        ) : null}

        {panel === "why" ? (
          <div className="rounded-xl bg-surface p-4 shadow-card ring-1 ring-ink-200/80">
            <p className="mb-2 text-sm font-semibold text-ink-950">{t.why}</p>
            <WhyList video={video} t={t} />
          </div>
        ) : null}

        {panel === "sources" ? (
          <div className="rounded-xl bg-surface p-4 shadow-card ring-1 ring-ink-200/80">
            <p className="mb-2 text-sm font-semibold text-ink-950">{t.sources}</p>
            <ul className="space-y-1 text-sm text-ink-700">
              {video.sources.map((source) => (
                <li key={source.id}>
                  {source.title}
                  {source.resource ? <code className="ml-1 text-xs text-ink-500">{source.resource}</code> : null}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-ink-500">{t.disclaimer}</p>
          </div>
        ) : null}

        {result ? (
          <p className="text-sm text-ink-600" role="status">
            {result.follow_up ? t.followUp : t.thanks}
          </p>
        ) : null}
      </div>
    </article>
  );
}
