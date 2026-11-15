"use client";

import { Film, Sparkles, Wand2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useSession } from "@/lib/client/session";
import { useAsync } from "@/lib/client/use-async";
import { useI18n } from "@/lib/i18n/provider";
import { tldoole, TldooleError } from "@/lib/tldoole/client";
import { tldooleText } from "@/lib/tldoole/text";
import type { Feed, FeedbackResult, VideoCard } from "@/lib/tldoole/types";
import { VideoSlide } from "./video-slide";

const POLL_MS = 8000;

export function TldooleFeed() {
  const { clientId, hydrated } = useSession();
  const { locale } = useI18n();
  const t = tldooleText(locale);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [concept, setConcept] = useState("");
  const [asking, setAsking] = useState(false);
  const [asked, setAsked] = useState(false);

  // Une version de plus recharge le fil; la précédente reste affichée pendant le rechargement.
  const { data, error: loadError, previous } = useAsync<Feed>(clientId ? `${clientId}|${version}` : null, (signal) =>
    tldoole.feed(clientId ?? "", signal),
  );
  const feed = data ?? previous;
  const reload = useCallback(() => setVersion((value) => value + 1), []);

  // Tant qu'une vidéo est en cours (A8, Polly, MediaConvert), le fil se rafraîchit.
  const pending = feed?.pending ?? 0;
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(reload, POLL_MS);
    return () => clearInterval(timer);
  }, [pending, reload]);

  const onFeedback = useCallback(
    async (video: VideoCard, input: { verdict?: "understood" | "unclear"; quiz_answer?: number }): Promise<FeedbackResult | null> => {
      if (!clientId) return null;
      try {
        const result = await tldoole.feedback(clientId, video.video_id, input);
        reload();
        return result;
      } catch (cause) {
        setError(cause instanceof TldooleError ? cause.message : t.loadError);
        return null;
      }
    },
    [clientId, reload, t.loadError],
  );

  const ask = async () => {
    if (!clientId || !concept) return;
    setAsking(true);
    try {
      await tldoole.request(clientId, concept);
      setAsked(true);
      reload();
    } catch (cause) {
      setError(cause instanceof TldooleError ? cause.message : t.loadError);
    } finally {
      setAsking(false);
    }
  };

  if (!hydrated) return <Spinner className="m-10" label={t.title} />;

  if (!clientId) {
    return (
      <div className="mx-auto flex max-w-xl flex-1 flex-col items-center justify-center gap-4 px-6 py-16 text-center">
        <Film aria-hidden className="size-10 text-navy" />
        <h1 className="text-xl font-semibold text-ink-950">{t.title}</h1>
        <p className="text-ink-600">{t.noClient}</p>
        <Link href="/" className="font-medium text-navy hover:underline">
          {t.startProfile}
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto grid w-full max-w-6xl flex-1 gap-6 px-4 py-6 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
      <section aria-label={t.title} className="h-[calc(100dvh-9rem)] snap-y snap-mandatory overflow-y-auto overscroll-contain rounded-2xl">
        {feed && feed.videos.length === 0 ? <p className="p-6 text-sm text-ink-600">{t.empty}</p> : null}
        {!feed && !loadError ? <Spinner className="m-10" /> : null}
        {feed?.videos.map((video) => <VideoSlide key={video.video_id} video={video} t={t} onFeedback={onFeedback} />)}
      </section>

      <aside className="space-y-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-ink-950">{t.title}</h1>
          <p className="mt-1 text-sm text-ink-600">{t.intro}</p>
          {error || loadError ? (
            <p className="mt-2 text-sm text-critical-ink" role="alert">
              {error ?? loadError?.message ?? t.loadError}
            </p>
          ) : null}
        </div>

        <Card>
          <CardHeader title={t.gaps} icon={<Sparkles aria-hidden className="size-4" />} />
          <ul className="divide-y divide-ink-150">
            {(feed?.gaps ?? []).length === 0 ? <li className="px-5 py-3 text-sm text-ink-500">{t.gapsEmpty}</li> : null}
            {feed?.gaps.map((gap) => (
              <li key={gap.concept_id} className="px-5 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-ink-900">{gap.label}</span>
                  {gap.confidence != null ? <Badge tone="neutral">{t.confidence(gap.confidence)}</Badge> : null}
                  {gap.detector ? <Badge tone="outline">{t.detector[gap.detector] ?? gap.detector}</Badge> : null}
                  {gap.status ? <Badge tone={gap.status === "resolved" ? "good" : gap.status === "unclear" ? "warning" : "brand"}>{t.gapStatus[gap.status] ?? gap.status}</Badge> : null}
                </div>
                {gap.reason ? <p className="mt-1 text-sm text-ink-600">{gap.reason}</p> : null}
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <CardHeader title={t.ask} subtitle={t.askHint} icon={<Wand2 aria-hidden className="size-4" />} />
          <div className="flex flex-wrap items-center gap-2 px-5 py-4">
            <label className="sr-only" htmlFor="tldoole-concept">
              {t.ask}
            </label>
            <select
              id="tldoole-concept"
              value={concept}
              onChange={(event) => {
                setConcept(event.target.value);
                setAsked(false);
              }}
              className="h-10 min-w-0 flex-1 rounded-lg bg-white px-3 text-sm ring-1 ring-inset ring-ink-300"
            >
              <option value="">—</option>
              {feed?.catalog.map((item) => (
                <option key={item.concept_id} value={item.concept_id}>
                  {item.label} · {item.title}
                </option>
              ))}
            </select>
            <Button onClick={() => void ask()} loading={asking} disabled={!concept}>
              {t.askButton}
            </Button>
            {asked ? (
              <p className="w-full text-sm text-good-ink" role="status">
                {t.askDone}
              </p>
            ) : null}
          </div>
        </Card>

        <Card>
          <CardHeader title={t.how} icon={<Film aria-hidden className="size-4" />} />
          <ol className="list-decimal space-y-1 px-9 py-4 text-sm text-ink-700">
            {t.howSteps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </Card>
      </aside>
    </div>
  );
}
