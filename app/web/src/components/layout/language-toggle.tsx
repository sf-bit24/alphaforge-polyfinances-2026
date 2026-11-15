"use client";

import type { Locale } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/components/ui/cn";

const LOCALES: Locale[] = ["fr", "en"];

/** Switches the interface at once, and asks the runtime to localize agent texts too. */
export function LanguageToggle({ tone = "dark" }: { tone?: "dark" | "light" }) {
  const { locale, setLocale, t } = useI18n();
  const session = useSession();

  const change = (next: Locale) => {
    if (next === locale) return;
    setLocale(next);
    if (session.state && session.clientId) void session.updateSettings({ locale: next });
  };

  return (
    <div
      role="group"
      aria-label={t.language.label}
      className={cn(
        "inline-flex rounded-lg p-0.5 text-xs font-semibold",
        tone === "dark" ? "bg-white/10 ring-1 ring-white/15" : "bg-ink-100 ring-1 ring-ink-200",
      )}
    >
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
              "rounded-md px-2.5 py-1 uppercase transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand-300",
              tone === "dark"
                ? active
                  ? "bg-white text-ink-950"
                  : "text-ink-200 hover:text-white"
                : active
                  ? "bg-white text-ink-950 shadow-sm"
                  : "text-ink-600 hover:text-ink-900",
            )}
          >
            {option}
          </button>
        );
      })}
    </div>
  );
}
