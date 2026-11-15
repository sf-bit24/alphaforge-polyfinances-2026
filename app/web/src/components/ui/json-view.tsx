import { cn } from "./cn";

/** Pretty-printed JSON, for trace inputs/outputs and structured document data. */
export function JsonView({ value, className, maxHeight = "max-h-72" }: { value: unknown; className?: string; maxHeight?: string }) {
  let text: string;
  try {
    text = JSON.stringify(value, null, 2) ?? String(value);
  } catch {
    text = String(value);
  }
  return (
    <pre
      tabIndex={0}
      className={cn(
        "overflow-auto rounded-lg border border-ink-150 bg-ink-50 p-3 font-mono text-[0.75rem] leading-relaxed text-ink-800",
        "focus-visible:outline-2 focus-visible:outline-focus",
        maxHeight,
        className,
      )}
    >
      {text}
    </pre>
  );
}
