"use client";

import { useI18n } from "@/lib/i18n/provider";

export function Footer() {
  const { t } = useI18n();
  return (
    <footer className="mt-auto border-t border-ink-200 bg-white">
      <div className="mx-auto flex max-w-[1680px] flex-col gap-1 px-4 py-5 text-xs text-ink-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>AlphaForge AI · {t.footer.team}</p>
        <p>{t.footer.data}</p>
      </div>
    </footer>
  );
}
