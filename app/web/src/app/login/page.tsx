import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { LoginView } from "@/components/auth/login-view";
import { getAuthConfig } from "@/lib/server/config";
import { safeNext } from "@/lib/server/auth/routes";
import { NOTICE_COOKIE, SESSION_COOKIE, sessionOf } from "@/lib/server/auth/session";
import { serverDictionary } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await serverDictionary();
  return { title: t.auth.title };
}

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);

/**
 * « Se connecter » (CONTRACTS.md 7.1): the way in when sign-in is on. Without sign-in, or with a
 * session already, the page sends the browser on to where it was going. After « Supprimer mon compte »,
 * it says « Compte supprimé ».
 */
export default async function LoginPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const next = safeNext(first(params.next));
  const config = getAuthConfig();
  if (config.AUTH_MODE === "off") redirect(next);
  const jar = await cookies();
  if (sessionOf(jar.get(SESSION_COOKIE)?.value, config)) redirect(next);
  // Set by `POST /api/auth/delete-account`, read here after the round trip through Cognito's `/logout`.
  const deleted = jar.get(NOTICE_COOKIE)?.value === "account_deleted";
  return <LoginView next={next} error={first(params.error) ?? null} deleted={deleted} />;
}
