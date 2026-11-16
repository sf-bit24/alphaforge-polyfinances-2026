import { PageSkeleton } from "@/components/ui/skeleton";
import { serverDictionary } from "@/lib/i18n/server";

/** Between two screens: the page's outline at once, while the next screen arrives (the bar at the top runs too). */
export default async function Loading() {
  const { t } = await serverDictionary();
  return <PageSkeleton label={t.common.loading} />;
}
