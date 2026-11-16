import { cn } from "./cn";

/** `tinted` takes the colour of the text around it, for a placeholder on a coloured tile. `cn` does not merge: never override the colour by className. */
const TONES = { grey: "bg-ink-150", tinted: "bg-current/15" };

/** A block that pulses while its content loads; give it the size of what it stands for. */
export function Skeleton({ className, tone = "grey" }: { className?: string; tone?: keyof typeof TONES }) {
  return <span aria-hidden className={cn("block animate-shimmer rounded-md", TONES[tone], className)} />;
}

/** A card-shaped placeholder: a title line, then `lines` text lines. */
export function SkeletonCard({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div aria-hidden className={cn("rounded-xl bg-surface p-5 shadow-card ring-1 ring-ink-200/80", className)}>
      <Skeleton className="h-4 w-1/3" />
      <div className="mt-4 space-y-2.5">
        {Array.from({ length: lines }, (_, index) => (
          <Skeleton key={index} className={cn("h-3", index === lines - 1 ? "w-2/3" : "w-full")} />
        ))}
      </div>
    </div>
  );
}

/** A whole screen loading: the heading, then a grid of cards. Announced once to screen readers. */
export function PageSkeleton({ label, cards = 4 }: { label: string; cards?: number }) {
  return (
    <div role="status" aria-label={label} className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
      <Skeleton className="h-7 w-48" />
      <Skeleton className="mt-3 h-3.5 w-full max-w-xl" />
      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        {Array.from({ length: cards }, (_, index) => (
          <SkeletonCard key={index} lines={index % 2 ? 4 : 3} />
        ))}
      </div>
    </div>
  );
}

/** Rows of a list loading: an icon and a title, with a description line under it when `withLine`. */
export function SkeletonRows({ label, count = 3, withLine = false, className }: { label: string; count?: number; withLine?: boolean; className?: string }) {
  return (
    <div role="status" aria-label={label} className={cn("space-y-3 py-1", className)}>
      {Array.from({ length: count }, (_, index) => (
        <div key={index} aria-hidden className="flex items-start gap-2.5">
          <Skeleton className="mt-0.5 size-4 shrink-0" />
          <div className="min-w-0 flex-1 space-y-1.5">
            <Skeleton className={cn("h-3.5", index % 3 === 1 ? "w-1/2" : "w-3/4")} />
            {withLine ? <Skeleton className="h-3 w-full" /> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

/** A document loading: its metadata box, a heading and paragraphs. */
export function DocumentSkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-5">
      <Skeleton className="h-16 w-full rounded-xl" />
      <Skeleton className="h-6 w-2/3" />
      {[0, 1, 2].map((paragraph) => (
        <div key={paragraph} className="space-y-2">
          <Skeleton className="h-3.5 w-full" />
          <Skeleton className="h-3.5 w-full" />
          <Skeleton className="h-3.5 w-4/5" />
        </div>
      ))}
    </div>
  );
}
