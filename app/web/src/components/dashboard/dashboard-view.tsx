"use client";

import Link from "next/link";
import { useHealth } from "@/lib/client/health";
import { useSession } from "@/lib/client/session";
import { formatPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { itemForStage } from "@/lib/journey/path";
import { cn } from "@/components/ui/cn";
import { Spinner } from "@/components/ui/spinner";
import { Assistant } from "./assistant";
import { ProfileBento, SampleBento } from "./bento";
import s from "./dashboard.module.css";

/** Example portfolio data are shown against the simulator only (team decision of 2026-11-14). */
export function useSampleMode(): boolean | null {
  const { locale } = useI18n();
  const { status, health } = useHealth(locale);
  if (status === "idle" || status === "loading") return null;
  return health?.mode === "mock";
}

function Gate({ title, text, cta }: { title: string; text: string; cta: string }) {
  return (
    <div className={s.gate}>
      <h1>{title}</h1>
      <p>{text}</p>
      <Link href="/" className={cn(s.btn, s.btnPrimary)}>
        {cta}
      </Link>
    </div>
  );
}

export function DashboardView() {
  const { t, locale } = useI18n();
  const session = useSession();
  const sample = useSampleMode();

  if (!session.hydrated || (session.resuming && !session.state)) {
    return (
      <div className="flex flex-1 items-center justify-center py-24">
        <Spinner label={t.session.loading} />
      </div>
    );
  }
  const state = session.state;
  if (!state) return <Gate title={t.dash.gate.noneTitle} text={t.dash.gate.noneText} cta={t.dash.gate.noneCta} />;
  if (itemForStage(state.stage) !== "house") return <Gate title={t.dash.gate.baseTitle} text={t.dash.gate.baseText} cta={t.dash.gate.baseCta} />;

  const { completeness } = state;
  return (
    <div className={s.main}>
      <section className={s.head}>
        <div>
          <h1>{t.dash.hello}</h1>
          <p>{sample ? t.dash.leadSample : t.dash.leadReal}</p>
        </div>
        <div className={s.headRight}>
          {sample ? <span className={s.example}>{t.dash.exampleChip}</span> : null}
          <Link className={s.btn} href="/details">
            {t.dash.allDetails}
          </Link>
        </div>
      </section>

      {sample === null ? <div className={s.bento} aria-busy /> : sample ? <SampleBento /> : <ProfileBento state={state} />}

      <section className={s.assist} aria-labelledby="assistant-title">
        <div className={s.assistH}>
          <div className={s.assistNote}>
            <h2 id="assistant-title">{t.assistant.title}</h2>
            <span className={cn(s.pill, completeness.ready && s.pillReady)}>{t.assistant.profilePill(formatPercent(completeness.displayed, locale))}</span>
          </div>
          <p>{sample ? t.assistant.noteSample : t.assistant.noteReal}</p>
        </div>
        <Assistant key={state.client_id} state={state} sample={sample === true} />
      </section>
    </div>
  );
}
