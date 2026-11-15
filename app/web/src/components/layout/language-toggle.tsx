"use client";

import type { Locale } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/components/ui/cn";

const LOCALES: Locale[] = ["fr", "en"];

/** The drafts' FR / EN switch. It changes the interface at once and asks the runtime to localize agent texts too. */
export function LanguageToggle({ className }: { className?: string }) {
  const { locale, setLocale, t } = useI18n();
  const session = useSession();

  const change = (next: Locale) => {
    if (next === locale) return;
    setLocale(next);
    if (session.state && session.clientId) void session.updateSettings({ locale: next });
  };

  return (
    <div role="group" aria-label={t.language.label} className={cn("flex overflow-hidden rounded-md border border-line text-[13px]", className)}>
      {LOCALES.map((option) => {
        const active = option === locale;
        return (
          <button
            key={option}
            type="button"
            aria-pressed={active}
            aria-label={t.language.switchTo[option]}
            onClick={() => change(option)}
            className={cn(
              "px-2.5 py-1 uppercase transition-colors",
              active ? "bg-navy text-white" : "bg-white text-ink-500 hover:text-navy",
            )}
          >
            {option}
          </button>
        );
      })}
    </div>
  );
}
