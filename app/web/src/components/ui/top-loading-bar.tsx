"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useBusy } from "@/lib/client/activity";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "./cn";

/** A short wait shows nothing; the bar appears after this delay, and lingers a moment once done. */
const SHOW_AFTER_MS = 120;
const HIDE_AFTER_MS = 200;

/** Same-origin link to another page, clicked without a modifier: a navigation is starting. */
function navigationTarget(event: MouseEvent): boolean {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
  const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
  if (!(link instanceof HTMLAnchorElement) || link.target === "_blank" || link.hasAttribute("download")) return false;
  const url = new URL(link.href, window.location.href);
  return url.origin === window.location.origin && url.pathname !== window.location.pathname;
}

/** True from a click on a link to another page until the new page is there. */
function useNavigating(): boolean {
  const pathname = usePathname();
  const [from, setFrom] = useState<string | null>(null);
  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (navigationTarget(event)) setFrom(window.location.pathname);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);
  return from !== null && from === pathname;
}

/** The thin red bar at the very top of every screen while something loads: a request in flight or a page on its way. */
export function TopLoadingBar() {
  const { t } = useI18n();
  const busy = useBusy();
  const navigating = useNavigating();
  const loading = busy || navigating;
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setShown(loading), loading ? SHOW_AFTER_MS : HIDE_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, [loading]);
  return (
    <div
      role="progressbar"
      aria-label={t.common.loading}
      aria-hidden={!shown}
      className={cn("pointer-events-none fixed inset-x-0 top-0 z-[70] h-[3px] overflow-hidden transition-opacity duration-200", shown ? "opacity-100" : "opacity-0")}
    >
      <div className="h-full w-full origin-left animate-loading-bar bg-red" />
    </div>
  );
}
