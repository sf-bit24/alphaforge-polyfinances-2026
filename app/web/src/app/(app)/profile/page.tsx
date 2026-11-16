import type { Metadata } from "next";
import { ProfileView } from "@/components/profile/profile-view";
import { serverDictionary } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await serverDictionary();
  return { title: t.appNav.profile };
}

export default function ProfilePage() {
  return <ProfileView />;
}
