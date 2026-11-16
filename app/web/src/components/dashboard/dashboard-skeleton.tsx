import { cn } from "@/components/ui/cn";
import { Skeleton } from "@/components/ui/skeleton";
import styles from "./dashboard.module.css";

/** The five tiles in their colours and places, each with grey lines where its figure will be. */
const TILES = [styles.tNavy, styles.tBlue, styles.tRed, styles.tGold, styles.tGreen];

export function BentoSkeleton({ label }: { label: string }) {
  return (
    <section role="status" aria-label={label} className={styles.bento}>
      {TILES.map((tone) => (
        <div key={tone} aria-hidden className={cn(styles.tile, tone)}>
          <Skeleton className="size-6" tone="tinted" />
          <Skeleton className="mt-auto h-8 w-24" tone="tinted" />
          <Skeleton className="mt-3 h-3.5 w-36" tone="tinted" />
          <Skeleton className="mt-2 h-3 w-full max-w-52" tone="tinted" />
        </div>
      ))}
    </section>
  );
}

/** The whole dashboard while the profile loads: the greeting, the tiles, and Yan's frame. */
export function DashboardSkeleton({ label }: { label: string }) {
  return (
    <div className={styles.main}>
      <section className={styles.head} aria-hidden>
        <div>
          <Skeleton className="h-7 w-40" />
          <Skeleton className="mt-2 h-3.5 w-80 max-w-full" />
        </div>
      </section>
      <BentoSkeleton label={label} />
      <section className={styles.assist} aria-hidden>
        <div className={styles.assistH}>
          <Skeleton className="h-6 w-56" />
        </div>
        <div className={cn(styles.frame, "gap-4 p-6")}>
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="mt-auto h-12 w-full rounded-xl" />
        </div>
      </section>
    </div>
  );
}
