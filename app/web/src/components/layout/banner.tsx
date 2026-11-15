"use client";

import { ShieldCheck } from "lucide-react";
import { useI18n } from "@/lib/i18n/provider";

/** The responsible-use framework, visible on every page. */
export function ResponsibleBanner() {
  const { t } = useI18n();
  return (
    <div role="note" className="border-b border-warning/40 bg-warning-wash">
      <p className="mx-auto flex max-w-[1680px] items-center gap-2 px-4 py-2 text-[0.8rem] font-medium text-warning-ink sm:px-6">
        <ShieldCheck aria-hidden className="size-4 shrink-0" />
        {t.banner.text}
      </p>
    </div>
  );
}
