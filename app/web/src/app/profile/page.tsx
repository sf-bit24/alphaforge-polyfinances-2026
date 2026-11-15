import type { Metadata } from "next";
import { ProfileWorkspace } from "@/components/profile/workspace";
import { serverDictionary } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await serverDictionary();
  return { title: t.nav.profile };
}

export default function ProfilePage() {
  return <ProfileWorkspace />;
}
