"use client";

import Link from "next/link";
import type { ClientState } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import { useI18n } from "@/lib/i18n/provider";
import { useSampleMode } from "@/components/dashboard/dashboard-view";
import { ExposuresView } from "@/components/profile/exposures";
import { cn } from "@/components/ui/cn";
import { Spinner } from "@/components/ui/spinner";
import styles from "./details.module.css";
import { SampleDetails } from "./sample-details";

/** `local` and `aws` modes: no portfolio engine in version 1, so only what is computed is shown. */
function RealDetails({ state }: { state: ClientState | null }) {
  const { t } = useI18n();
  const confirmed = state?.portfolio && state.portfolio.status === "confirmed" ? state.portfolio : null;
  return (
    <div className={styles.main}>
      <div className={styles.head}>
        <div>
          <h1>{t.details.title}</h1>
          <p>{t.details.realLead}</p>
        </div>
        <Link className={styles.btn} href="/dashboard">
          {t.details.back}
        </Link>
      </div>
      <div className={styles.grid}>
        <section className={cn(styles.tile, styles.tWide, styles.v2)}>
          <h2>{t.details.v2.title}</h2>
          <p>{t.details.v2.text}</p>
          <ul>
            {t.details.v2.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>{t.details.v2.honest}</p>
        </section>
        <section className={cn(styles.tile, styles.tWide)} aria-label={t.details.existing.title}>
          <header>
            <h2>{t.details.existing.title}</h2>
          </header>
          {confirmed ? (
            <ExposuresView exposures={confirmed.exposures} positions={confirmed.positions} sources={confirmed.sources} fx={confirmed.fx} />
          ) : (
            <div className={styles.v2}>
              <p>{t.details.existing.none}</p>
              <p>
                <Link href="/" className={styles.btn}>
                  {t.details.existing.cta}
                </Link>
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export function DetailsView() {
  const { t } = useI18n();
  const session = useSession();
  const sample = useSampleMode();
  if (sample === null || (!sample && (!session.hydrated || (session.resuming && !session.state)))) {
    return (
      <div className={styles.page}>
        <div className="flex items-center justify-center py-24">
          <Spinner label={t.common.loading} />
        </div>
      </div>
    );
  }
  return <div className={styles.page}>{sample ? <SampleDetails /> : <RealDetails state={session.state} />}</div>;
}
