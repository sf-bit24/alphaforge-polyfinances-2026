import Link from "next/link";
import { cn } from "@/components/ui/cn";

/** The drafts' mark: a red rounded square and the name (no bank logo). Yan's pixels fly out of the square (`data-yan-home`). */
export function Brand({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      className={cn("flex shrink-0 items-center gap-2.5 rounded-md text-[17px] font-bold text-navy no-underline", className)}
    >
      <i aria-hidden data-yan-home className="inline-block size-[22px] rounded-md bg-red" />
      AlphaForge AI
    </Link>
  );
}
