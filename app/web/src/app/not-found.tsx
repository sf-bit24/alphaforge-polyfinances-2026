import Link from "next/link";
import { serverDictionary } from "@/lib/i18n/server";

export default async function NotFound() {
  const { t } = await serverDictionary();
  return (
    <div className="mx-auto max-w-xl px-4 py-24 text-center">
      <p className="font-mono text-sm text-ink-500">404</p>
      <h1 className="mt-2 text-2xl font-semibold text-ink-950">{t.errors.hints.not_found}</h1>
      <Link href="/" className="mt-6 inline-block font-medium text-brand-700 underline underline-offset-2">
        {t.nav.home}
      </Link>
    </div>
  );
}
