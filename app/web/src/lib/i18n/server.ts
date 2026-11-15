import "server-only";
import { cookies } from "next/headers";
import { dictionaries } from "./dictionary";
import { LOCALE_COOKIE, parseLocale } from "./locale";

/** Locale chosen by the investor (cookie), for server-rendered metadata. */
export async function serverDictionary() {
  const locale = parseLocale((await cookies()).get(LOCALE_COOKIE)?.value);
  return { locale, t: dictionaries[locale] };
}
