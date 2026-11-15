import type { Metadata } from "next";
import { Journey } from "@/components/journey/journey";
import { serverDictionary } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await serverDictionary();
  return { title: t.appNav.profile };
}

/** The profile journey: the walker, one stop per base question, then the house. */
export default function JourneyPage() {
  return (
    <main id="main" tabIndex={-1} className="focus:outline-none">
      <Journey />
    </main>
  );
}
