import type { Metadata } from "next";
import { DashboardView } from "@/components/dashboard/dashboard-view";
import { serverDictionary } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await serverDictionary();
  return { title: t.appNav.dashboard };
}

export default function DashboardPage() {
  return <DashboardView />;
}
