import type { Metadata } from "next";
import { SettingsView } from "@/components/settings/settings-view";
import { serverDictionary } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await serverDictionary();
  return { title: t.settings.title };
}

export default function SettingsPage() {
  return <SettingsView />;
}
