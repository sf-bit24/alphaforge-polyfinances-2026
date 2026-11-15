"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/components/ui/cn";
import { LanguageToggle } from "./language-toggle";
import { Logo } from "./logo";
import { ModeChip } from "./mode-chip";

export function Header() {
  const { t } = useI18n();
  const pathname = usePathname();
  const links = [
    { href: "/", label: t.nav.home },
    { href: "/profile", label: t.nav.profile },
    { href: "/knowledge", label: t.nav.knowledge },
    { href: "/settings", label: t.nav.settings },
  ];
  return (
    <header className="sticky top-0 z-30 bg-ink-950 text-white shadow-[0_1px_0_rgb(255_255_255/0.06)]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-ink-950"
      >
        {t.nav.skip}
      </a>
      {/* Below md the nav takes a second row: 3rem + 2.5rem = 5.5rem, the offset of sticky elements (workspace CompactSummary). */}
      <div className="mx-auto flex max-w-[1680px] flex-wrap items-center gap-x-4 px-4 sm:px-6 md:h-14 md:flex-nowrap">
        <Link href="/" className="flex h-12 shrink-0 items-center gap-2.5 rounded-md focus-visible:outline-2 focus-visible:outline-brand-300 md:h-auto">
          <Logo className="size-8" />
          <span className="leading-tight">
            <span className="block text-[0.95rem] font-semibold tracking-tight">AlphaForge AI</span>
            <span className="hidden text-[0.7rem] text-ink-300 xl:block">{t.brand.tagline}</span>
          </span>
        </Link>
        <nav
          aria-label={t.nav.menu}
          className="order-last -mx-1 flex h-10 w-full min-w-0 items-center gap-0.5 overflow-x-auto px-1 pb-1 md:order-none md:ml-4 md:h-auto md:w-auto md:pb-0"
        >
          {links.map((link) => {
            const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-sm font-medium whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-brand-300",
                  active ? "bg-white/12 text-white" : "text-ink-300 hover:bg-white/6 hover:text-white",
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex shrink-0 items-center gap-3">
          <ModeChip />
          <LanguageToggle />
        </div>
      </div>
    </header>
  );
}
