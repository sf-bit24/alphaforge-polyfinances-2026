import type { Metadata } from "next";
import { DetailsView } from "@/components/details/details-view";
import { serverDictionary } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await serverDictionary();
  return { title: t.details.title };
}

export default function DetailsPage() {
  return <DetailsView />;
}
