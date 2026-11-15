"use client";

import { Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/components/ui/cn";
import { Brand } from "./brand";
import { LanguageToggle } from "./language-toggle";
import { ModeChip } from "./mode-chip";

function NavTab({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      ref={active ? (node) => node?.scrollIntoView({ block: "nearest", inline: "nearest" }) : undefined}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex shrink-0 items-center border-b-[3px] px-3.5 text-[15px] whitespace-nowrap no-underline transition-colors",
        active ? "border-red font-[650] text-navy" : "border-transparent text-ink-600 hover:text-navy",
      )}
    >
      {label}
    </Link>
  );
}

function NavTabs({ pathname }: { pathname: string }) {
  const { t } = useI18n();
  const tabs = [
    { href: "/dashboard", label: t.appNav.dashboard },
    { href: "/details", label: t.appNav.details },
    { href: "/", label: t.appNav.profile },
    { href: "/knowledge", label: t.appNav.knowledge },
  ];
  return (
    <nav
      aria-label={t.nav.menu}
      className="order-last -mx-4 -mb-px flex h-11 w-[calc(100%+2rem)] min-w-0 gap-1 overflow-x-auto border-t border-line px-2 [scrollbar-width:none] sm:-mx-8 sm:w-[calc(100%+4rem)] sm:px-6 xl:order-none xl:mx-0 xl:h-16 xl:w-auto xl:border-t-0 xl:px-0"
    >
      {tabs.map((tab) => (
        <NavTab key={tab.href} href={tab.href} label={tab.label} active={tab.href === "/" ? pathname === "/" : pathname.startsWith(tab.href)} />
      ))}
    </nav>
  );
}

function SettingsLink({ active }: { active: boolean }) {
  const { t } = useI18n();
  return (
    <Link
      href="/settings"
      aria-label={t.nav.settings}
      title={t.nav.settings}
      aria-current={active ? "page" : undefined}
      className={cn(
        "grid size-8 place-items-center rounded-md border transition-colors",
        active ? "border-navy bg-navy text-white" : "border-line text-ink-600 hover:border-navy hover:text-navy",
      )}
    >
      <Settings aria-hidden className="size-4" />
    </Link>
  );
}

/** Top navigation of the drafts: brand, tabs with a red underline, the responsible framework and the language. */
export function AppNav() {
  const { t } = useI18n();
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-white">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-navy focus:shadow-lift"
      >
        {t.nav.skip}
      </a>
      {/* One row from 1280 px; below, the tabs go to a second row that scrolls sideways. */}
      <div className="flex flex-wrap items-center gap-x-6 px-4 sm:px-8 xl:gap-x-10">
        <div className="flex h-16 items-center">
          <Brand />
        </div>
        <NavTabs pathname={pathname} />
        <div className="ml-auto flex h-16 shrink-0 items-center gap-3 text-[13px] text-ink-500 sm:gap-[18px]">
          <span className="hidden min-[1536px]:inline">{t.appNav.simulation}</span>
          <ModeChip className="hidden xl:inline-flex" />
          <LanguageToggle />
          <SettingsLink active={pathname.startsWith("/settings")} />
        </div>
      </div>
    </header>
  );
}
